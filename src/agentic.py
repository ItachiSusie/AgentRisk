"""Agentic distillation, round three (docs/agentic-distill/00-common.md).

Subcommands
  audit   stage A (blind fact audit: no gold, no predicted level) + stage B (classification with
          gold and prediction) + mechanical consistency checks K0-K8, one re-ask on contradiction.
          Writes results/analysis/<task>/<run_id>-audit-v3d/audit.jsonl, summary.md and, with
          --spot-check N, spot-check.md for a human to grade.
  repair  stage C: for every audited failure that is consistent and repairable, write a patch,
          check it for sample-specific terms, re-run the predictor on a train_evolve regression
          set, feed the result back, at most --max-attempts times. Writes repair.jsonl in the
          lessons format that src/merge_lessons.py reads.

Usage
    python src/agentic.py audit --triage <run_dir>/triage/triage.jsonl --pairs 3:4 --limit 20
    python src/agentic.py audit --triage ... --pairs 3:4,4:3 --spot-check 10 --seed 0
    python src/agentic.py repair --audit results/analysis/task1/<run_id>-audit-v3d/audit.jsonl --limit 10
"""
import argparse
import json
import random
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from analyst import (analyst_client, build_pool, call_json, load_reasoning, norm, quote_in_text,
                     tokenize)
from common import DOMAINS, DRIVERS, load_jsonl, task_fields
from regress import build_system, flips, is_correct, label_of, predict_rows
from run import output_format_for

ROOT = Path(__file__).resolve().parent.parent
FACT_LAYERS = ("correct", "misread", "missed", "misread+missed")
CATEGORIES = {
    "task1": ("reading", "target_confusion", "weighting", "threshold", "scale",
              "gold_questionable", "unexplained"),   # v3d merges threshold + weighting into scale
    "task2a": ("reading", "target_confusion", "weighting", "cardinality", "confusable_pair",
               "missed_harm", "gold_questionable", "unexplained"),   # weighting: v3/v3b only
}
CATEGORIES["task2b"] = CATEGORIES["task2a"]
REPAIRABLE = {"reading", "target_confusion", "weighting", "threshold", "scale", "cardinality",
              "confusable_pair", "missed_harm"}
STAGE_A_CHECKS = {"K0", "K5", "K6", "K9"}

LEVEL_WORDS = r"(?:minimal|low|moderate|high|critical)"
LEVEL_PATTERNS = [
    re.compile(rf"\b{LEVEL_WORDS}\b(?:-(?:to|end)-{LEVEL_WORDS})?", re.I),
    re.compile(r"\b(?:severity|level|risk_severity|risk severity|score|rated?|rating)\s*(?:of\s*|=\s*|:\s*|is\s*)?[1-5]\b", re.I),
    re.compile(r"\b[1-5]\s*(?:/\s*5|out of 5)\b", re.I),
    re.compile(r"\((?:[1-5])\)"),
]


# ---------------------------------------------------------------- text helpers
LABELS_OF = {"task2a": DOMAINS, "task2b": DRIVERS}


def moves(item):
    """Task 1 audits say moves_level, Task 2 audits say moves_labels; missing counts as moving."""
    for key in ("moves_level", "moves_labels"):
        if key in item:
            return bool(item[key])
    return True


def mask_labels(text, task):
    """Blind the stage-A analyst on Task 2: replace every label name with [LABEL] (D13)."""
    for label in sorted(LABELS_OF[task], key=len, reverse=True):
        parts = [re.escape(x.strip()) for x in label.split("/")]
        text = re.sub(r"\s*/\s*".join(parts), "[LABEL]", text, flags=re.I)
    return text


def blind_text(said, task):
    return mask_levels(said) if task == "task1" else mask_labels(said, task)


def as_key(x):
    """Comparable form of a label: an int level, or a sorted tuple of labels."""
    return tuple(sorted(x)) if isinstance(x, (list, tuple)) else x


def mask_levels(text):
    """Blind the stage-A analyst: replace every severity word or number-as-level with [LEVEL]."""
    for pat in LEVEL_PATTERNS:
        text = pat.sub("[LEVEL]", text)
    return text


def stated_text(reasoning):
    """The model's stated rationale as one string, for both reason and facts lineages."""
    if isinstance(reasoning, dict):
        lines = ["FACTS:"] + [f"- \"{f['quote']}\" — {f['note']}" for f in reasoning["facts"]]
        return "\n".join(lines + ["JUDGMENT: " + reasoning.get("judgment", "")])
    return reasoning or ""


def in_text(quote, hay_norm, min_len=8):
    q = norm(quote)
    return len(q) >= min_len and q in hay_norm


def missed_quotes(a, level_moving_only=False):
    """missed_facts is a list of strings (v3) or of {quote, moves_level, would_change_to} (v3b)."""
    out = []
    for m in a.get("missed_facts") or []:
        if isinstance(m, dict):
            if level_moving_only and not moves(m):
                continue
            out.append(m.get("quote") or "")
        else:
            out.append(m)
    return out


def derived_fact_layer(a):
    bad = any(not c.get("supported") and moves(c) for c in a.get("claims") or [])
    missed = bool(missed_quotes(a, level_moving_only=True))
    return {(False, False): "correct", (True, False): "misread",
            (False, True): "missed", (True, True): "misread+missed"}[(bad, missed)]


