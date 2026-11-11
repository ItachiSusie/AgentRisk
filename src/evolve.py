"""Evolve: improve one single-task zero-shot instruction by small, out-of-fold-gated edits.

Design: docs/evolve/spec.md (algorithm, parameters, layout); success criteria: docs/evolve/eval.md.
Only train_evolve is used, through its 5 scenario-group folds; train_val and dev never enter.

Usage:
    python src/evolve.py init     --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt \
                                  [--seed <extra seed>] [--param name=value ...] [--limit-per-fold N]
    python src/evolve.py baseline --run-dir <dir>         # seeds on all items + noise repeat -> tau
    python src/evolve.py step     --run-dir <dir> [--rounds N]
    python src/evolve.py status   --run-dir <dir>         # champion, rounds, tokens, gates, process metrics
    python src/evolve.py export   --run-dir <dir> --version reason-v5

Global flags: --concurrency N, --limit-per-fold N (pilot), --dry-run (fake predictor and proposer,
no API call; the run goes to results/_smoke/evolve/). --limit-per-fold and --dry-run are fixed at
init and recorded in config.json; every later command reads them from there.

Everything is resumable: each API result is on disk (cache/) before it is used, and a round's
files (rounds/round_XX/*.json) are reused when the step is re-run.
"""
import argparse
import difflib
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyst import build_pool, neighbours, quote_in_text, stratified_sample  # noqa: E402
from assemble_instruction import ANCHORS  # noqa: E402
from common import DOMAINS, DRIVERS, load_jsonl, unpack_prediction  # noqa: E402
from paired_bootstrap import bootstrap, per_sample  # noqa: E402
from triage import confusion_pairs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROMPTS_ROOT = ROOT / "prompts"
FOLDS_FILE = ROOT / "data" / "splits" / "train_evolve_folds.json"
TRAIN_FILE = ROOT / "data" / "raw" / "train.jsonl"
TRAIN_VAL_FILE = ROOT / "data" / "splits" / "train_val.json"
BLIND_PROMPT = PROMPTS_ROOT / "evolve" / "proposer_blind_v1.txt"
EDIT_PROMPT = PROMPTS_ROOT / "evolve" / "proposer_edit_v1.txt"

FIELD = {"task1": "risk_severity", "task2a": "risk_domains", "task2b": "risk_drivers"}
METRIC = {"task1": "mae", "task2a": "domain", "task2b": "driver"}
LABELS = {"task2a": DOMAINS, "task2b": DRIVERS}
# Invalid outputs (after MAX_ATTEMPTS) are scored with the worst loss for gating (spec 4.7).
WORST_LOSS = {"task1": 4.0, "task2a": 1.0, "task2b": 1.0}
LINEAGE_FORMATS = {"answer": "labels", "reason": "reasoning-answer-v1",
                   "facts": "facts-judgment-answer-v1"}
SEED_NAME_RE = re.compile(r"zero_shot_(answer|reason|facts)_v\d+\.txt$")
VERSION_RE = re.compile(r"^(answer|reason|facts)-v\d+$")
ID_RE = re.compile(r"AGENTRISK-\d+")
EDIT_TYPES = ("definition", "pre_check", "conditional", "delete")
OPS = ("replace", "insert_after", "delete")
FAULTS = ("misread_evidence", "missed_evidence", "wrong_rule", "sound_but_wrong")
MAX_ATTEMPTS = 3   # same retry budget as src/run.py

# spec section 5; every value is written to config.json, changing one means a new run
DEFAULTS = {
    "max_rounds": 8, "max_patience": 2, "n_candidates": 4, "m_wrong": 8, "m_right": 8,
    "min_wrong": 4, "quick_n": 40, "quick_max_rw": 2, "max_full": 2, "min_net": 5,
    "p_better": 0.9, "max_rw_frac": 0.03, "max_gold1_loss": 2, "max_edit_words": 60,
    "max_growth_words": 150, "proposer_temperature": 0.7, "budget_tokens": 30_000_000,
    "bootstrap_iterations": 3000, "g3_sev_shift": 0.05, "g3_count_shift": 0.1,
    "g3_min_level_n": 10, "g5_min_folds": 3,
    # not in the spec table, needed to make the spec concrete (see docs/evolve/implementation.md)
    "traj_chars": 6000,        # trajectories longer than this keep their end (the proposed action)
    "copy_ngram": 4,           # check 4.5.5: word n-gram copied from a batch trajectory
    "proposer_max_tokens": 8192,
    "placebo": 0,              # eval.md 5.2: 1 permutes the gold shown to the proposer in call 2
    "noise_share": 0.5,        # a round is label noise if > this share of wrong items is sound_but_wrong
    "predictor_batch": 64,     # requests between two budget checks
}


class DataRoleError(AssertionError):
    """An id outside the proposing fold reached the proposer, or a held-out split leaked in."""


class BudgetExhausted(RuntimeError):
    pass


class ApiUnavailable(RuntimeError):
    """Items failed every attempt with API errors; they are not cached and the step stops."""


# ---------------------------------------------------------------- small helpers
def now():
    return datetime.now(timezone.utc).isoformat()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()


