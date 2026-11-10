"""Stage 2: trajectory-grounded error analysis (the agentic error analyst).

Two calls per failure, with a mechanical gate between them:

  call 1  explain   gold basis + VERBATIM evidence quotes + what the current instruction implies
  gate              every quote must be a contiguous substring of the trajectory (else discard)
  call 2  patch     TRIGGER / RULE / COUNTER-EXAMPLE, bounded by neighbouring train samples

The gate is the cheap version of "inspect the artifact and validate the fix": it stops the
model from inventing a failure mechanism that the text does not support.

If the run being analysed used an instruction that makes the model state its own reasoning
(v4+, see prompts/zero_shot_v4.txt), that reasoning is pulled out of raw_responses.jsonl and
put in the dossier as `model_reasoning`. The analyst then audits what the model actually
reasoned instead of inferring it from the labels — pair it with prompts/analyst_v4_explain.txt.

Usage:
    python src/analyst.py worklist results/_smoke/.../triage/triage.jsonl
    python src/analyst.py run --worklist results/analysis/<name>/worklist.jsonl --limit 5
    python src/analyst.py run --worklist ... --dry-run          # build dossiers, no API call
    python src/analyst.py run --worklist ... \
        --explain-prompt prompts/analyst_v4_explain.txt \
        --patch-prompt prompts/analyst_v4_patch.txt --model <name>
    python src/analyst.py probe --instruction prompts/zero_shot_v1.txt --patch patches/<id>.txt \
        --ids AGENTRISK-235,AGENTRISK-501
"""
import argparse
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openai import OpenAI
from rank_bm25 import BM25Okapi

from common import DOMAINS, DRIVERS, load_jsonl, task_fields
from run import PARAMS, get_client

ROOT = Path(__file__).resolve().parent.parent
EXPLAIN_PROMPT = ROOT / "prompts" / "analyst_v1_explain.txt"
PATCH_PROMPT = ROOT / "prompts" / "analyst_v1_patch.txt"
ROOT_CAUSES = ("label_definition", "evidence_reading", "severity_anchor", "output_schema", "unexplained")


# ---------------------------------------------------------------- helpers
def norm(text):
    return re.sub(r"\s+", " ", text or "").strip()


def quote_in_text(quote, haystack_norm):
    q = norm(quote)
    if len(q) < 12:          # too short to be evidence
        return False
    return q in haystack_norm