def blind_view(a):
    """(level the blind audit favours or None, whether it could not tell the two levels apart).

    v3 / v3b: blind_implied + adjacent_defensible (a yes/no that came back true 41/41 times).
    v3c: favoured_level is one of the two candidate levels, or "cannot_tell".
    """
    if "favoured_labels" in a:
        fav = a.get("favoured_labels")
        return (None, True) if fav == "cannot_tell" else (as_key(fav or []), False)
    if "favoured_level" in a:
        fav = a.get("favoured_level")
        return (fav if isinstance(fav, int) else None), fav == "cannot_tell"
    return a.get("blind_implied"), bool(a.get("adjacent_defensible"))


# ---------------------------------------------------------------- consistency (K0-K8)
def mechanical(a, reasoning_text, row):
    """Substring checks on the stage-A quotes; nothing here needs a model."""
    traj = norm(row["formatted_interaction"] + "\n" + row["proposed_action"])
    said = norm(reasoning_text)
    claims = a.get("claims") or []
    return {
        "claims_in_reasoning": [in_text(c.get("claim", ""), said) for c in claims],
        "evidence_in_trajectory": [None if not c.get("evidence") else quote_in_text(c["evidence"], traj)
                                   for c in claims],
        # short field lines such as "Matches: 2" are legitimate evidence, so 6 characters suffice here
        "missed_in_trajectory": [in_text(q, traj, min_len=6) for q in missed_quotes(a)],
        "level_moving_missed_in_trajectory": [in_text(q, traj, min_len=6)
                                              for q in missed_quotes(a, level_moving_only=True)],
        "missed_already_stated": [q for q in missed_quotes(a)
                                  if len(norm(q)) >= 12 and norm(q).lower()[:60] in said.lower()],
    }


def consistency_check(task, a, b, gold, pred, mech):
    """Return a list of violated rules, each 'Kn: explanation'. Empty list = consistent."""
    v = []
    fl, cat = a.get("fact_layer"), b.get("category")
    if fl not in FACT_LAYERS:
        v.append(f"K0: fact_layer {fl!r} is not one of {FACT_LAYERS}")
    elif fl != derived_fact_layer(a):
        v.append(f"K0: fact_layer is {fl!r} but the listed claims and missed_facts imply "
                 f"{derived_fact_layer(a)!r}")
    if cat not in CATEGORIES[task]:
        v.append(f"K1: category {cat!r} is not one of {CATEGORIES[task]}")
        return v
    if cat in ("reading", "missed_harm") and fl == "correct":
        v.append(f"K1: category is {cat} but fact_layer is correct")
    if fl in FACT_LAYERS and fl != "correct" and cat not in (
            "reading", "target_confusion", "gold_questionable", "unexplained", "missed_harm"):
        v.append(f"K1: fact_layer is {fl!r} but category {cat!r} assumes a correct reading")
    if cat in ("threshold", "weighting", "scale", "cardinality", "confusable_pair") and fl != "correct":
        v.append(f"K2: category {cat!r} requires fact_layer correct, got {fl!r}")
    if task == "task1":
        bi, adj = blind_view(a)
        if cat == "threshold" and not (bi == pred or adj):
            v.append(f"K3: threshold needs blind_implied == prediction ({pred}) or "
                     f"adjacent_defensible; got blind_implied {bi}, adjacent_defensible {adj}")
        if cat == "weighting" and not (bi == gold and not adj):
            v.append(f"K4: weighting needs blind_implied == gold ({gold}) and adjacent_defensible "
                     f"false; got {bi}, {adj}")
        if cat == "gold_questionable" and bi == gold:
            v.append(f"K8: gold_questionable but blind_implied equals gold ({gold})")
    if fl in ("misread", "misread+missed"):
        ok = [m for c, m in zip(a.get("claims") or [], mech["claims_in_reasoning"])
              if not c.get("supported") and moves(c) and m]
        if not ok:
            v.append("K5: fact_layer says misread but no unsupported claim is a verbatim part "
                     "of the reasoning")
    if fl in ("missed", "misread+missed") and not any(mech["level_moving_missed_in_trajectory"]):
        v.append("K6: fact_layer says missed but no missed_fact is a verbatim quote of the trajectory")
    if mech.get("missed_already_stated"):
        v.append("K9: listed as not known, but the assessor's output already states it: "
                 + "; ".join(mech["missed_already_stated"])[:300])
    if task != "task1" and cat == "gold_questionable":
        bi, _ = blind_view(a)
        if bi == as_key(gold):
            v.append("K8: gold_questionable but the blind audit favours the gold label set")
    if task != "task1" and cat == "cardinality":
        g, p = set(gold), set(pred)
        if not (g & p) or len(g) == len(p):
            v.append("K7: cardinality needs overlapping sets of different size")
    return v


# ---------------------------------------------------------------- run context
def load_context(triage_path):
    run_dir = Path(triage_path).parent.parent
    config = json.loads((run_dir / "config.json").read_text())
    task = config.get("task", "multi")
    if task not in CATEGORIES:
        sys.exit(f"agentic.py supports single-task runs only; {run_dir} is {task}")
    rows = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}
    return {"run_dir": run_dir, "config": config, "task": task, "rows": rows, "preds": preds,
            "triage": {r["example_id"]: r for r in load_jsonl(Path(triage_path))},
            "reasoning": load_reasoning(run_dir),
            "instruction": (ROOT / config["prompt_file"]).read_text(encoding="utf-8")}