def words(text):
    return (text or "").split()


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, obj):
    """Atomic: a killed process never leaves a half-written file behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def git_sha():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src", "prompts/evolve"],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def truncate_keep_end(text, max_chars):
    """Long trajectories keep their end, which holds the proposed action."""
    if max_chars is None or len(text) <= max_chars:
        return text
    return "[...]" + text[-max_chars:]


def coerce(value, default):
    if isinstance(default, bool):
        return value.lower() in ("1", "true", "yes")
    if isinstance(default, int):
        return int(float(value))
    if isinstance(default, float):
        return float(value)
    return value


def parse_params(pairs):
    params = dict(DEFAULTS)
    for pair in pairs or []:
        if "=" not in pair:
            sys.exit(f"--param expects name=value, got {pair!r}")
        name, value = pair.split("=", 1)
        if name not in DEFAULTS:
            sys.exit(f"unknown parameter {name!r}; known: {', '.join(DEFAULTS)}")
        params[name] = coerce(value, DEFAULTS[name])
    return params


# ---------------------------------------------------------------- prompt structure
def split_tail(prompt):
    """(head, output-format tail). The tail starts at the earliest assemble_instruction.ANCHORS hit."""
    found = sorted((prompt.index(a), a) for a in ANCHORS if a in prompt)
    if not found:
        raise ValueError(f"no output-format anchor found; tried {ANCHORS}")
    i = found[0][0]
    return prompt[:i], prompt[i:]


def protected_strings(task, seed_text):
    """Text that must survive every edit byte for byte (spec 4.5 check 3)."""
    if task == "task1":
        # severity level names, e.g. "3 Moderate:" at the start of a scale line
        found = re.findall(r"^\s*([1-5] [A-Z][A-Za-z]+:)", seed_text, flags=re.M)
        if len(found) != 5:
            raise ValueError(f"task1 seed must list 5 severity levels, found {found}")
        return found
    return list(LABELS[task])


def label_lines(task, text):
    """Lines that are exactly one label name (the label list of a task 2 prompt)."""
    if task == "task1":
        return []
    names = set(LABELS[task])
    return [ln for ln in text.splitlines() if ln.strip() in names]


def apply_edit(prompt, edit):
    """Return the candidate text. Raises ValueError with the reason when the edit cannot apply."""
    anchor, op, new_text = edit.get("anchor") or "", edit.get("op"), edit.get("new_text") or ""
    if not all(isinstance(value, str) for value in (anchor, op, new_text)):
        raise ValueError("anchor, op and new_text must be strings")
    if op not in OPS:
        raise ValueError(f"unknown op {op!r}")
    if not anchor.strip():
        raise ValueError("empty anchor")
    count = prompt.count(anchor)
    if count != 1:
        raise ValueError(f"anchor occurs {count} times (must be exactly once)")
    i = prompt.index(anchor)
    j = i + len(anchor)
    if op == "replace":
        if not new_text.strip():
            raise ValueError("replace with empty new_text (use op delete)")
        return prompt[:i] + new_text + prompt[j:]
    if op == "delete":
        if new_text.strip():
            raise ValueError("delete must have empty new_text")
        whole_line = (i == 0 or prompt[i - 1] == "\n") and (j == len(prompt) or prompt[j] == "\n")
        if whole_line and j < len(prompt):
            j += 1   # a deleted line takes its line break with it
        out = prompt[:i] + prompt[j:]
        return re.sub(r"\n{3,}", "\n\n", out)
    if not new_text.strip():
        raise ValueError("insert_after with empty new_text")
    at_line_end = j == len(prompt) or prompt[j] == "\n"
    sep = "\n" if at_line_end else " "
    return prompt[:j] + sep + new_text.strip() + prompt[j:]


def ngrams(tokens, n):
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def lower_tokens(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def validate_edit(edit, champion, seed_text, task, batch_rows, tried_norms, params):
    """Spec 4.5: returns (candidate_text, None) or (None, reason)."""
    try:
        cand = apply_edit(champion, edit)
    except ValueError as e:
        return None, f"apply: {e}"
    # 2. quotes are verbatim and cite >= 2 distinct batch items
    by_id = {r["example_id"]: r for r in batch_rows}
    fixes = edit.get("fixes") or []
    if not isinstance(fixes, list):
        return None, "fixes must be a list"
    cited = set()
    for fx in fixes:
        if not isinstance(fx, dict):
            return None, "fixes entries must be objects"
        eid, quote = fx.get("example_id"), fx.get("quote")
        if not isinstance(eid, str) or not isinstance(quote, str):
            return None, "fixes example_id and quote must be strings"
        if eid not in by_id:
            return None, f"fixes cites {eid!r}, not a batch item"
        row = by_id[eid]
        hay = norm_ws(row["formatted_interaction"] + "\n" + row["proposed_action"])
        if not quote_in_text(quote, hay):
            return None, f"quote for {eid} is not verbatim trajectory text"
        cited.add(eid)
    if len(cited) < 2:
        return None, f"fixes cites {len(cited)} distinct item(s), needs >= 2"
    # 3. protected text survives: label / level names and the output-format tail
    for s in protected_strings(task, seed_text):
        if s not in cand:
            return None, f"protected text removed: {s!r}"
    missing_lines = [ln for ln in label_lines(task, champion) if ln not in cand.splitlines()]
    if missing_lines:
        return None, f"label line changed: {missing_lines[0].strip()!r}"
    try:
        if split_tail(cand)[1] != split_tail(champion)[1]:
            return None, "output-format tail changed"
    except ValueError:
        return None, "output-format anchor removed"
    # 4. size
    new_text = edit.get("new_text") or ""
    if len(words(new_text)) > params["max_edit_words"]:
        return None, f"new_text has {len(words(new_text))} words > {params['max_edit_words']}"
    if len(words(cand)) > len(words(seed_text)) + params["max_growth_words"]:
        return None, (f"candidate has {len(words(cand))} words > seed {len(words(seed_text))}"
                      f" + {params['max_growth_words']}")
    # 5. nothing copied from the batch, no ids. n-grams already in the champion prompt are not
    # "copied from the batch" (an edit may reuse the prompt's own wording).
    if ID_RE.search(new_text):
        return None, "new_text contains an example id"
    n = params["copy_ngram"]
    new_grams = ngrams(lower_tokens(new_text), n) - ngrams(lower_tokens(champion), n)
    if new_grams:
        for row in batch_rows:
            traj = ngrams(lower_tokens(row["formatted_interaction"] + " " + row["proposed_action"]), n)
            hit = new_grams & traj
            if hit:
                return None, f"new_text copies {' '.join(sorted(hit)[0])!r} from {row['example_id']}"
    # 6. not a prompt already tried in this run
    if norm_ws(cand) in tried_norms:
        return None, "identical to a prompt already tried"
    return cand, None


def word_diff(a, b):
    """Words not shared in order between two texts (both sides counted)."""
    wa, wb = words(a), words(b)
    matched = sum(m.size for m in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_matching_blocks())
    return len(wa) + len(wb) - 2 * matched


# ---------------------------------------------------------------- data
def load_data(limit_per_fold=None, check_folds=True):
    """Rows of train_evolve and the fold lists. Refuses to start on a drifted folds file."""
    folds_doc = json.loads(FOLDS_FILE.read_text())
    if check_folds:
        import make_folds
        payload, _, _ = make_folds.build(folds_doc["k"])
        if [f["example_ids"] for f in payload["folds"]] != [f["example_ids"] for f in folds_doc["folds"]]:
            sys.exit("data/splits/train_evolve_folds.json fails make_folds.py --check; refusing to start")
    folds = [list(f["example_ids"]) for f in folds_doc["folds"]]
    if limit_per_fold:
        folds = [ids[:limit_per_fold] for ids in folds]
    all_ids = [i for ids in folds for i in ids]
    if len(set(all_ids)) != len(all_ids):
        raise DataRoleError("an id appears in two folds")
    held = set()
    if TRAIN_VAL_FILE.exists():
        held |= set(json.loads(TRAIN_VAL_FILE.read_text())["example_ids"])
    if held & set(all_ids):
        raise DataRoleError("train_val ids inside train_evolve folds")
    train = {r["example_id"]: r for r in load_jsonl(TRAIN_FILE)}
    rows = {i: train[i] for i in all_ids}
    return rows, folds, folds_doc


def assert_ids_in_fold(payload, fold_ids):
    """Spec 3: no proposer payload may contain an id outside F_k."""
    found = set(ID_RE.findall(json.dumps(payload, ensure_ascii=False)))
    outside = found - set(fold_ids)
    if outside:
        raise DataRoleError(f"proposer payload contains ids outside the proposing fold: {sorted(outside)[:5]}")


# ---------------------------------------------------------------- losses and the flip ledger
def item_loss(task, gold_row, rec):
    if rec is None or rec.get("status") != "ok":
        return WORST_LOSS[task]
    eid = gold_row["example_id"]
    pred = {eid: {FIELD[task]: rec["labels"][FIELD[task]]}}
    return per_sample({eid: gold_row}, pred, [eid], METRIC[task], task)[0]


def losses(task, rows, preds, ids):
    return [item_loss(task, rows[i], preds.get(i)) for i in ids]


def ledger(base, cand):
    """Flip ledger between two loss vectors on the same items (spec section 2)."""
    improved = sum(c < b for b, c in zip(base, cand))
    worsened = sum(c > b for b, c in zip(base, cand))
    return {
        "n": len(base),
        "improved": improved,
        "worsened": worsened,
        "net": improved - worsened,
        "right_to_wrong": sum(b == 0 and c > 0 for b, c in zip(base, cand)),
        "wrong_to_right": sum(b > 0 and c == 0 for b, c in zip(base, cand)),
        "base_correct": sum(b == 0 for b in base),
        "base_mean": sum(base) / len(base) if base else 0.0,
        "cand_mean": sum(cand) / len(cand) if cand else 0.0,
    }


def pred_value(task, rec):
    if rec is None or rec.get("status") != "ok":
        return None
    return rec["labels"][FIELD[task]]


def label_fp_fn(task, rows, preds, ids):
    stats = {lbl: {"fp": 0, "fn": 0} for lbl in LABELS[task]}
    for i in ids:
        gold = set(rows[i][FIELD[task]])
        pred = set(pred_value(task, preds.get(i)) or [])
        for lbl in pred - gold:
            stats[lbl]["fp"] += 1
        for lbl in gold - pred:
            stats[lbl]["fn"] += 1
    return stats


def mean_signed_error_by_level(rows, preds, ids):
    out = {}
    for lvl in range(1, 6):
        errs = [preds[i]["labels"]["risk_severity"] - lvl for i in ids
                if rows[i]["risk_severity"] == lvl and preds.get(i, {}).get("status") == "ok"]
        out[lvl] = {"n": sum(rows[i]["risk_severity"] == lvl for i in ids),
                    "mse": (sum(errs) / len(errs)) if errs else 0.0}
    return out


def full_gate_metrics(task, rows, champ, cand, ids, fold_of, params, tau_scaled):
    """Spec 4.7: every gate on the evaluation folds. Returns (passed, metrics)."""
    base = losses(task, rows, champ, ids)
    new = losses(task, rows, cand, ids)
    led = ledger(base, new)
    diffs = [c - b for b, c in zip(base, new)]
    obs, lo, hi, p_better = bootstrap(diffs, params["bootstrap_iterations"], seed=0)
    gates = {}
    need = max(params["min_net"], 2 * tau_scaled)
    gates["G1_gain"] = {"pass": led["net"] >= need and p_better >= params["p_better"],
                        "net": led["net"], "need_net": need, "p_better": p_better,
                        "diff": obs, "ci": [lo, hi]}
    rw_cap = params["max_rw_frac"] * led["base_correct"]
    g2 = {"right_to_wrong": led["right_to_wrong"], "cap": rw_cap,
          "pass": led["right_to_wrong"] <= rw_cap}
    if task == "task1":
        gold1_lost = sum(1 for i, b, c in zip(ids, base, new)
                         if rows[i]["risk_severity"] == 1 and b == 0 and c > 0)
        g2["gold1_lost"] = gold1_lost
        g2["pass"] = g2["pass"] and gold1_lost <= params["max_gold1_loss"]
    gates["G2_no_damage"] = g2
    if task == "task1":
        b_lv = mean_signed_error_by_level(rows, champ, ids)
        c_lv = mean_signed_error_by_level(rows, cand, ids)
        grown = {lvl: round(abs(c_lv[lvl]["mse"]) - abs(b_lv[lvl]["mse"]), 4) for lvl in b_lv
                 if b_lv[lvl]["n"] >= params["g3_min_level_n"]
                 and abs(c_lv[lvl]["mse"]) - abs(b_lv[lvl]["mse"]) > params["g3_sev_shift"]}
        gates["G3_no_shift"] = {"pass": not grown, "levels_grown": grown,
                                "champion": b_lv, "candidate": c_lv}
    else:
        def mean_count(preds):
            return sum(len(pred_value(task, preds.get(i)) or []) for i in ids) / len(ids)
        cb, cc = mean_count(champ), mean_count(cand)
        sb, sc = label_fp_fn(task, rows, champ, ids), label_fp_fn(task, rows, cand, ids)
        swaps = [lbl for lbl in sb
                 if sc[lbl]["fp"] < sb[lbl]["fp"] and sc[lbl]["fn"] > sb[lbl]["fn"]
                 and sc[lbl]["fp"] + sc[lbl]["fn"] >= sb[lbl]["fp"] + sb[lbl]["fn"]]
        gates["G3_no_shift"] = {"pass": abs(cc - cb) <= params["g3_count_shift"] and not swaps,
                                "mean_count": [cb, cc], "swapped_labels": swaps,
                                "fp_fn_champion": sb, "fp_fn_candidate": sc}
    gates["G4_size"] = {"pass": True, "note": "enforced by validate_edit"}
    per_fold = {}
    for f in sorted({fold_of[i] for i in ids}):
        d = [x for i, x in zip(ids, diffs) if fold_of[i] == f]
        per_fold[f] = sum(d) / len(d)
    agree = sum(v < 0 for v in per_fold.values())
    gates["G5_stability"] = {"pass": agree >= min(params["g5_min_folds"], len(per_fold)),
                             "folds_better": agree, "per_fold_diff": per_fold}
    inv_b = sum(1 for i in ids if champ.get(i, {}).get("status") != "ok")
    inv_c = sum(1 for i in ids if cand.get(i, {}).get("status") != "ok")
    gates["G6_validity"] = {"pass": inv_c <= inv_b, "invalid": [inv_b, inv_c]}
    passed = all(g["pass"] for g in gates.values())
    return passed, {"ledger": led, "gates": gates}


# ---------------------------------------------------------------- target selection and batch
def cell_key(cell):
    return json.dumps(cell, ensure_ascii=False)


def wrong_cells(task, rows, preds, ids):
    """cell -> list of wrong ids, with the spec 4.1 cost. Invalid predictions are not targeted."""
    cells = {}
    for i in ids:
        rec = preds.get(i)
        if rec is None or rec.get("status") != "ok":
            continue
        gold, pred = rows[i][FIELD[task]], pred_value(task, rec)
        if task == "task1":
            if gold != pred:
                cells.setdefault((gold, pred), []).append(i)
            continue
        g, p = set(gold), set(pred)
        if g == p:
            continue
        missing, extra = g - p, p - g
        # same counting as triage.confusion_pairs, kept per item so the cell knows its items
        assert dict(confusion_pairs([(g, p)], top=None)) == {(a, b): 1 for a in missing for b in extra}
        for a in missing:
            for b in extra:
                cells.setdefault((a, b), []).append(i)
        if missing and not extra:
            for a in missing:
                cells.setdefault((a, None), []).append(i)
        if extra and not missing:
            for b in extra:
                cells.setdefault((None, b), []).append(i)
    out = []
    for cell, items in cells.items():
        cost = len(items) * abs(cell[0] - cell[1]) if task == "task1" else len(items)
        out.append({"cell": list(cell), "items": sorted(items), "count": len(items), "cost": cost})
    out.sort(key=lambda c: (-c["cost"], -c["count"], cell_key(c["cell"])))
    return out


def cell_blocked(history, key):
    outcomes = history.get(key, [])
    return "label_noise" in outcomes or outcomes[-2:] == ["failed", "failed"]


def pick_target(task, rows, preds, fold_ids, min_wrong, history):
    ranking = wrong_cells(task, rows, preds, fold_ids)
    for c in ranking:
        if c["count"] < min_wrong:
            continue
        if cell_blocked(history, cell_key(c["cell"])):
            continue
        return c, ranking
    return None, ranking


def on_boundary(task, gold, cell):
    a, b = cell
    if task == "task1":
        return gold in (a, b)
    return any(x is not None and x in gold for x in (a, b))


def describe_cell(task, cell):
    a, b = cell
    if task == "task1":
        return f"gold severity {a} predicted as {b}"
    if a is None:
        return f"extra label {b!r} predicted where gold does not have it"
    if b is None:
        return f"gold label {a!r} missing (no wrong label added)"
    return f"gold label {a!r} missing while {b!r} was predicted instead"


def blind_boundary(task, cell):
    """Call 1 sees the boundary as two-sided and unordered: no hint of which side is gold."""
    a, b = cell
    if task == "task1":
        lo, hi = sorted((a, b))
        return {"description": f"risk_severity {lo} vs {hi}", "options": [lo, hi]}
    labels = sorted(x for x in (a, b) if x is not None)
    if len(labels) == 1:
        return {"description": f"whether the label {labels[0]!r} applies", "options": labels}
    return {"description": f"{labels[0]!r} vs {labels[1]!r} (either, both or neither may apply)",
            "options": labels}


def sanitize_blind(blind, batch_ids):
    """Drop blind-audit items whose id is not in the batch and mask stray ids, so a typo by the
    proposer cannot trip the data-role assertion forever on replay. Returns (clean, dropped)."""
    allowed = set(batch_ids)
    dropped = []
    items = blind.get("items") if isinstance(blind, dict) else None
    clean = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or it.get("example_id") not in batch_ids:
            dropped.append(it.get("example_id") if isinstance(it, dict) else repr(it)[:80])
            continue
        text = json.dumps(it, ensure_ascii=False)
        stray = set(ID_RE.findall(text)) - allowed
        for sid in stray:
            text = text.replace(sid, "[id]")
            dropped.append(f"mention:{sid}")
        clean.append(json.loads(text))
    return {"items": clean}, dropped


def contrast_batch(task, rows, preds, fold_ids, target, t, params):
    rng = random.Random(f"batch:{t}")
    wrong = list(target["items"])
    rng.shuffle(wrong)
    wrong = sorted(wrong[: params["m_wrong"]])
    fold_set = set(fold_ids)
    pool = [rows[i] for i in fold_ids
            if i not in wrong and preds.get(i, {}).get("status") == "ok"
            and item_loss(task, rows[i], preds[i]) == 0
            and on_boundary(task, rows[i][FIELD[task]], target["cell"])]
    right = []
    if pool:
        bm25, pool_rows = build_pool(pool)
        ranked = [neighbours(bm25, pool_rows, rows[w], k=len(pool_rows)) for w in wrong]
        depth = 0
        while len(right) < min(params["m_right"], len(pool)) and depth < len(pool):
            for lst in ranked:
                if depth < len(lst) and lst[depth]["example_id"] not in right:
                    right.append(lst[depth]["example_id"])
                    if len(right) >= params["m_right"]:
                        break
            depth += 1
    order = wrong + right
    rng.shuffle(order)
    for i in order:
        if i not in fold_set:
            raise DataRoleError(f"{i} is not in the proposing fold")
    return {"wrong": wrong, "right": right, "order": order}


def batch_item(task, row, rec, params):
    return {
        "example_id": row["example_id"],
        "trajectory": truncate_keep_end(row["formatted_interaction"], params["traj_chars"]),
        "proposed_action": row["proposed_action"],
        "prediction": pred_value(task, rec),
        "reasoning": rec.get("reasoning") if rec else None,
    }


def quick_set(task, rows, eval_ids, cell, t, n):
    rng = random.Random(f"quick:{t}")
    boundary = sorted(i for i in eval_ids if on_boundary(task, rows[i][FIELD[task]], cell))
    rng.shuffle(boundary)
    take = boundary[: n // 2]
    taken = set(take)
    rest = [i for i in eval_ids if i not in taken]

    def stratum(i):
        gold = rows[i][FIELD[task]]
        return str(gold) if task == "task1" else sorted(gold)[0]
    need = min(n - len(take), len(rest))
    if need > 0:
        recs = [{"example_id": i, "bucket": stratum(i)} for i in rest]
        if need >= len({r["bucket"] for r in recs}):
            picked, _ = stratified_sample(recs, need, seed=f"quick:{t}")
        else:   # fewer slots than strata: analyst.stratified_sample needs one slot per stratum
            picked = rng.sample(recs, need)
        take += [r["example_id"] for r in picked]
    return sorted(take)


# ---------------------------------------------------------------- model calls (real and fake)
def real_predict(text, row, output_format, task, replica):
    import run
    response = run.request(run.zero_shot_messages(row, text))
    usage = response.usage
    try:
        out = run.parse(response)
    except ValueError as e:   # truncated / empty / non-JSON: an invalid output, not an API error
        out = {"_unparsable": response.choices[0].message.content,
               "finish_reason": response.choices[0].finish_reason, "error": repr(e)}
    return out, {"prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                                 "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                                 "model": response.model}


def fake_predict(text, row, output_format, task, replica):
    """Deterministic stand-in: right ~70% of the time, varies with the prompt text and replica."""
    h = int(hashlib.sha256(f"{sha256_text(text)}|{row['example_id']}|{replica}".encode()).hexdigest(), 16)
    g = int(hashlib.sha256(f"{row['example_id']}|{replica}".encode()).hexdigest(), 16)
    right = (h % 100) < 60 + (g % 20)
    gold = row[FIELD[task]]
    if task == "task1":
        value = gold if right else max(1, min(5, gold + (1 if h % 2 else -1)))
    else:
        value = list(gold) if right else [LABELS[task][h % (len(LABELS[task]) - 1)]]
    answer = {FIELD[task]: value}
    if output_format == "labels":
        out = answer
    elif output_format == "reasoning-answer-v1":
        out = {"reasoning": f"fake reasoning for {row['example_id']}", "answer": answer}
    else:
        out = {"facts": [{"quote": "q1", "note": "n"}, {"quote": "q2", "note": "n"}],
               "judgment": "fake", "answer": answer}
    return out, {"prompt_tokens": len(text) // 4 + len(row["formatted_interaction"]) // 4,
                 "completion_tokens": 50, "model": "fake"}


def real_propose(system, payload, params):
    import run
    from openai import OpenAI  # noqa: F401  (run.get_client builds the client)
    p = dict(run.PARAMS)
    p["temperature"] = params["proposer_temperature"]
    p["max_tokens"] = params["proposer_max_tokens"]
    last = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            resp = run.get_client().chat.completions.create(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                **p)
            content = resp.choices[0].message.content
            if resp.choices[0].finish_reason != "stop" or not content:
                raise ValueError(f"incomplete proposer response ({resp.choices[0].finish_reason})")
            return json.loads(content), {"raw": content, "model": resp.model,
                                         "prompt_tokens": resp.usage.prompt_tokens,
                                         "completion_tokens": resp.usage.completion_tokens,
                                         "attempt": attempt + 1}
        except (ValueError, *run.RETRYABLE) as e:
            last = e
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"proposer failed after {MAX_ATTEMPTS} attempts: {last!r}")


def fake_propose(system, payload, params):
    """Deterministic stand-in proposer: valid JSON of the right shape, for --dry-run and tests."""
    usage = {"raw": None, "model": "fake", "prompt_tokens": len(json.dumps(payload)) // 4,
             "completion_tokens": 200, "attempt": 1}
    items = payload["items"]

    def quote(it):
        text = norm_ws(it["trajectory"].replace("[...]", ""))
        return text[-60:-20] if len(text) > 80 else text[:40]
    if "blind_audit" not in payload:   # call 1
        return {"items": [{"example_id": it["example_id"],
                           "decisive_facts": [{"fact": "fake", "quote": quote(it)}],
                           "reasoning_check": "none", "check_note": "fake",
                           "own_label": it["prediction"]} for it in items]}, usage
    wrong = [it for it in items if it["wrong"]]
    faults = [{"example_id": it["example_id"], "fault": "wrong_rule"} for it in wrong]
    head, _ = split_tail(payload["instruction"])
    lines = [ln for ln in head.splitlines()
             if len(ln.strip()) > 30 and payload["instruction"].count(ln.strip()) == 1]
    # never touch a protected line: label names / severity level names
    lines = [ln for ln in lines if not re.match(r"^\s*[1-5] [A-Z]", ln)
             and ln.strip() not in set(DOMAINS) | set(DRIVERS)]
    salt = int(hashlib.sha256(payload["instruction"].encode()).hexdigest(), 16)
    fixes = [{"example_id": it["example_id"], "quote": quote(it)} for it in wrong[:2]]
    edits = []
    for n, et in enumerate(payload["edit_types"]):
        anchor = lines[(salt + n) % len(lines)].strip() if lines else ""
        zz = f"zq{(salt >> (n * 8)) % 997}"
        new = {"definition": f"Weigh {zz} reversibility explicitly when the boundary is unclear.",
               "pre_check": f"Before choosing, confirm {zz} who authorised the action.",
               "conditional": f"If {zz} consent is explicit choose the lower option, otherwise the higher.",
               "delete": ""}[et]
        edits.append({"edit_type": et, "op": {"delete": "delete", "definition": "replace"}.get(et, "insert_after"),
                      "anchor": anchor, "new_text": new, "rationale": "fake",
                      "fixes": fixes, "must_not_change": []})
    return {"faults": faults, "edits": edits}, usage


# ---------------------------------------------------------------- the run
class Evolver:
    def __init__(self, run_dir, concurrency=8, predict_fn=None, propose_fn=None, log=print):
        self.run_dir = Path(run_dir)
        self.config = read_json(self.run_dir / "config.json")
        if self.config is None:
            sys.exit(f"no config.json in {self.run_dir}; run `evolve.py init` first")
        self.state = read_json(self.run_dir / "state.json")
        self.params = self.config["params"]
        self.task = self.config["task"]
        self.output_format = self.config["output_format"]
        self.concurrency = concurrency
        dry = self.config["dry_run"]
        self.predict_fn = predict_fn or (fake_predict if dry else real_predict)
        self.propose_fn = propose_fn or (fake_propose if dry else real_propose)
        self.log = log
        self.rows, self.folds, _ = load_data(self.config["limit_per_fold"],
                                             check_folds=self.config.get("check_folds", True))
        self.all_ids = [i for f in self.folds for i in f]
        self.fold_of = {i: k for k, f in enumerate(self.folds) for i in f}
        self.cache_dir = self.run_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.cache = {}           # (prompt_sha, replica) -> {eid: record}
        self.request_log = Counter()   # (prompt_sha, replica, eid) -> requests made in this process
        self.api_failures = []

    # ---- state
    def save_state(self):
        write_json(self.run_dir / "state.json", self.state)

    def prompt_text(self, cand_id):
        return (self.run_dir / "prompts" / f"{cand_id}.txt").read_text(encoding="utf-8")

    def register_prompt(self, cand_id, text):
        path = self.run_dir / "prompts" / f"{cand_id}.txt"
        path.parent.mkdir(exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") != text:
            raise RuntimeError(f"{path} exists with different text")
        path.write_text(text, encoding="utf-8")
        self.state["prompts"][cand_id] = sha256_text(text)
        return sha256_text(text)

    def tried_norms(self):
        return {norm_ws(self.prompt_text(c)) for c in self.state["prompts"]}

    # ---- prediction cache
    def policy(self, replica):
        return f"attempts{MAX_ATTEMPTS}|{self.output_format}|replica{replica}"

    def cache_path(self, sha, replica):
        return self.cache_dir / f"pred_{sha[:16]}_r{replica}.jsonl"

    def load_cache(self, sha, replica):
        key = (sha, replica)
        if key not in self.cache:
            path = self.cache_path(sha, replica)
            recs = {}
            if path.exists():
                for r in load_jsonl(path):
                    if r["policy"] == self.policy(replica) and r["prompt_sha"] == sha:
                        recs[r["example_id"]] = r
            self.cache[key] = recs
        return self.cache[key]

    def _predict_one(self, text, sha, row, replica):
        eid = row["example_id"]
        attempts = []
        rec = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            with self.lock:
                self.request_log[(sha, replica, eid)] += 1
            try:
                out, usage = self.predict_fn(text, row, self.output_format, self.task, replica)
            except Exception as e:   # noqa: BLE001  network / API errors: recorded, retried
                attempts.append({"attempt": attempt, "status": "api_error", "error": repr(e)})
                if self.config["dry_run"]:
                    raise
                if type(e).__name__ in ("AuthenticationError", "PermissionDeniedError", "NotFoundError"):
                    raise
                time.sleep(2 ** attempt + random.random())
                continue
            self.add_tokens(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            try:
                labels, reasoning = unpack_prediction(out, self.output_format, self.task)
                rec = {"status": "ok", "labels": labels,
                       "reasoning": reasoning if isinstance(reasoning, str) else
                       (json.dumps(reasoning, ensure_ascii=False) if reasoning else None)}
                attempts.append({"attempt": attempt, "status": "ok", "usage": usage})
                break
            except ValueError as e:
                attempts.append({"attempt": attempt, "status": "invalid_output", "error": repr(e),
                                 "output": out, "usage": usage})
        if rec is None and any(a["status"] == "api_error" for a in attempts):
            # transient failure: never cached, so a rerun retries it (as src/run.py does)
            with self.lock:
                self.api_failures.append(eid)
            return None
        if rec is None:
            rec = {"status": "invalid", "labels": None, "reasoning": None}
        rec.update(example_id=eid, prompt_sha=sha, policy=self.policy(replica),
                   attempts=attempts, time=now())
        with self.lock:
            append_jsonl(self.cache_path(sha, replica), rec)
            self.cache[(sha, replica)][eid] = rec
            write_json(self.run_dir / "state.json", self.state)   # tokens are on disk with the record
        return rec

    def add_tokens(self, n, out=0):
        with self.lock:
            self.state["tokens_used"] = self.state.get("tokens_used", 0) + int(n or 0)
            self.state["output_tokens_used"] = self.state.get("output_tokens_used", 0) + int(out or 0)

    def check_budget(self):
        if self.state.get("tokens_used", 0) >= self.params["budget_tokens"]:
            self.save_state()
            raise BudgetExhausted(f"token budget {self.params['budget_tokens']:,} reached "
                                  f"({self.state['tokens_used']:,} used); run stays resumable")

    def predict(self, cand_id, ids, replica=0):
        """Predictions of a registered prompt on ids; cached by (prompt sha, id, policy)."""
        text = self.prompt_text(cand_id)
        sha = sha256_text(text)
        recs = self.load_cache(sha, replica)
        todo = [i for i in ids if i not in recs]
        bs = self.params["predictor_batch"]
        for start in range(0, len(todo), bs):
            self.check_budget()
            chunk = todo[start:start + bs]
            with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
                for fut in [pool.submit(self._predict_one, text, sha, self.rows[i], replica) for i in chunk]:
                    fut.result()
            self.save_state()
            if self.api_failures:
                failed, self.api_failures = sorted(self.api_failures), []
                self.write_predictions(cand_id, sha, replica)
                raise ApiUnavailable(f"{len(failed)} item(s) exhausted retries with API errors "
                                     f"({failed[:5]}); nothing is gated on them. Rerun the same command.")
        self.write_predictions(cand_id, sha, replica)
        return {i: recs[i] for i in ids}

    def write_predictions(self, cand_id, sha, replica):
        recs = self.load_cache(sha, replica)
        name = cand_id if replica == 0 else f"{cand_id}_repeat{replica}"
        path = self.run_dir / "predictions" / f"{name}.jsonl"
        path.parent.mkdir(exist_ok=True)
        lines = []
        for i in self.all_ids:
            if i in recs:
                r = recs[i]
                lines.append(json.dumps({"example_id": i, "status": r["status"],
                                         **({FIELD[self.task]: r["labels"][FIELD[self.task]]}
                                            if r["status"] == "ok" else {})}, ensure_ascii=False))
        path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def preds_of(self, cand_id, replica=0):
        return self.load_cache(sha256_text(self.prompt_text(cand_id)), replica)

    def mean_loss(self, cand_id, ids):
        preds = self.preds_of(cand_id)
        ls = losses(self.task, self.rows, preds, ids)
        return sum(ls) / len(ls)

    # ---- proposer
    def propose(self, path, system_file, payload, fold_ids):
        """Replays a persisted response if one exists (temperature 0.7 is not reproducible)."""
        saved = read_json(path)
        if saved is not None:
            return saved["parsed"]
        system = Path(system_file).read_text(encoding="utf-8")
        assert_ids_in_fold({"system": system, "payload": payload}, fold_ids)
        self.check_budget()
        parsed, meta = self.propose_fn(system, payload, self.params)
        self.add_tokens(meta.get("prompt_tokens", 0), meta.get("completion_tokens", 0))
        raw = {"meta": {k: v for k, v in meta.items() if k != "raw"}, "parsed": parsed}
        (self.cache_dir / "proposer").mkdir(exist_ok=True)
        (self.cache_dir / "proposer" / (path.parent.name + "_" + path.name)).write_text(
            json.dumps({"payload": payload, "raw": meta.get("raw")}, ensure_ascii=False), encoding="utf-8")
        write_json(path, raw)
        self.save_state()
        return parsed

    # ---- baseline
    def baseline(self):
        if self.state.get("baseline_done"):
            self.log("baseline already done")
            return self.state
        seeds = self.config["seeds"]
        scores = {}
        for s in seeds:
            self.log(f"seed {s['id']}: predicting {len(self.all_ids)} items")
            self.predict(s["id"], self.all_ids)
            scores[s["id"]] = self.mean_loss(s["id"], self.all_ids)
        s0 = seeds[0]["id"]
        self.log(f"seed {s0}: noise repeat on {len(self.all_ids)} items")
        self.predict(s0, self.all_ids, replica=1)
        a, b = self.preds_of(s0, 0), self.preds_of(s0, 1)
        def key(r):
            v = pred_value(self.task, r)
            return (r["status"], v if self.task == "task1" or v is None else tuple(sorted(v)))
        changed = [i for i in self.all_ids if key(a[i]) != key(b[i])]
        la, lb = losses(self.task, self.rows, a, self.all_ids), losses(self.task, self.rows, b, self.all_ids)
        champion = min(scores, key=lambda c: (scores[c], c))
        base = {"seed_mean_loss": scores, "tau": len(changed), "tau_ids": changed,
                "repeat_mean_loss": [sum(la) / len(la), sum(lb) / len(lb)],
                "repeat_ledger": ledger(la, lb), "champion": champion,
                "n_items": len(self.all_ids)}
        write_json(self.run_dir / "baseline.json", base)
        self.state.update(baseline_done=True, champion=champion, tau=len(changed),
                          lineage=[{"round": 0, "champion": champion, "mean_loss": scores[champion]}])
        self.save_state()
        self.log(f"tau = {len(changed)} items changed between two identical runs; "
                 f"champion {champion} mean loss {scores[champion]:.4f}")
        return base

    # ---- one round
    def run_round(self, t):
        p = self.params
        rd = self.run_dir / "rounds" / f"round_{t:02d}"
        rd.mkdir(parents=True, exist_ok=True)
        decision = read_json(rd / "decision.json")
        if decision is not None:
            return decision
        k = t % len(self.folds)
        fold_ids = self.folds[k]
        eval_ids = [i for j, f in enumerate(self.folds) if j != k for i in f]
        champ_id = self.state["champion"]
        champ_text = self.prompt_text(champ_id)
        champ = self.predict(champ_id, self.all_ids)   # all cached in practice

        target = read_json(rd / "target.json")
        if target is None:
            cell, ranking = pick_target(self.task, self.rows, champ, fold_ids, p["min_wrong"],
                                        self.state["cell_history"])
            target = {"round": t, "fold": k, "champion": champ_id, "target": cell,
                      "ranking": ranking[:15]}
            write_json(rd / "target.json", target)
        cell = target["target"]
        base_dec = {"round": t, "fold": k, "champion_before": champ_id,
                    "cell": cell["cell"] if cell else None}
        if cell is None:
            return self.finish_round(rd, dict(base_dec, outcome="skipped", reason="no target cell"))

        batch = read_json(rd / "batch.json")
        if batch is None:
            batch = contrast_batch(self.task, self.rows, champ, fold_ids, cell, t, p)
            write_json(rd / "batch.json", batch)
        items = [batch_item(self.task, self.rows[i], champ[i], p) for i in batch["order"]]
        head, _ = split_tail(champ_text)
        boundary = describe_cell(self.task, cell["cell"])
        blind = self.propose(rd / "proposer_blind.json", BLIND_PROMPT, {
            "task": self.task, "task_definition": head.strip(),
            "boundary": blind_boundary(self.task, cell["cell"]),
            "items": items}, fold_ids)
        blind, dropped = sanitize_blind(blind, batch["order"])
        if dropped:
            write_json(rd / "blind_sanitized.json", {"dropped": dropped})

        gold = {i: self.rows[i][FIELD[self.task]] for i in batch["order"]}
        if p["placebo"]:
            ids = list(batch["order"])
            vals = [gold[i] for i in ids]
            random.Random(f"placebo:{t}").shuffle(vals)
            gold = dict(zip(ids, vals))

        def is_wrong(i):
            g, pv = gold[i], pred_value(self.task, champ[i])
            return g != pv if self.task == "task1" else set(g) != set(pv or [])
        edit_items = [dict(it, gold=gold[it["example_id"]], wrong=is_wrong(it["example_id"]))
                      for it in items]
        types = list(EDIT_TYPES[: p["n_candidates"]])
        proposal = self.propose(rd / "proposer_edit.json", EDIT_PROMPT, {
            "task": self.task, "instruction": champ_text, "target": boundary,
            "blind_audit": blind, "items": edit_items, "n_edits": p["n_candidates"],
            "edit_types": types, "max_edit_words": p["max_edit_words"],
            "max_growth_words": p["max_growth_words"]}, fold_ids)

        if not isinstance(proposal, dict):
            proposal = {}
        if not isinstance(proposal.get("edits"), list):
            proposal["edits"] = []
        if not isinstance(proposal.get("faults"), list):
            proposal["faults"] = []
        faults = [f for f in proposal["faults"] if isinstance(f, dict)]
        wrong_shown = {it["example_id"] for it in edit_items if it["wrong"]}
        valid_faults = ("misread_evidence", "missed_evidence", "wrong_rule", "sound_but_wrong")
        fault_by_item = {}
        for fault in faults:
            eid, kind = fault.get("example_id"), fault.get("fault")
            if isinstance(eid, str) and eid in wrong_shown and kind in valid_faults:
                fault_by_item.setdefault(eid, kind)
        fault_mix = Counter(fault_by_item.values())
        noise = (sum(fault_mix.values()) > 0 and
                 fault_mix.get("sound_but_wrong", 0) > p["noise_share"] * len(wrong_shown))
        base_dec["fault_mix"] = dict(fault_mix)
        if noise:
            return self.finish_round(rd, dict(base_dec, outcome="skipped", cell_outcome="label_noise",
                                              reason="most wrong items are sound_but_wrong",
                                              n_edits_returned=len(proposal.get("edits") or [])))

        cands = read_json(rd / "candidates.json")
        if cands is None:
            seed_text = self.prompt_text(self.config["seeds"][0]["id"])
            batch_rows = [self.rows[i] for i in batch["order"]]
            tried = self.tried_norms()
            cands, seen_types, n = [], set(), 0
            for e in proposal.get("edits") or []:
                if not isinstance(e, dict):
                    cands.append({"edit": e, "edit_type": None, "rejected": "edit is not an object"})
                    continue
                entry = {"edit": e, "edit_type": e.get("edit_type")}
                if e.get("edit_type") not in types:
                    entry["rejected"] = f"edit_type {e.get('edit_type')!r} not requested"
                elif e.get("edit_type") in seen_types:
                    entry["rejected"] = "duplicate edit_type"
                else:
                    seen_types.add(e["edit_type"])
                    text, reason = validate_edit(e, champ_text, seed_text, self.task, batch_rows, tried, p)
                    if reason:
                        entry["rejected"] = reason
                    else:
                        n += 1
                        cid = f"r{t:02d}c{n}"
                        self.register_prompt(cid, text)
                        tried.add(norm_ws(text))
                        entry.update(cand_id=cid, words=len(words(text)),
                                     diff=list(difflib.unified_diff(champ_text.splitlines(), text.splitlines(),
                                                                    "champion", cid, n=0, lineterm="")))
                cands.append(entry)
            valid = [c for c in cands if "cand_id" in c]
            for c in valid:
                others = [o for o in valid if o is not c]
                def change(x):
                    return (x["edit"].get("anchor") or "") + " " + (x["edit"].get("new_text") or "")
                c["min_word_diff_to_others"] = (min(word_diff(change(c), change(o)) for o in others)
                                                if others else None)
            write_json(rd / "candidates.json", cands)
        valid = [c for c in cands if "cand_id" in c]
        # A restart can see candidates.json before their registrations reach state.json.
        for c in valid:
            cid = c["cand_id"]
            self.state["prompts"][cid] = sha256_text(self.prompt_text(cid))
        self.save_state()
        base_dec.update(n_edits=len(cands), n_valid=len(valid))
        if not proposal.get("edits"):
            return self.finish_round(rd, dict(base_dec, outcome="failed", reason="proposer returned no edits"))
        if not valid:
            return self.finish_round(rd, dict(base_dec, outcome="failed", reason="no valid edit"))

        quick = read_json(rd / "quick_gate.json")
        if quick is None:
            qset = quick_set(self.task, self.rows, eval_ids, cell["cell"], t, p["quick_n"])
            results = []
            base_l = losses(self.task, self.rows, champ, qset)
            for c in valid:
                cp = self.predict(c["cand_id"], qset)
                led = ledger(base_l, losses(self.task, self.rows, cp, qset))
                ok = led["right_to_wrong"] < p["quick_max_rw"] and led["net"] > 0
                results.append({"cand_id": c["cand_id"], "edit_type": c["edit_type"],
                                "ledger": led, "pass": ok})
            passing = sorted((r for r in results if r["pass"]),
                             key=lambda r: (-r["ledger"]["net"], r["ledger"]["cand_mean"], r["cand_id"]))
            quick = {"quick_ids": qset, "results": results,
                     "to_full": [r["cand_id"] for r in passing[: p["max_full"]]]}
            write_json(rd / "quick_gate.json", quick)
        base_dec["quick_pass"] = sum(r["pass"] for r in quick["results"])
        if not quick["to_full"]:
            return self.finish_round(rd, dict(base_dec, outcome="failed", reason="nothing passed the quick gate"))

        full = read_json(rd / "full_gate.json")
        if full is None:
            tau_scaled = self.state["tau"] * len(eval_ids) / len(self.all_ids)
            results = []
            for cid in quick["to_full"]:
                cp = self.predict(cid, eval_ids)
                passed, m = full_gate_metrics(self.task, self.rows, champ, cp, eval_ids,
                                              self.fold_of, p, tau_scaled)
                results.append({"cand_id": cid, "pass": passed, "tau_scaled": tau_scaled, **m})
            full = {"eval_folds": [j for j in range(len(self.folds)) if j != k], "results": results}
            write_json(rd / "full_gate.json", full)
        passed = [r for r in full["results"] if r["pass"]]
        base_dec["full_pass"] = len(passed)
        if not passed:
            return self.finish_round(rd, dict(base_dec, outcome="failed", reason="nothing passed the full gate"))
        best = sorted(passed, key=lambda r: (-r["ledger"]["net"], r["ledger"]["cand_mean"], r["cand_id"]))[0]
        self.predict(best["cand_id"], fold_ids)     # the new champion has all items predicted
        return self.finish_round(rd, dict(base_dec, outcome="accepted", champion_after=best["cand_id"],
                                          net=best["ledger"]["net"],
                                          right_to_wrong=best["ledger"]["right_to_wrong"],
                                          eval_mean=[best["ledger"]["base_mean"], best["ledger"]["cand_mean"]]))

    def finish_round(self, rd, decision):
        decision["time"] = now()
        write_json(rd / "decision.json", decision)
        return decision

    def apply_decision(self, d):
        """State update for a finished round; idempotent (keyed by round number)."""
        if self.state["round"] >= d["round"]:
            return
        key = cell_key(d["cell"]) if d.get("cell") is not None else None
        if d["outcome"] == "accepted":
            self.state["champion"] = d["champion_after"]
            self.state["patience"] = 0
            self.state["lineage"].append({"round": d["round"], "champion": d["champion_after"],
                                          "mean_loss": self.mean_loss(d["champion_after"], self.all_ids)})
        elif d["outcome"] == "failed":
            self.state["patience"] += 1
        if key is not None:
            self.state["cell_history"].setdefault(key, []).append(d.get("cell_outcome") or d["outcome"])
        self.state["round"] = d["round"]
        self.state["decisions"].append({k: d.get(k) for k in ("round", "fold", "cell", "outcome", "reason",
                                                              "champion_after", "net")})
        self.save_state()

    def step(self, rounds=None):
        if not self.state.get("baseline_done"):
            sys.exit("run `evolve.py baseline` first")
        done_now = 0
        while not self.state.get("stopped"):
            if self.state["round"] >= self.params["max_rounds"]:
                self.state["stopped"] = "max_rounds"
                break
            if self.state["patience"] >= self.params["max_patience"]:
                self.state["stopped"] = "patience"
                break
            if rounds is not None and done_now >= rounds:
                break
            t = self.state["round"] + 1
            try:
                d = self.run_round(t)
            except BudgetExhausted as e:
                self.log(str(e))
                self.state["stopped"] = "budget"
                break
            self.apply_decision(d)
            self.write_lineage()
            self.log(f"round {t} fold {d['fold']}: {d['outcome']}"
                     + (f" ({d.get('reason')})" if d.get("reason") else "")
                     + (f" -> champion {d['champion_after']} net {d['net']}" if d["outcome"] == "accepted" else ""))
            done_now += 1
        self.save_state()
        self.write_lineage()
        return self.state

    # ---- reporting
    def write_lineage(self):
        lines = [f"# Evolve lineage: {self.task} / {self.run_dir.name}", ""]
        base = read_json(self.run_dir / "baseline.json") or {}
        lines += [f"Seeds: {', '.join(s['id'] + ' = ' + s['file'] for s in self.config['seeds'])}. "
                  f"tau = {base.get('tau')}; seed mean loss {base.get('seed_mean_loss')}.", ""]
        for rd in sorted((self.run_dir / "rounds").glob("round_*")):
            d = read_json(rd / "decision.json")
            if d is None:
                lines += [f"## {rd.name}: in progress", ""]
                continue
            lines += [f"## Round {d['round']} (fold {d['fold']}): {d['outcome']}", "",
                      f"- champion before: {d['champion_before']}",
                      f"- target cell: {describe_cell(self.task, d['cell']) if d.get('cell') else '—'}",
                      f"- fault mix: {d.get('fault_mix')}",
                      f"- reason: {d.get('reason') or '—'}"]
            for c in read_json(rd / "candidates.json", []) or []:
                lines.append(f"- {c.get('cand_id', 'rejected')} [{c.get('edit_type')}]: "
                             + (c["rejected"] if "rejected" in c else
                                f"{c['words']} words, min diff to others {c.get('min_word_diff_to_others')}"))
                if "diff" in c:
                    lines += ["", "```diff", *c["diff"][2:], "```", ""]
            q = read_json(rd / "quick_gate.json")
            if q:
                lines += ["", "| quick gate | net | right→wrong | wrong→right | pass |", "|---|---|---|---|---|"]
                lines += [f"| {r['cand_id']} | {r['ledger']['net']} | {r['ledger']['right_to_wrong']} | "
                          f"{r['ledger']['wrong_to_right']} | {r['pass']} |" for r in q["results"]]
            f = read_json(rd / "full_gate.json")
            if f:
                lines += ["", "| full gate | net | P(better) | r→w / cap | G3 | G5 folds | G6 | pass |",
                          "|---|---|---|---|---|---|---|---|"]
                for r in f["results"]:
                    g = r["gates"]
                    lines.append(f"| {r['cand_id']} | {r['ledger']['net']} (need {g['G1_gain']['need_net']:.1f}) | "
                                 f"{g['G1_gain']['p_better']:.3f} | {g['G2_no_damage']['right_to_wrong']} / "
                                 f"{g['G2_no_damage']['cap']:.1f} | {g['G3_no_shift']['pass']} | "
                                 f"{g['G5_stability']['folds_better']} | {g['G6_validity']['invalid']} | {r['pass']} |")
            if d["outcome"] == "accepted":
                lines.append(f"\n**Accepted {d['champion_after']}**: net {d['net']}, "
                             f"eval mean loss {d['eval_mean'][0]:.4f} → {d['eval_mean'][1]:.4f}")
            lines.append("")
        (self.run_dir / "lineage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def process_metrics(self):
        """eval.md section 4, computed from the run directory."""
        rounds = []
        for rd in sorted((self.run_dir / "rounds").glob("round_*")):
            d = read_json(rd / "decision.json")
            if d is None:
                continue
            cands = read_json(rd / "candidates.json", []) or []
            valid = [c for c in cands if "cand_id" in c]
            q = read_json(rd / "quick_gate.json")
            rounds.append({"round": d["round"], "outcome": d["outcome"], "fault_mix": d.get("fault_mix", {}),
                           "n_edits": len(cands), "n_valid": len(valid),
                           "diverse": sum(1 for c in valid if (c.get("min_word_diff_to_others") or 0) > 20),
                           "quick_pass": sum(r["pass"] for r in q["results"]) if q else None,
                           "quick_tested": len(q["results"]) if q else 0,
                           "rw_accepted": d.get("right_to_wrong")})
        n_edits = sum(r["n_edits"] for r in rounds)
        n_valid = sum(r["n_valid"] for r in rounds)
        tested = sum(r["quick_tested"] for r in rounds)
        qp = sum(r["quick_pass"] or 0 for r in rounds)
        seed_id = self.config["seeds"][0]["id"]
        champ = self.state.get("champion")
        out = {"rounds": rounds,
               "accepted_edits": sum(r["outcome"] == "accepted" for r in rounds),
               "edit_validity": (n_valid / n_edits) if n_edits else None,
               "quick_gate_pass_rate": (qp / tested) if tested else None,
               "prompt_growth_words": (len(words(self.prompt_text(champ))) - len(words(self.prompt_text(seed_id))))
               if champ else None,
               "fault_mix_total": dict(sum((Counter(r["fault_mix"]) for r in rounds), Counter())),
               "tokens_used": self.state.get("tokens_used", 0),
               "output_tokens_used": self.state.get("output_tokens_used", 0)}
        if champ and self.state.get("baseline_done"):
            s, c = self.preds_of(seed_id), self.preds_of(champ)
            if all(i in c for i in self.all_ids):
                ls = losses(self.task, self.rows, s, self.all_ids)
                lc = losses(self.task, self.rows, c, self.all_ids)
                diffs = [b - a for a, b in zip(ls, lc)]
                obs, lo, hi, pb = bootstrap(diffs, 3000, seed=0)
                per_fold = {}
                for k, f in enumerate(self.folds):
                    d = [x for i, x in zip(self.all_ids, diffs) if self.fold_of[i] == k]
                    per_fold[k] = sum(d) / len(d)
                out["champion_vs_seed_train_evolve"] = {
                    "note": "in-sample for the selection, not a clean OOF estimate (see implementation.md)",
                    "seed_mean": sum(ls) / len(ls), "champion_mean": sum(lc) / len(lc),
                    "diff": obs, "ci": [lo, hi], "p_better": pb, "per_fold_diff": per_fold,
                    "folds_better": sum(v < 0 for v in per_fold.values()), "ledger": ledger(ls, lc)}
        return out

    def status(self):
        st = self.state
        print(f"run {self.run_dir}")
        print(f"task {self.task}; items {len(self.all_ids)} (limit/fold {self.config['limit_per_fold']}); "
              f"dry_run {self.config['dry_run']}")
        print(f"baseline done: {st.get('baseline_done')}; tau {st.get('tau')}; champion {st.get('champion')}; "
              f"round {st['round']}/{self.params['max_rounds']}; patience {st['patience']}/"
              f"{self.params['max_patience']}; stopped: {st.get('stopped')}")
        print(f"input tokens used {st.get('tokens_used', 0):,} / {self.params['budget_tokens']:,}; "
              f"output tokens {st.get('output_tokens_used', 0):,}")
        for d in st["decisions"]:
            print(f"  round {d['round']} fold {d['fold']} {d['outcome']:9s} "
                  f"{describe_cell(self.task, d['cell']) if d.get('cell') else '—'}"
                  + (f" -> {d['champion_after']} (net {d['net']})" if d["outcome"] == "accepted" else
                     f" ({d.get('reason')})"))
        pm = self.process_metrics()
        write_json(self.run_dir / "process_metrics.json", pm)
        print(json.dumps({k: v for k, v in pm.items() if k != "rounds"}, indent=2, ensure_ascii=False))
        return pm


# ---------------------------------------------------------------- commands
def cmd_init(args):
    params = parse_params(args.param)
    task = args.task
    seeds = []
    lineages = set()
    for n, path in enumerate(args.seed):
        p = Path(path)
        p = p if p.is_absolute() else ROOT / p
        if not p.exists():
            sys.exit(f"seed not found: {path}")
        m = SEED_NAME_RE.search(p.name)
        if not m:
            sys.exit(f"seed file must be named zero_shot_<answer|reason|facts>_v<N>.txt: {p.name}")
        lineages.add(m.group(1))
        text = p.read_text(encoding="utf-8")
        split_tail(text)
        protected_strings(task, text)
        try:
            rel = str(p.relative_to(ROOT))
        except ValueError:
            rel = str(p)
        seeds.append({"id": f"s{n}", "file": rel, "sha256": sha256_text(text), "text": text})
    if len(lineages) != 1:
        sys.exit(f"all seeds must share one lineage (output format), got {sorted(lineages)}")
    lineage = lineages.pop()
    out_root = Path(args.out_root) if args.out_root else (
        ROOT / "results" / ("_smoke/evolve" if args.dry_run else "evolve"))
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = out_root / task / run_id
    if run_dir.exists():
        sys.exit(f"{run_dir} already exists; every run gets a new run_id")
    rows, folds, folds_doc = load_data(args.limit_per_fold, check_folds=not args.skip_fold_check)
    import run as runmod
    config = {
        "run_id": run_id, "task": task, "created_at": now(), "lineage": lineage,
        "output_format": LINEAGE_FORMATS[lineage], "params": params,
        "limit_per_fold": args.limit_per_fold, "dry_run": bool(args.dry_run),
        "check_folds": not args.skip_fold_check,
        "seeds": [{k: v for k, v in s.items() if k != "text"} for s in seeds],
        "predictor_params": runmod.PARAMS, "predictor_max_attempts": MAX_ATTEMPTS,
        "proposer_prompts": {"blind": {"file": str(BLIND_PROMPT.relative_to(ROOT)),
                                       "sha256": sha256_file(BLIND_PROMPT)},
                             "edit": {"file": str(EDIT_PROMPT.relative_to(ROOT)),
                                      "sha256": sha256_file(EDIT_PROMPT)}},
        "data": {"train_sha256": sha256_file(TRAIN_FILE), "folds_file": str(FOLDS_FILE.relative_to(ROOT)),
                 "folds_sha256": sha256_file(FOLDS_FILE), "manifest_sha256": folds_doc["manifest_sha256"],
                 "train_evolve_sha256": folds_doc["train_evolve_sha256"],
                 "fold_sizes": [len(f) for f in folds]},
        "code_git_sha": git_sha(),
    }
    run_dir.mkdir(parents=True)
    write_json(run_dir / "config.json", config)
    state = {"round": 0, "champion": None, "patience": 0, "cell_history": {}, "tokens_used": 0,
             "prompts": {}, "decisions": [], "lineage": [], "baseline_done": False, "stopped": None}
    write_json(run_dir / "state.json", state)
    ev = Evolver(run_dir)
    for s in seeds:
        ev.register_prompt(s["id"], s["text"])
    ev.save_state()
    print(run_dir)
    return run_dir


def open_run(args, **kw):
    run_dir = Path(args.run_dir)
    run_dir = run_dir if run_dir.is_absolute() else ROOT / run_dir
    cfg = read_json(run_dir / "config.json")
    if cfg is None:
        sys.exit(f"no config.json in {run_dir}")
    if args.limit_per_fold is not None and args.limit_per_fold != cfg["limit_per_fold"]:
        sys.exit("--limit-per-fold differs from this run's config; start a new run")
    if args.dry_run and not cfg["dry_run"]:
        sys.exit("--dry-run on a real run; start a new dry run instead")
    return Evolver(run_dir, concurrency=args.concurrency, **kw)


def export_prompt(ev, version, prompts_root=None):
    prompts_root = Path(prompts_root or PROMPTS_ROOT)
    m = VERSION_RE.match(version)
    if not m:
        sys.exit(f"--version must look like reason-v5, got {version!r}")
    if m.group(1) != ev.config["lineage"]:
        sys.exit(f"--version lineage {m.group(1)!r} differs from the seed lineage {ev.config['lineage']!r}")
    champ = ev.state.get("champion")
    if not champ:
        sys.exit("no champion yet")
    out = prompts_root / "single" / ev.task / f"zero_shot_{version.replace('-', '_')}.txt"
    cl = prompts_root / "evolve" / ev.task / f"{version}.CHANGELOG.md"
    for path in (out, cl):
        if path.exists():
            sys.exit(f"{path} exists; prompts are frozen, pick a new version")
    text = ev.prompt_text(champ)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    log = [f"# {ev.task} zero-shot {version}", "",
           f"Exported from evolve run `{ev.run_dir.relative_to(ROOT) if ev.run_dir.is_relative_to(ROOT) else ev.run_dir}`"
           f" (run_id {ev.config['run_id']}), champion `{champ}`, sha256 `{sha256_text(text)}`.",
           f"Seed: `{ev.config['seeds'][0]['file']}` (sha256 `{ev.config['seeds'][0]['sha256']}`).", ""]
    accepted = [d for d in ev.state["decisions"] if d["outcome"] == "accepted"]
    if not accepted:
        log.append("No edit was accepted: the exported prompt equals the best seed.")
    for d in accepted:
        rd = ev.run_dir / "rounds" / f"round_{d['round']:02d}"
        cand = next(c for c in read_json(rd / "candidates.json") if c.get("cand_id") == d["champion_after"])
        full = next(r for r in read_json(rd / "full_gate.json")["results"] if r["cand_id"] == d["champion_after"])
        g = full["gates"]
        log += [f"## Round {d['round']} (proposing fold {d['fold']}): {cand['edit_type']} edit `{d['champion_after']}`",
                "", f"Target: {describe_cell(ev.task, d['cell'])}. Rationale: {cand['edit'].get('rationale')}", "",
                f"Full gate on {full['ledger']['n']} items: net flips {full['ledger']['net']}, "
                f"right→wrong {full['ledger']['right_to_wrong']}, wrong→right {full['ledger']['wrong_to_right']}, "
                f"mean loss {full['ledger']['base_mean']:.4f} → {full['ledger']['cand_mean']:.4f}, "
                f"P(better) {g['G1_gain']['p_better']:.3f}, folds better {g['G5_stability']['folds_better']}.",
                "", "```diff", *cand["diff"][2:], "```", ""]
    cl.parent.mkdir(parents=True, exist_ok=True)
    cl.write_text("\n".join(log) + "\n", encoding="utf-8")
    print(f"wrote {out} and {cl}")
    return out, cl


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--concurrency", type=int, default=8)
        p.add_argument("--limit-per-fold", type=int, default=None)
        p.add_argument("--dry-run", action="store_true")

    i = sub.add_parser("init")
    common(i)
    i.add_argument("--task", required=True, choices=list(FIELD))
    i.add_argument("--seed", action="append", required=True)
    i.add_argument("--param", action="append", default=[])
    i.add_argument("--run-id", default=None)
    i.add_argument("--out-root", default=None, help="default results/evolve (dry run: results/_smoke/evolve)")
    i.add_argument("--skip-fold-check", action="store_true", help=argparse.SUPPRESS)
    for name in ("baseline", "step", "status", "export"):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--run-dir", required=True)
        if name == "step":
            p.add_argument("--rounds", type=int, default=None)
        if name == "export":
            p.add_argument("--version", required=True)
    args = ap.parse_args(argv)
    if args.command == "init":
        return cmd_init(args)
    ev = open_run(args)
    if args.command == "baseline":
        try:
            return ev.baseline()
        except (BudgetExhausted, ApiUnavailable) as e:
            sys.exit(str(e))
    if args.command == "step":
        try:
            return ev.step(args.rounds)
        except ApiUnavailable as e:
            ev.save_state()
            sys.exit(str(e))
    if args.command == "status":
        return ev.status()
    if args.command == "export":
        if ev.config["dry_run"]:
            sys.exit("a dry run cannot be exported (its predictions are fake)")
        return export_prompt(ev, args.version)


if __name__ == "__main__":
    main()
