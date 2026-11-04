"""Merge three single-task runs into one joint-prediction directory for scoring.

Single-task runs each predict one field, so none of them can be compared against the
multi-task table's "all three fields correct" column. This stitches the three runs of the
SAME configuration back together by example_id and writes a directory that
`src/evaluate.py` scores exactly like any joint run.

Hard rule (docs/single-task/00-common.md section 4, C11): a sample is kept only if ALL THREE
tasks produced a valid prediction for it. Nothing is ever filled in from the gold labels or
from a default "safe" label; samples that are incomplete are dropped and listed by id.

Usage:
    python src/assemble_single.py \\
        --task1  results/deepseek-flash/task1/zero-shot-reason-v1/<run_id> \\
        --task2a results/deepseek-flash/task2a/zero-shot-reason-v1/<run_id> \\
        --task2b results/deepseek-flash/task2b/zero-shot-reason-v1/<run_id>
    python src/evaluate.py results/deepseek-flash/single-merged/zero-shot-reason-v1/<run_id>
"""
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from common import TASK_FIELDS, load_jsonl, validate_prediction

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("task1", "task2a", "task2b")
# config fields that must agree across the three runs, or they are not the same experiment
MUST_MATCH = ("experiment", "strategy", "version", "split", "data_file", "data_sha256",
              "selection", "seed", "k", "selection_file", "params")


def rel(path):
    """Repo-relative when the path is inside the repo, absolute otherwise (e.g. a temp dir)."""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def load_source(path, task):
    run_dir = Path(path)
    config = json.loads((run_dir / "config.json").read_text())
    if config.get("task") != task:
        sys.exit(f"{run_dir} has task={config.get('task')!r}, expected {task!r}")
    field, = TASK_FIELDS[task]
    preds = {}
    for rec in load_jsonl(run_dir / "predictions.jsonl"):
        eid = rec["example_id"]
        if eid in preds:
            sys.exit(f"duplicate prediction for {eid} in {run_dir}")
        validate_prediction({k: v for k, v in rec.items() if k != "example_id"}, task)
        preds[eid] = rec[field]
    return run_dir, config, preds


def main():
    ap = argparse.ArgumentParser()
    for task in SOURCES:
        ap.add_argument(f"--{task}", required=True, help=f"finished {task} run directory")
    ap.add_argument("--out", default=None, help="override the output run directory")
    args = ap.parse_args()

    loaded = {task: load_source(getattr(args, task), task) for task in SOURCES}

    # same experiment on every side, or the merged numbers would mix configurations
    ref_task = SOURCES[0]
    ref_cfg = loaded[ref_task][1]
    for task in SOURCES[1:]:
        cfg = loaded[task][1]
        for key in MUST_MATCH:
            if cfg.get(key) != ref_cfg.get(key):
                sys.exit(f"{key} differs: {ref_task}={ref_cfg.get(key)!r} vs {task}={cfg.get(key)!r}; "
                         f"these are not the same configuration")

    golds = {r["example_id"]: r for r in load_jsonl(ROOT / ref_cfg["data_file"])}
    merged, incomplete = [], {}
    for eid in golds:
        have = {task: loaded[task][2].get(eid) for task in SOURCES}
        missing = [task for task, v in have.items() if v is None]
        if missing:
            incomplete[eid] = missing
            continue
        row = {"example_id": eid}
        for task in SOURCES:
            field, = TASK_FIELDS[task]
            row[field] = have[task]
        validate_prediction({k: v for k, v in row.items() if k != "example_id"}, "multi")
        merged.append(row)

    if not merged:
        sys.exit("no example has a prediction from all three tasks")

    experiment = ref_cfg["experiment"]
    out_dir = Path(args.out) if args.out else (
        ROOT / "results" / "deepseek-flash" / "single-merged" / experiment
        / datetime.now().strftime("%Y%m%d-%H%M%S"))
    if out_dir.exists():
        sys.exit(f"{out_dir} already exists; pass --out or wait a second")
    out_dir.mkdir(parents=True)

    with (out_dir / "predictions.jsonl").open("w", encoding="utf-8") as f:
        for row in merged:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # The real per-attempt logs of all three runs, concatenated: evaluate.py then reports the
    # true total cost of answering all three subtasks, which is the number to compare against
    # one joint call. A source without its raw log makes the total wrong, so refuse instead.
    with (out_dir / "raw_responses.jsonl").open("w", encoding="utf-8") as out:
        for task in SOURCES:
            raw = loaded[task][0] / "raw_responses.jsonl"
            if not raw.exists():
                shutil.rmtree(out_dir)
                sys.exit(f"{raw} is missing; the merged token total would be wrong. "
                         f"Pass runs whose raw logs are on this machine.")
            with raw.open(encoding="utf-8") as src:
                for line in src:
                    out.write(line)

    config = {
        "run_id": out_dir.name,
        "experiment": experiment,
        "task": "multi",
        "assembled_from_single_tasks": True,
        "strategy": ref_cfg["strategy"],
        "version": ref_cfg["version"],
        "split": ref_cfg["split"],
        "created_at": datetime.now().astimezone().isoformat(),
        "params": ref_cfg["params"],
        "data_file": ref_cfg["data_file"],
        "data_sha256": ref_cfg["data_sha256"],
        "data_hf_commit_sha": ref_cfg.get("data_hf_commit_sha"),
        "prompt_file": None,   # three different instructions produced this; see sources
        "prompt_sha256": "",
        "sources": {task: {"run_dir": rel(loaded[task][0]),
                           "run_id": loaded[task][1]["run_id"],
                           "prompt_id": loaded[task][1].get("prompt_id"),
                           "prompt_file": loaded[task][1]["prompt_file"],
                           "prompt_sha256": loaded[task][1]["prompt_sha256"]}
                    for task in SOURCES},
        "n_merged": len(merged),
        "incomplete_example_ids": {eid: tasks for eid, tasks in sorted(incomplete.items())},
        "returned_models": sorted({m for task in SOURCES
                                   for m in loaded[task][1].get("returned_models", [])}),
        "invocations": [],
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")

    print(f"merged {len(merged)}/{len(golds)} samples -> {rel(out_dir)}")
    for task in SOURCES:
        print(f"  {task:6s} {rel(loaded[task][0])}")
    if incomplete:
        print(f"dropped {len(incomplete)} sample(s) missing at least one task, NOT filled in:")
        for eid, tasks in sorted(incomplete.items()):
            print(f"  {eid}: missing {', '.join(tasks)}")
    print(f"\nnow run: .venv/bin/python src/evaluate.py {rel(out_dir)}")


if __name__ == "__main__":
    main()