def gold_pred(ctx, eid):
    field = task_fields(ctx["task"])[0]
    return ctx["rows"][eid][field], ctx["preds"][eid][field]


def select_failures(ctx, pairs, ids, limit):
    out = []
    for eid in sorted(ctx["triage"]):
        t = ctx["triage"][eid]
        if t.get("status") != "scored" or t.get("bucket") == "exact":
            continue
        if ids and eid not in ids:
            continue
        if pairs and ctx["task"] == "task1" and gold_pred(ctx, eid) not in pairs:
            continue
        out.append(eid)
    return out[:limit] if limit else out


# ---------------------------------------------------------------- audit
def audit_one(ctx, eid, client, params, prompts):
    row, task = ctx["rows"][eid], ctx["task"]
    reasoning = ctx["reasoning"].get(eid)
    if not reasoning:
        return {"example_id": eid, "status": "discarded:no_reasoning"}
    base, said, blind = stage_a_payload(ctx, eid, prompts.get("tag", "v3"))
    base.pop("example_id")
    gold, pred = gold_pred(ctx, eid)
    rec = {"example_id": eid, "gold": gold, "prediction": pred, "model_reasoning": said,
           "masked_reasoning": blind, "rounds": []}

    a_feedback, b_feedback, a = None, None, None
    for rnd in range(2):
        if a is None or a_feedback:
            a, _ = call_json(client, prompts["audit"],
                             dict(base, **({"previous_audit": a, "problems": a_feedback}
                                           if a_feedback else {})), params)
        mech = mechanical(a, blind, row)
        b, _ = call_json(client, prompts["classify"], dict(
            base, blind_audit=a, gold=gold, prediction=pred,
            **({"previous_classification": rec["rounds"][-1]["classify"], "problems": b_feedback}
               if b_feedback else {})), params)
        violations = consistency_check(task, a, b, gold, pred, mech)
        rec["rounds"].append({"audit": a, "classify": b, "mechanical": mech,
                              "violations": violations})
        if not violations:
            break
        a_feedback = [x for x in violations if x.split(":")[0] in STAGE_A_CHECKS] or None
        b_feedback = violations
    return finalize(rec)


def finalize(rec):
    last = rec["rounds"][-1]
    bi, cannot_tell = blind_view(last["audit"])
    rec.update(fact_layer=last["audit"].get("fact_layer"),
               blind_implied=bi, adjacent_defensible=cannot_tell,
               category=last["classify"].get("category"),
               contradiction_first_round=bool(rec["rounds"][0]["violations"]))
    if last["violations"]:
        rec["status"] = "discarded:contradiction"
    elif rec["category"] in REPAIRABLE:
        rec["status"] = "kept"
    else:
        rec["status"] = f"discarded:{rec['category']}"
    return rec


def stage_a_payload(ctx, eid, tag):
    """What the blind stage may see: no gold, no predicted level (v3c adds the two candidates)."""
    row, task = ctx["rows"][eid], ctx["task"]
    said = stated_text(ctx["reasoning"].get(eid))
    blind = blind_text(said, task)
    payload = {"example_id": eid, "trajectory": row["formatted_interaction"],
               "proposed_action": row["proposed_action"], "instruction": ctx["instruction"],
               "assessor_reasoning": blind}
    if tag >= "v3c" and task == "task1":
        payload["candidate_levels"] = sorted(gold_pred(ctx, eid))
    elif tag >= "v3c":   # Task 2: the two label sets, in a fixed order that does not reveal which is gold
        payload["candidate_label_sets"] = sorted(sorted(x) for x in gold_pred(ctx, eid))
    return payload, said, blind