def tokenize(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def build_pool(rows, k=3):
    """BM25 over the candidate pool's trajectories, for neighbour guardrails."""
    bm25 = BM25Okapi([tokenize(r["formatted_interaction"]) for r in rows])
    return bm25, rows


def neighbours(bm25, rows, row, k=3):
    scores = bm25.get_scores(tokenize(row["formatted_interaction"]))
    order = sorted(range(len(rows)), key=lambda i: (-scores[i], i))
    return [rows[i] for i in order if rows[i]["example_id"] != row["example_id"]][:k]


def analyst_client(args):
    """The analyst may run on a different model than the one being analysed.

    Default: the same DeepSeek client and params as src/run.py. --base-url or --api-key-env
    builds a separate client; extra_body is dropped there because {"thinking": ...} is a
    DeepSeek extension that other providers reject.
    """
    params = dict(PARAMS)
    if args.model:
        params["model"] = args.model
    params["max_tokens"] = args.max_tokens
    if not (args.base_url or args.api_key_env):
        return get_client(), params
    key_env = args.api_key_env or "DEEPSEEK_API_KEY"
    if not os.environ.get(key_env):
        sys.exit(f"{key_env} is not set; add it to .env and re-export (set -a; . ./.env; set +a)")
    params.pop("extra_body", None)
    client = OpenAI(api_key=os.environ[key_env],
                    base_url=args.base_url or "https://api.deepseek.com",
                    timeout=120.0, max_retries=0)
    return client, params


def load_reasoning(run_dir):
    """example_id -> the rationale the model stated on its successful attempt (v4+ runs).

    predictions.jsonl keeps labels only, so the reasoning is read back from the raw log.
    Returns {} for label-only runs, which leaves the dossier exactly as it was in round one.
    """
    path = run_dir / "raw_responses.jsonl"
    if not path.exists():
        return {}
    out = {}
    for rec in load_jsonl(path):
        if rec.get("status") != "ok":
            continue
        if rec.get("reasoning"):
            out[rec["example_id"]] = rec["reasoning"]
        elif rec.get("facts"):   # facts lineage (docs/agentic-distill/00-common.md section 2)
            out[rec["example_id"]] = {"facts": rec["facts"], "judgment": rec.get("judgment", "")}
    return out


def call_json(client, system, payload, params, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                **params,
            )
            content = resp.choices[0].message.content
            return json.loads(content), resp
        except (json.JSONDecodeError, TypeError, IndexError) as exc:
            if attempt == retries:
                raise
            print(f"    retry after bad response: {exc}", flush=True)
    raise RuntimeError("unreachable")


def why_selected(triage_rec, fields):
    """One line naming the defect, in the fields this task actually predicts."""
    parts = []
    if "risk_severity" in fields and triage_rec.get("severity_delta") is not None:
        parts.append(f"severity delta {triage_rec['severity_delta']:+d}")
    for field, name in (("risk_domains", "domain"), ("risk_drivers", "driver")):
        if field in fields:
            parts.append(f"{name} missing {triage_rec.get(f'{name}_missing')} "
                         f"/ extra {triage_rec.get(f'{name}_extra')}")
    return "; ".join(parts)


def dossier(row, pred, triage_rec, neighbour_rows, reasoning=None, task="multi"):
    """Everything the analyst is allowed to see for one failure.

    reasoning: what the model said about its own decision (v4+). Absent for label-only runs.
    task: restricts gold, prediction and the triage summary to that subtask's fields, so a
    single-task analyst is never shown labels the model was not asked to produce.
    """
    fields = task_fields(task)

    def label_block(r):
        return {f: r[f] for f in fields}

    doss = {
        "task": task,
        "example_id": row["example_id"],
        "trajectory": row["formatted_interaction"],
        "proposed_action": row["proposed_action"],
        "gold": label_block(row),
        "prediction": {f: pred[f] for f in fields},
        "triage": {k: triage_rec[k] for k in
                   ("bucket", "severity_delta", "domain_missing", "domain_extra",
                    "driver_missing", "driver_extra") if k in triage_rec},
        "why_this_sample_was_selected": why_selected(triage_rec, fields),
        "neighbour_guardrails": [
            {"example_id": n["example_id"], "gold": label_block(n),
             "proposed_action": n["proposed_action"][:400]}
            for n in neighbour_rows
        ],
    }
    if reasoning:
        doss["model_reasoning"] = reasoning
    return doss


# ---------------------------------------------------------------- subcommands
def stratified_sample(fails, n, seed=0):
    """Proportional allocation across buckets, deterministic per bucket."""
    import random
    by = {}
    for r in fails:
        by.setdefault(r["bucket"], []).append(r)
    total = len(fails)
    quota = {b: n * len(v) / total for b, v in by.items()}
    alloc = {b: int(q) for b, q in quota.items()}
    # largest remainder, at least 1 per bucket so rare buckets are represented
    for b in by:
        alloc[b] = max(alloc[b], 1) if len(by[b]) >= 1 else 0
    while sum(alloc.values()) > n:
        b = max((b for b in alloc if alloc[b] > 1), key=lambda b: alloc[b] - quota[b])
        alloc[b] -= 1
    while sum(alloc.values()) < n:
        b = max((b for b in by if alloc[b] < len(by[b])), key=lambda b: quota[b] - alloc[b])
        alloc[b] += 1
    picked = []
    for b, k in sorted(alloc.items()):
        if k:
            picked += random.Random(f"{seed}:{b}").sample(by[b], k)
    return picked, alloc


def cmd_worklist(args):
    recs = load_jsonl(Path(args.triage))
    fails = [r for r in recs if r.get("status") == "scored" and r.get("bucket") != "exact"]
    if args.sample:
        fails, alloc = stratified_sample(fails, min(args.sample, len(fails)), args.seed)
        print("stratified allocation: " + ", ".join(f"{b}={k}" for b, k in sorted(alloc.items())))
        default_name = f"worklist_sample{args.sample}.jsonl"
    else:
        default_name = "worklist.jsonl"
    out = Path(args.out) if args.out else Path(args.triage).parent.parent / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in fails:
            item = {"example_id": r["example_id"], "bucket": r["bucket"]}
            if "severity_delta" in r:
                item["severity_delta"] = r["severity_delta"]
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    by = {}
    for r in fails:
        by[r["bucket"]] = by.get(r["bucket"], 0) + 1
    print(f"{len(fails)} failures -> {out}")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {v}")


def cmd_run(args):
    triage_dir = Path(args.triage).parent
    run_dir = triage_dir.parent
    config = json.loads((run_dir / "config.json").read_text())
    task = config.get("task", "multi")   # runs predating single-task support are joint
    if getattr(args, "task", None) and args.task != task:
        sys.exit(f"--task {args.task} but {run_dir}/config.json says task={task}")
    data_path = ROOT / config["data_file"]
    rows = {r["example_id"]: r for r in load_jsonl(data_path)}
    triage = {r["example_id"]: r for r in load_jsonl(Path(args.triage))}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}
    reasoning = load_reasoning(run_dir)

    pool_path = Path(args.pool) if args.pool else data_path
    pool = load_jsonl(pool_path)
    bm25, pool_rows = build_pool(pool)

    worklist = load_jsonl(Path(args.worklist))
    out_dir = (Path(args.out_dir) if args.out_dir
               else ROOT / "results" / "analysis" / ("multitask" if task == "multi" else task)
               / run_dir.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    lessons_path = out_dir / "lessons.jsonl"
    done = set()
    if lessons_path.exists():
        done = {json.loads(l)["example_id"] for l in lessons_path.read_text().splitlines() if l.strip()}

    instruction = (ROOT / config["prompt_file"]).read_text(encoding="utf-8")
    explain_sys = (ROOT / args.explain_prompt).read_text(encoding="utf-8")
    patch_sys = (ROOT / args.patch_prompt).read_text(encoding="utf-8")
    todo = [w for w in worklist if w["example_id"] not in done][: args.limit]
    print(f"{len(done)} already analysed, {len(todo)} to do -> {lessons_path}", flush=True)
    covered = sum(1 for w in todo if reasoning.get(w["example_id"]))
    print(f"task: {task}; stated reasoning available for {covered}/{len(todo)} of them "
          f"(run prompt: {config['prompt_file']}); explain prompt: {args.explain_prompt}",
          flush=True)

    client, params = (None, None) if args.dry_run else analyst_client(args)
    if client is not None:
        print(f"analyst model: {params['model']} (max_tokens {params['max_tokens']}) "
              f"at concurrency {args.concurrency}", flush=True)
    counts = {"kept": 0, "discarded": 0}
    lock = threading.Lock()

    def analyse(i, item):
        eid = item["example_id"]
        row, pred, tri = rows[eid], preds[eid], triage[eid]
        doss = dossier(row, pred, tri, neighbours(bm25, pool_rows, row, args.neighbours),
                       reasoning.get(eid), task)

        if args.dry_run:
            said = doss.get("model_reasoning")
            print(f"[{i}/{len(todo)}] {eid} {tri['bucket']} | dossier {len(json.dumps(doss))} chars"
                  f" | model_reasoning: {norm(said)[:160] + '…' if said else 'ABSENT'}")
            if i == 1:
                print(json.dumps(doss, ensure_ascii=False)[:800])
            return

        payload = dict(doss, instruction=instruction)
        explain, _ = call_json(client, explain_sys, payload, params)
        quotes = explain.get("evidence") or []
        hay = norm(row["formatted_interaction"] + "\n" + row["proposed_action"])
        ok_quotes = [q for q in quotes if quote_in_text(q, hay)]
        bad_quotes = [q for q in quotes if q not in ok_quotes]
        root_cause_type = explain.get("root_cause_type")

        record = {"example_id": eid, "bucket": tri["bucket"], "gold": doss["gold"],
                  "prediction": doss["prediction"],
                  "model_reasoning": doss.get("model_reasoning"), "explain": explain,
                  "quotes_ok": ok_quotes, "quotes_rejected": bad_quotes,
                  "root_cause_type": root_cause_type,
                  "reasoning_fault": explain.get("reasoning_fault"),
                  "patch": None, "status": None}

        if root_cause_type not in ROOT_CAUSES:
            record["status"] = "discarded:bad_root_cause_type"
        elif not ok_quotes:
            record["status"] = "discarded:no_verbatim_evidence"
        else:
            patch, _ = call_json(client, patch_sys, {
                "instruction": instruction, "diagnosis": explain,
                "neighbour_guardrails": doss["neighbour_guardrails"],
            }, params)
            record["patch"] = patch
            if not patch.get("patch_text"):
                record["status"] = "discarded:patch_refused"
            else:
                record["status"] = "kept"

        with lock:   # one writer at a time: lessons.jsonl must stay one JSON object per line
            counts["kept" if record["status"] == "kept" else "discarded"] += 1
            with lessons_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(todo)}] {eid} {record['status']} "
              f"quotes {len(ok_quotes)}/{len(quotes)} cause={root_cause_type}"
              + (f" fault={record['reasoning_fault']}" if record["reasoning_fault"] else ""),
              flush=True)

    # --dry-run stays sequential so the printed order matches the worklist
    workers = 1 if args.dry_run else args.concurrency
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in [pool.submit(analyse, i, item) for i, item in enumerate(todo, 1)]:
            future.result()   # re-raise anything a worker did not handle

    print(f"kept {counts['kept']}, discarded {counts['discarded']}")


