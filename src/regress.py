"""Regression checks for instruction patches (docs/agentic-distill/00-common.md section 5, 6.2).

Two uses:
  - library: build an instruction with patches, re-run the predictor on a few rows, and say
    which samples a patch fixed or broke. src/agentic.py repair calls this in its loop.
  - CLI `compare BASE_RUN NEW_RUN`: per-class accuracy change between two finished runs on
    the same data (the whole-train_evolve check after merging).

Usage:
    python src/regress.py compare results/_smoke/task1/zero-shot-facts-v1/<id> results/_smoke/task1/zero-shot-facts-v2/<id>
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from assemble_instruction import split_at_anchor
from common import load_jsonl, task_fields, unpack_prediction
from run import PARAMS, get_client, parse, zero_shot_messages

ROOT = Path(__file__).resolve().parent.parent
GATE = {"task1": None, "task2a": "No Material Harm", "task2b": "No Material Risk"}


def build_system(instruction, patches, title="Decision rules distilled from training errors"):
    """Insert patch texts before the output-format section, exactly as assemble_instruction.py."""
    if not patches:
        return instruction
    head, tail, _ = split_at_anchor(instruction, "instruction")
    block = (f"{title}. Each rule names the condition it applies to, the decision it forces, "
             f"and a counter-example that must not get the rule.\n\n"
             + "\n\n".join(p.strip() for p in patches) + "\n\n")
    return head.rstrip() + "\n\n" + block + tail


def label_of(pred, task):
    field = task_fields(task)[0]
    v = pred[field]
    return v if isinstance(v, int) else tuple(sorted(v))


def is_correct(pred, gold, task):
    return pred is not None and label_of(pred, task) == label_of(gold, task)


def predict_one(client, system, row, task, output_format, retries=2):
    """One zero-shot prediction; None when the output stays invalid after retries."""
    for _ in range(retries + 1):
        try:
            resp = client.chat.completions.create(messages=zero_shot_messages(row, system), **PARAMS)
            pred, _ = unpack_prediction(parse(resp), output_format, task)
            return pred
        except (ValueError, json.JSONDecodeError):
            continue
    return None


def predict_rows(system, rows, task, output_format, concurrency=8, client=None):
    client = client or get_client()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {r["example_id"]: pool.submit(predict_one, client, system, r, task, output_format)
                   for r in rows}
    return {eid: f.result() for eid, f in futures.items()}


def flips(rows, before, after, task):
    """before/after: example_id -> prediction. Returns (fixed ids, broken ids)."""
    fixed, broken = [], []
    for r in rows:
        eid = r["example_id"]
        ok0, ok1 = is_correct(before.get(eid), r, task), is_correct(after.get(eid), r, task)
        if not ok0 and ok1:
            fixed.append(eid)
        if ok0 and not ok1:
            broken.append(eid)
    return fixed, broken


# ---------------------------------------------------------------- per-class comparison
def per_class(golds, preds, task):
    """task1: accuracy per gold severity. task2: recall and precision per label."""
    field = task_fields(task)[0]
    out = {}
    if task == "task1":
        for lvl in range(1, 6):
            ids = [i for i, g in golds.items() if g[field] == lvl and i in preds]
            if ids:
                out[f"severity {lvl}"] = (sum(preds[i][field] == lvl for i in ids) / len(ids), len(ids))
        return out
    labels = sorted({l for g in golds.values() for l in g[field]})
    for lab in labels:
        has = [i for i, g in golds.items() if lab in g[field] and i in preds]
        said = [i for i in preds if lab in preds[i][field]]
        if has:
            out[f"{lab} recall"] = (sum(lab in preds[i][field] for i in has) / len(has), len(has))
        if said:
            out[f"{lab} precision"] = (sum(lab in golds[i][field] for i in said) / len(said), len(said))
    return out


def cmd_compare(args):
    base, new = Path(args.base), Path(args.new)
    cb, cn = (json.loads((d / "config.json").read_text()) for d in (base, new))
    if cb["data_file"] != cn["data_file"] or cb.get("task") != cn.get("task"):
        sys.exit("the two runs must use the same task and data file")
    task = cb.get("task", "multi")
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / cb["data_file"])}
    pb = {r["example_id"]: r for r in load_jsonl(base / "predictions.jsonl")}
    pn = {r["example_id"]: r for r in load_jsonl(new / "predictions.jsonl")}
    a, b = per_class(golds, pb, task), per_class(golds, pn, task)
    print(f"| class | base | new | change | n |\n| --- | --- | --- | --- | --- |")
    worst = 0.0
    for k in a:
        if k in b:
            d = b[k][0] - a[k][0]
            worst = min(worst, d)
            flag = " **drop > 5pp**" if d < -args.max_drop else ""
            print(f"| {k} | {a[k][0]:.3f} | {b[k][0]:.3f} | {d:+.3f}{flag} | {a[k][1]} |")
    gate = "severity 1" if task == "task1" else f"{GATE[task]} recall"
    if gate in a and gate in b and b[gate][0] < a[gate][0]:
        print(f"\nGATE DROPPED: {gate} {a[gate][0]:.3f} -> {b[gate][0]:.3f}")
    print(f"\nlargest drop {worst:+.3f} (limit -{args.max_drop})")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("compare")
    c.add_argument("base")
    c.add_argument("new")
    c.add_argument("--max-drop", type=float, default=0.05)
    c.set_defaults(func=cmd_compare)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