def write_summary(out_dir, recs, task):
    n = len(recs)
    lines = [f"# Audit v3 summary", "", f"- audited: {n}", ""]
    if not n:
        (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
        return
    def table(title, counter):
        lines.extend([f"## {title}", "", "| value | n | share |", "| --- | --- | --- |"])
        for k, v in counter.most_common():
            lines.append(f"| {k} | {v} | {v / n:.0%} |")
        lines.append("")
    table("status", Counter(r["status"] for r in recs))
    table("fact_layer", Counter(r.get("fact_layer") for r in recs))
    table("category", Counter(r.get("category") for r in recs))
    contra = sum(r.get("contradiction_first_round", False) for r in recs)
    lines += [f"- contradiction rate before re-ask: {contra}/{n} = {contra / n:.0%}",
              f"- still contradictory after re-ask: "
              f"{sum(r['status'] == 'discarded:contradiction' for r in recs)}", ""]
    if True:
        rel = Counter()
        for r in recs:
            bi = as_key(r.get("blind_implied"))
            rel["== gold" if bi == as_key(r["gold"]) else "== prediction" if bi == as_key(r["prediction"]) else "other"] += 1
        table("blind_implied versus gold / prediction", rel)
        adj = sum(bool(r.get("adjacent_defensible")) for r in recs)
        lines.append(f"- cannot tell the two levels apart (v3c cannot_tell / v3, v3b adjacent_defensible): {adj}/{n}")
        pairs = Counter((as_key(r["gold"]), as_key(r["prediction"])) for r in recs)
        lines.append("- pairs (gold, prediction): " + ", ".join(f"{k}: {v}" for k, v in sorted(pairs.items())))
    mech_claims = [m for r in recs for m in r["rounds"][-1]["mechanical"]["claims_in_reasoning"]] if recs else []
    if mech_claims:
        lines.append(f"- claims found verbatim in the reasoning: {sum(mech_claims)}/{len(mech_claims)}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_spot_check(out_dir, recs, ctx, n, seed):
    pool = [r for r in recs if r.get("rounds")]
    picked = sorted(random.Random(seed).sample(pool, min(n, len(pool))), key=lambda r: r["example_id"])
    out = ["# 盲测探针人工抽查", "",
           f"从 {len(pool)} 条中随机抽 {len(picked)} 条（seed={seed}）。每条只回答两个问题：",
           "1. 事实层（fact_layer）判得对不对？", "2. 判断层（category）判得对不对？", "",
           "| id | 事实层对吗 | 判断层对吗 | 备注 |", "| --- | --- | --- | --- |"]
    out += [f"| {r['example_id']} |  |  |  |" for r in picked]
    for r in picked:
        row = ctx["rows"][r["example_id"]]
        last = r["rounds"][-1]
        a, b = last["audit"], last["classify"]
        out += ["", "---", "", f"## {r['example_id']}　真实 {r['gold']} / 预测 {r['prediction']}", "",
                f"**最终动作**：`{row['proposed_action'][:400]}`", "",
                "**模型推理（原文）**：", "", "> " + r["model_reasoning"].replace("\n", "\n> "), "",
                (f"**阶段 A（盲审）**：fact_layer = `{a.get('fact_layer')}`，"
                 + (f"按定义更支持 = {a.get('favoured_level')}（候选 {sorted([r['gold'], r['prediction']])}），"
                    f"关键特征 = {a.get('decisive_feature')}" if "favoured_level" in a else
                    f"按定义更支持 = {a.get('favoured_labels')}，关键特征 = {a.get('decisive_feature')}"
                    if "favoured_labels" in a else
                    f"blind_implied = {a.get('blind_implied')}，adjacent_defensible = {a.get('adjacent_defensible')}")), ""]
        for c, ok in zip(a.get("claims") or [], last["mechanical"]["claims_in_reasoning"]):
            mark = "有依据" if c.get("supported") else "**无依据**"
            out.append(f"- {mark}{'' if ok else '（⚠ 引文不在推理原文中）'}：「{c.get('claim')}」"
                       f" ← 轨迹：「{(c.get('evidence') or '（轨迹未提及）')[:300]}」")
        if a.get("missed_facts"):
            out.append("- 推理没提到的事实：")
            for m in a["missed_facts"]:
                if isinstance(m, dict):
                    tag = (f"**会改变等级 → {m.get('would_change_to')}**" if m.get("moves_level")
                           else "不影响等级")
                    out.append(f"  - {tag}：「{(m.get('quote') or '')[:300]}」")
                else:
                    out.append(f"  - 「{m[:300]}」")
        out += ["", f"阶段 A 理由：{a.get('why')}", "",
                f"**阶段 B（归类）**：category = `{b.get('category')}`；factor = {b.get('factor') or '—'}", "",
                f"边界：{b.get('boundary')}", "", f"备注：{b.get('note') or '—'}", ""]
        if len(r["rounds"]) > 1:
            out.append(f"第一轮矛盾：{'; '.join(r['rounds'][0]['violations'])}")
        out.append(f"状态：`{r['status']}`")
    (out_dir / "spot-check.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def cmd_audit(args):
    ctx = load_context(args.triage)
    task = ctx["task"]
    pairs = {tuple(int(x) for x in p.split(":")) for p in args.pairs.split(",")} if args.pairs else None
    ids = set(args.ids.split(",")) if args.ids else None
    todo_all = select_failures(ctx, pairs, ids, args.limit)
    out_dir = Path(args.out_dir) if args.out_dir else (
        ROOT / "results" / "analysis" / task / f"{ctx['run_dir'].name}-audit-{args.tag}")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "audit.jsonl"
    done = {r["example_id"]: r for r in load_jsonl(path)} if path.exists() else {}
    todo = [e for e in todo_all if e not in done]
    prompts = {k: (ROOT / getattr(args, f"{k}_prompt").format(task=task, tag=args.tag)).read_text(encoding="utf-8")
               for k in ("audit", "classify")}
    prompts["tag"] = args.tag
    print(f"{task}: {len(todo_all)} selected, {len(done)} already audited, {len(todo)} to do -> {path}",
          flush=True)
    if args.dry_run:
        eid = todo_all[0]
        said = stated_text(ctx["reasoning"].get(eid))
        print(f"{eid} masked reasoning:\n{blind_text(said, task)}")
        return
    client, params = analyst_client(args)
    lock = threading.Lock()

    def work(eid):
        try:
            rec = audit_one(ctx, eid, client, params, prompts)
        except Exception as exc:  # one bad sample must not stop the batch; it is re-tried on resume
            print(f"  {eid} error: {exc!r}", flush=True)
            return
        with lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"  {eid} {rec['status']} fact={rec.get('fact_layer')} cat={rec.get('category')}"
              f"{' (re-asked)' if rec.get('contradiction_first_round') else ''}", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(work, todo))
    recs = [r for r in load_jsonl(path) if r["example_id"] in set(todo_all)]
    write_summary(out_dir, recs, task)
    if args.spot_check:
        write_spot_check(out_dir, recs, ctx, args.spot_check, args.seed)
    print(f"wrote {out_dir / 'summary.md'}" + (f" and spot-check.md" if args.spot_check else ""))


# ---------------------------------------------------------------- file hand-off (Claude as analyst)
# Without an API key for the analyst, the stages run as files: `export` writes one input file per
# sample, a separate agent session that sees nothing else writes one output file per sample, and
# `import` runs the same mechanical checks and summaries as `audit`. Stage A inputs never contain
# the gold or the predicted level, so a fresh session that reads only its own files stays blind.
STAGES = {"a": ("a_in", "a_out"), "b": ("b_in", "b_out"), "a2": ("a2_in", "a2_out"),
          "b2": ("b2_in", "b2_out")}


def handoff_dir(args, ctx):
    return Path(args.out_dir) if args.out_dir else (
        ROOT / "results" / "analysis" / ctx["task"] / f"{ctx['run_dir'].name}-audit-{args.tag}")


def read_dir(d):
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))} if d.exists() else {}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def cmd_export(args):
    ctx = load_context(args.triage)
    task = ctx["task"]
    out = handoff_dir(args, ctx) / "claude"
    pairs = {tuple(int(x) for x in p.split(":")) for p in args.pairs.split(",")} if args.pairs else None
    ids = select_failures(ctx, pairs, set(args.ids.split(",")) if args.ids else None, args.limit)
    prompt_a = (ROOT / f"prompts/single/{task}/analyst_{args.tag}_audit.txt").read_text(encoding="utf-8")
    prompt_b = (ROOT / f"prompts/single/{task}/analyst_{args.tag}_classify.txt").read_text(encoding="utf-8")
    (out).mkdir(parents=True, exist_ok=True)
    (out / "prompt_a.txt").write_text(prompt_a, encoding="utf-8")
    (out / "prompt_b.txt").write_text(prompt_b, encoding="utf-8")
    a_out, b_out, a2_out = (read_dir(out / STAGES[k][1]) for k in ("a", "b", "a2"))
    n = 0
    for eid in ids:
        payload, _, _ = stage_a_payload(ctx, eid, args.tag)
        gold, pred = gold_pred(ctx, eid)
        if args.stage == "a":
            write_json(out / "a_in" / f"{eid}.json", payload)
        elif args.stage == "b" and eid in a_out:
            write_json(out / "b_in" / f"{eid}.json", dict(payload, blind_audit=a_out[eid],
                                                          gold=gold, prediction=pred))
        elif args.stage == "b2" and (out / "b2_pending" / f"{eid}.json").exists():
            pend = json.loads((out / "b2_pending" / f"{eid}.json").read_text())
            audit = a2_out.get(eid, a_out.get(eid))
            write_json(out / "b2_in" / f"{eid}.json", dict(
                payload, blind_audit=audit, gold=gold, prediction=pred,
                previous_classification=b_out.get(eid), problems=pend["problems"]))
        else:
            continue
        n += 1
    if args.stage == "a":   # the full sample list; later stages only touch a subset of it
        (out / "ids.txt").write_text("\n".join(ids) + "\n")
    print(f"stage {args.stage}: wrote {n} input files to {out / STAGES[args.stage][0]}")