def cmd_probe(args):
    """Apply one patch on top of the instruction and see what flips."""
    instruction = (ROOT / args.instruction).read_text(encoding="utf-8")
    patch = Path(args.patch).read_text(encoding="utf-8")
    system = instruction.rstrip() + "\n\n" + patch.strip() + "\n"
    ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    data_path = ROOT / args.data
    rows = {r["example_id"]: r for r in load_jsonl(data_path)}
    client = get_client()
    flips, breaks = [], []
    for eid in ids:
        row = rows[eid]
        got, _ = call_json(client, system, {"formatted_interaction": row["formatted_interaction"],
                                            "proposed_action": row["proposed_action"]}, PARAMS)
        before = {"risk_severity": row.get("_pred_severity"), "risk_domains": row.get("_pred_domains")}
        gold_sev = row["risk_severity"]
        ok_before = None
        ok_after = got.get("risk_severity") == gold_sev
        print(f"{eid}: gold sev {gold_sev} -> patch sev {got.get('risk_severity')} "
              f"{'FIXED' if ok_after else 'still wrong'}; domains {got.get('risk_domains')} "
              f"drivers {got.get('risk_drivers')}")
        (flips if ok_after else breaks).append(eid)
    print(f"\nfixed {len(flips)}/{len(ids)}: {flips}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)

    w = sub.add_parser("worklist", help="failures from a triage.jsonl")
    w.add_argument("triage")
    w.add_argument("--out", default=None)
    w.add_argument("--sample", type=int, default=None, help="stratified subsample size")
    w.add_argument("--seed", type=int, default=0)
    w.set_defaults(func=cmd_worklist)

    r = sub.add_parser("run", help="explain + patch every failure in a worklist")
    r.add_argument("--task", default=None,
                   help="optional: assert the run is this task (the task is read from config.json)")
    r.add_argument("--triage", required=True, help="<run_dir>/triage/triage.jsonl")
    r.add_argument("--worklist", required=True)
    r.add_argument("--out-dir", default=None)
    r.add_argument("--pool", default=None, help="candidate rows for neighbour guardrails (default: the run's data file)")
    r.add_argument("--neighbours", type=int, default=3)
    r.add_argument("--limit", type=int, default=None)
    r.add_argument("--concurrency", type=int, default=1, help="failures analysed at once")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--explain-prompt", default=str(EXPLAIN_PROMPT.relative_to(ROOT)),
                   help="use prompts/analyst_v4_explain.txt for runs that state their reasoning")
    r.add_argument("--patch-prompt", default=str(PATCH_PROMPT.relative_to(ROOT)))
    r.add_argument("--model", default=None, help=f"analyst model (default: {PARAMS['model']})")
    r.add_argument("--base-url", default=None, help="OpenAI-compatible endpoint for --model")
    r.add_argument("--api-key-env", default=None,
                   help="env var holding the key for --base-url (default: DEEPSEEK_API_KEY)")
    r.add_argument("--max-tokens", type=int, default=2048,
                   help="the v4 explain schema is longer than v1's; 1024 can truncate it")
    r.set_defaults(func=cmd_run)

    p = sub.add_parser("probe", help="run one patch text over some ids")
    p.add_argument("--instruction", default="prompts/zero_shot_v1.txt")
    p.add_argument("--patch", required=True)
    p.add_argument("--ids", required=True)
    p.add_argument("--data", default="data/splits/train_evolve.jsonl",
                   help="never tune on dev; dev is the frozen final test")
    p.set_defaults(func=cmd_probe)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