def cmd_import(args):
    ctx = load_context(args.triage)
    task = ctx["task"]
    root = handoff_dir(args, ctx)
    out = root / "claude"
    ids = (out / "ids.txt").read_text().split()
    got = {k: read_dir(out / v[1]) for k, v in STAGES.items()}
    recs, waiting = [], []
    for eid in ids:
        if eid not in got["a"] or eid not in got["b"]:
            waiting.append(eid)
            continue
        _, said, blind = stage_a_payload(ctx, eid, args.tag)
        row, (gold, pred) = ctx["rows"][eid], gold_pred(ctx, eid)
        rec = {"example_id": eid, "gold": gold, "prediction": pred, "model_reasoning": said,
               "masked_reasoning": blind, "analyst": "claude (separate session, file hand-off)",
               "rounds": []}
        a, b = got["a"][eid], got["b"][eid]
        mech = mechanical(a, blind, row)
        v = consistency_check(task, a, b, gold, pred, mech)
        rec["rounds"].append({"audit": a, "classify": b, "mechanical": mech, "violations": v})
        if v:
            if eid in got["b2"]:
                a2 = got["a2"].get(eid, a)
                mech2 = mechanical(a2, blind, row)
                v2 = consistency_check(task, a2, got["b2"][eid], gold, pred, mech2)
                rec["rounds"].append({"audit": a2, "classify": got["b2"][eid], "mechanical": mech2,
                                      "violations": v2})
            else:   # queue a re-ask: stage A again (blind) when the problem is in the audit itself
                a_level = [x for x in v if x.split(":")[0] in STAGE_A_CHECKS]
                if a_level and eid not in got["a2"]:
                    payload, _, _ = stage_a_payload(ctx, eid, args.tag)
                    write_json(out / "a2_in" / f"{eid}.json",
                               dict(payload, previous_audit=a, problems=a_level))
                write_json(out / "b2_pending" / f"{eid}.json", {"problems": v})
                waiting.append(eid)
                continue
        recs.append(finalize(rec))
    with (root / "audit.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    write_summary(root, recs, task)
    if args.spot_check:
        write_spot_check(root, recs, ctx, args.spot_check, args.seed)
    print(f"imported {len(recs)}; waiting for re-ask or outputs: {len(waiting)} {waiting}")
    pend_a = sorted(p.stem for p in (out / "a2_in").glob("*.json")) if (out / "a2_in").exists() else []
    todo_a2 = [e for e in pend_a if e not in got["a2"]]
    if todo_a2:
        print(f"  stage a2 (blind re-audit) needed for: {todo_a2}")


# ---------------------------------------------------------------- repair (stage C)
SPECIFIC = [re.compile(p) for p in (
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",              # e-mail
    r"\b[\w-]+\.(?:example|com|org|net|io|ai|dev|local)\b",  # domains
    r"(?:/[\w.-]+){2,}",                          # paths
    r"\b[A-Z][A-Z0-9]*-[A-Z0-9][\w-]*\b",         # IDs such as D-50831, AGENTRISK-040
    r"`[^`]+`",                                   # quoted commands
)]


def generality_check(patch_text, row, instruction):
    """Terms copied from the failing sample, which a general rule must not contain."""
    text = row["formatted_interaction"] + "\n" + row["proposed_action"]
    bad = set()
    for pat in SPECIFIC:
        for m in pat.findall(text):
            if len(m) >= 4 and m in patch_text:
                bad.add(m)
    known = set(tokenize(instruction))
    # A capitalised word counts only mid-sentence: "Check whether ..." after "RULE:" is ordinary
    # English, while "... sent to Tbilisi" is a name copied from the case.
    for word in set(re.findall(r"\b[A-Z][a-z]{3,}\b", text)):
        if word.lower() in known:
            continue
        for m in re.finditer(rf"\b{re.escape(word)}\b", patch_text):
            before = patch_text[:m.start()].rstrip()
            if before and not before.endswith((":", ".", "!", "?", ";", "(", "\"")):
                bad.add(word)
                break
    if re.search(r"AGENTRISK-\d+", patch_text):
        bad.add("example id")
    return sorted(bad)


def regression_set(ctx, eid, bm25, pool_rows, n_same=5, n_correct=10):
    task, row = ctx["task"], ctx["rows"][eid]
    field = task_fields(task)[0]
    gold, pred = gold_pred(ctx, eid)
    scores = bm25.get_scores(tokenize(row["formatted_interaction"]))
    ranked = [pool_rows[i] for i in sorted(range(len(pool_rows)), key=lambda i: (-scores[i], i))
              if pool_rows[i]["example_id"] != eid]
    def correct_now(r):
        p = ctx["preds"].get(r["example_id"])
        return p is not None and is_correct(p, r, task)
    same = [r for r in ranked if not correct_now(r) and r["example_id"] in ctx["preds"]
            and gold_pred(ctx, r["example_id"]) == (gold, pred)][:n_same] if task == "task1" else \
           [r for r in ranked if not correct_now(r) and r["example_id"] in ctx["preds"]][:n_same]
    if task == "task1":
        sides = [gold, pred]
        side_of = lambda r: r[field] if r[field] in sides else None
    else:
        touched = set(gold) ^ set(pred)
        side_of = lambda r: bool(set(r[field]) & touched)
        sides = [True, False]
    correct = []
    for side in sides:
        correct += [r for r in ranked if correct_now(r) and side_of(r) == side][: n_correct // 2]
    return row, same, correct


def repair_one(ctx, rec, bm25, pool_rows, client, params, patch_sys, args):
    eid, task = rec["example_id"], ctx["task"]
    output_format = output_format_for(task, ctx["config"]["version"])
    row, same, correct = regression_set(ctx, eid, bm25, pool_rows)
    rows = [row] + same + correct
    before = {r["example_id"]: ctx["preds"][r["example_id"]] for r in rows}
    last = rec["rounds"][-1]
    history, field = [], task_fields(task)[0]
    for attempt in range(1, args.max_attempts + 1):
        patch, _ = call_json(client, patch_sys, {
            "instruction": ctx["instruction"], "audit": last["audit"], "classification": last["classify"],
            "gold": rec["gold"], "prediction": rec["prediction"], "previous_attempts": history}, params)
        text = (patch or {}).get("patch_text")
        if not text:
            return dict(status="discarded:patch_refused", attempts=history, patch=patch)
        result = try_patch(ctx, eid, text, row, same, correct, args.concurrency)
        history.append(result)
        if result.get("passed"):
            return dict(status="kept", attempts=history, patch=dict(patch, patch_text=text),
                        regression_ids=[r["example_id"] for r in [row] + same + correct])
    return dict(status="discarded:failed_regression", attempts=history, patch=None)


def try_patch(ctx, eid, text, row, same, correct, concurrency=8):
    """Generality check, then re-run the predictor with the patch on the regression set."""
    task = ctx["task"]
    bad = generality_check(text, row, ctx["instruction"])
    if bad:
        return {"patch_text": text, "rejected_by_generality_check": bad, "passed": False}
    output_format = output_format_for(task, ctx["config"]["version"])
    rows = [row] + same + correct
    before = {r["example_id"]: ctx["preds"][r["example_id"]] for r in rows}
    system = build_system(ctx["instruction"], [text])
    after = predict_rows(system, rows, task, output_format, concurrency)
    fixed, broken = flips(rows, before, after, task)
    correct_ids = {r["example_id"] for r in correct}
    broken_correct = [b for b in broken if b in correct_ids]
    if broken_correct:   # temperature-0 wobble: a sample counts as broken only if it fails twice
        again = predict_rows(system, [r for r in rows if r["example_id"] in broken_correct],
                             task, output_format, concurrency)
        broken_correct = [b for b in broken_correct if not is_correct(again[b], ctx["rows"][b], task)]
    same_ids = {r["example_id"] for r in same}
    net_same = sum(i in same_ids for i in fixed) - sum(i in same_ids for i in broken)
    return {"patch_text": text, "target_fixed": eid in fixed, "fixed": fixed,
            "broken_correct": broken_correct, "net_same_class": net_same,
            "predictions_after": {k: (label_of(v, task) if v else None) for k, v in after.items()},
            "passed": eid in fixed and not broken_correct and net_same >= 0}


# ---------------------------------------------------------------- repair by file hand-off (D14)
# Claude writes each patch in a separate session (patch_in -> patch_out); the code checks it and
# runs the regression with the predictor model (deepseek); the result goes into the next patch_in.
REPAIR_FROM = {"reading", "target_confusion", "missed_harm"}   # Task 2 adds missed_harm (C6)


def repair_state_dir(args):
    return Path(args.out_dir)


def cmd_repair_export(args):
    ctx = load_context(args.triage)
    if "train_evolve" not in ctx["config"]["data_file"]:
        sys.exit("repair regresses on the run's own data; it must be train_evolve")
    audits = [{r["example_id"]: r for r in load_jsonl(Path(d) / "audit.jsonl")} for d in args.audit_dirs]
    ids = sorted(set.intersection(*(set(a) for a in audits)))
    picked = [i for i in ids if all(a[i].get("category") in REPAIR_FROM and a[i].get("status") == "kept"
                                    for a in audits)]
    out = repair_state_dir(args)
    (out / "state").mkdir(parents=True, exist_ok=True)
    patch_path = ROOT / args.patch_prompt.format(task=ctx["task"])   # one patch prompt per task (C8)
    (out / "prompt_patch.txt").write_text(patch_path.read_text(encoding="utf-8"))
    new = 0
    for eid in picked:
        sp = out / "state" / f"{eid}.json"
        if sp.exists():
            continue
        rec = audits[0][eid]
        last = rec["rounds"][-1]
        state = {"example_id": eid, "gold": rec["gold"], "prediction": rec["prediction"],
                 "category": rec["category"], "factor": last["classify"].get("factor"),
                 "audit": last["audit"], "classification": last["classify"],
                 "attempts": [], "status": "open"}
        write_json(sp, state)
        write_patch_in(out, ctx, state)
        new += 1
    print(f"{len(ids)} audited in all runs; {len(picked)} judged {sorted(REPAIR_FROM)} by every run; "
          f"{new} new -> {out / 'patch_in'}")


def write_patch_in(out, ctx, state):
    n = len(state["attempts"]) + 1
    field = task_fields(ctx["task"])[0]
    history = []
    for a in state["attempts"]:
        h = {k: v for k, v in a.items() if k != "predictions_after"}
        # the patch writer cannot fix what it cannot see: show what each broken sample is about
        h["broken_samples"] = [
            {"gold": ctx["rows"][b][field], "prediction_with_patch": (a.get("predictions_after") or {}).get(b),
             "proposed_action": ctx["rows"][b]["proposed_action"][:300]}
            for b in a.get("broken_correct") or []]
        history.append(h)
    write_json(out / "patch_in" / f"{state['example_id']}_a{n}.json", {
        "instruction": ctx["instruction"], "audit": state["audit"],
        "classification": state["classification"], "gold": state["gold"],
        "prediction": state["prediction"], "previous_attempts": history})


def cmd_repair_step(args):
    ctx = load_context(args.triage)
    task, field = ctx["task"], task_fields(ctx["task"])[0]
    out = repair_state_dir(args)
    bm25, pool_rows = build_pool(list(ctx["rows"].values()))
    states = [json.loads(p.read_text()) for p in sorted((out / "state").glob("*.json"))]
    waiting = []
    for st in states:
        if st["status"] != "open":
            continue
        n = len(st["attempts"]) + 1
        po = out / "patch_out" / f"{st['example_id']}_a{n}.json"
        if not po.exists():
            waiting.append(f"{st['example_id']}_a{n}")
            continue
        patch = json.loads(po.read_text())
        text = (patch or {}).get("patch_text")
        if not text:
            st["status"] = "discarded:patch_refused"
            st["attempts"].append({"refused": patch})
        else:
            row, same, correct = regression_set(ctx, st["example_id"], bm25, pool_rows)
            res = try_patch(ctx, st["example_id"], text, row, same, correct, args.concurrency)
            st["attempts"].append(res)
            if res["passed"]:
                st["status"], st["patch"] = "kept", dict(patch, patch_text=text)
                st["regression_ids"] = [r["example_id"] for r in [row] + same + correct]
            elif len(st["attempts"]) >= args.max_attempts:
                st["status"] = "discarded:failed_regression"
            else:
                write_patch_in(out, ctx, st)
                waiting.append(f"{st['example_id']}_a{n + 1}")
        write_json(out / "state" / f"{st['example_id']}.json", st)
        print(f"  {st['example_id']} attempt {n}: {st['status']}"
              + (f" (fixed target={st['attempts'][-1].get('target_fixed')}, broke {st['attempts'][-1].get('broken_correct')})"
                 if 'target_fixed' in st['attempts'][-1] else ""), flush=True)
    # lessons in the format merge_lessons.py reads
    states = [json.loads(p.read_text()) for p in sorted((out / "state").glob("*.json"))]
    with (out / "repair.jsonl").open("w", encoding="utf-8") as f:
        for st in states:
            if st["status"] == "open":
                continue
            f.write(json.dumps({"example_id": st["example_id"], "gold": {field: st["gold"]},
                                "prediction": {field: st["prediction"]}, "category": st["category"],
                                "factor": st.get("factor"), "status": st["status"],
                                "patch": st.get("patch"), "attempts": st["attempts"]},
                               ensure_ascii=False) + "\n")
    c = Counter(st["status"] for st in states)
    print(f"status: {dict(c)}; waiting for patches: {waiting}")




def cmd_repair(args):
    audit_path = Path(args.audit)
    audit = [r for r in load_jsonl(audit_path) if r.get("status") == "kept"]
    run_name = audit_path.parent.name.rsplit("-audit-", 1)[0]
    task = audit_path.parent.parent.name
    triage = next((ROOT / "results" / "_smoke" / task).glob(f"*/{run_name}/triage/triage.jsonl"), None)
    if triage is None:
        sys.exit(f"cannot find the triage of run {run_name} under results/_smoke/{task}")
    ctx = load_context(triage)
    data_file = ctx["config"]["data_file"]
    if "train_evolve" not in data_file:
        sys.exit(f"repair regresses on the run's own data; it must be train_evolve, got {data_file}")
    pool_rows = list(ctx["rows"].values())
    bm25, pool_rows = build_pool(pool_rows)
    out_path = audit_path.parent / "repair.jsonl"
    done = {r["example_id"] for r in load_jsonl(out_path)} if out_path.exists() else set()
    todo = [r for r in audit if r["example_id"] not in done][: args.limit]
    patch_sys = (ROOT / args.patch_prompt).read_text(encoding="utf-8")
    print(f"{len(audit)} repairable, {len(done)} done, {len(todo)} to do -> {out_path}", flush=True)
    if args.dry_run:
        for rec in todo[:3]:
            row, same, correct = regression_set(ctx, rec["example_id"], bm25, pool_rows)
            print(rec["example_id"], "same-class", [r["example_id"] for r in same],
                  "correct", [(r["example_id"], label_of(r, task)) for r in correct])
        return
    client, params = analyst_client(args)
    field = task_fields(task)[0]
    for rec in todo:
        res = repair_one(ctx, rec, bm25, pool_rows, client, params, patch_sys, args)
        lesson = {"example_id": rec["example_id"], "bucket": ctx["triage"][rec["example_id"]]["bucket"],
                  "gold": {field: rec["gold"]}, "prediction": {field: rec["prediction"]},
                  "category": rec["category"], "fact_layer": rec["fact_layer"],
                  "factor": rec["rounds"][-1]["classify"].get("factor"), **res}
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(lesson, ensure_ascii=False) + "\n")
        print(f"  {rec['example_id']} {res['status']} after {len(res['attempts'])} attempt(s)", flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    a = sub.add_parser("audit")
    a.add_argument("--triage", required=True)
    a.add_argument("--pairs", default=None, help="task1 only: gold:pred pairs, e.g. 3:4,4:3")
    a.add_argument("--ids", default=None)
    a.add_argument("--limit", type=int, default=None)
    a.add_argument("--out-dir", default=None)
    a.add_argument("--tag", default="v3", help="analyst prompt version; picks analyst_<tag>_*.txt and the output dir")
    a.add_argument("--audit-prompt", default="prompts/single/{task}/analyst_{tag}_audit.txt")
    a.add_argument("--classify-prompt", default="prompts/single/{task}/analyst_{tag}_classify.txt")
    a.add_argument("--spot-check", type=int, default=0)
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("repair")
    r.add_argument("--audit", required=True)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--max-attempts", type=int, default=3)
    r.add_argument("--patch-prompt", default="prompts/single/analyst_v3_patch.txt")
    r.add_argument("--dry-run", action="store_true")
    for p in (a, r):
        p.add_argument("--concurrency", type=int, default=4)
        p.add_argument("--model", default=None)
        p.add_argument("--base-url", default=None)
        p.add_argument("--api-key-env", default=None)
        p.add_argument("--max-tokens", type=int, default=2048)
    for name, fn in (("repair-export", cmd_repair_export), ("repair-step", cmd_repair_step)):
        x = sub.add_parser(name, help="repair loop by file hand-off: Claude writes patches, the predictor regresses")
        x.add_argument("--triage", required=True)
        x.add_argument("--out-dir", required=True)
        if name == "repair-export":
            x.add_argument("--audit-dirs", nargs="+", required=True)
            x.add_argument("--patch-prompt", default="prompts/single/{task}/analyst_patch_v1.txt")
        else:
            x.add_argument("--max-attempts", type=int, default=3)
            x.add_argument("--concurrency", type=int, default=8)
        x.set_defaults(func=fn)
    for name, fn in (("export", cmd_export), ("import", cmd_import)):
        x = sub.add_parser(name, help="file hand-off for an analyst without an API (Claude session)")
        x.add_argument("--triage", required=True)
        x.add_argument("--tag", default="v3c")
        x.add_argument("--out-dir", default=None)
        if name == "export":
            x.add_argument("--stage", choices=list(STAGES), required=True)
            x.add_argument("--pairs", default=None)
            x.add_argument("--ids", default=None)
            x.add_argument("--limit", type=int, default=None)
        else:
            x.add_argument("--spot-check", type=int, default=0)
            x.add_argument("--seed", type=int, default=0)
        x.set_defaults(func=fn)
    a.set_defaults(func=cmd_audit)
    r.set_defaults(func=cmd_repair)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
