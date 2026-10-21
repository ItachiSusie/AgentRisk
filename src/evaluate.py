"""Score a finished run against the gold labels and write metrics.json.

Usage: python src/evaluate.py results/deepseek-flash/zero-shot-v1/<run_id>
"""
import argparse
import json
import sys
from pathlib import Path

from common import compute_metrics, load_jsonl, validate_prediction

ROOT = Path(__file__).resolve().parent.parent


def token_usage(raw_records):
    """Sum usage over every attempt, retries included."""
    total = {"attempts": len(raw_records), "prompt_tokens": 0, "completion_tokens": 0,
             "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 0}
    for rec in raw_records:
        usage = (rec.get("response") or {}).get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
            total[key] += usage.get(key) or 0
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    config = json.loads((run_dir / "config.json").read_text())
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}

    preds = {}
    for rec in load_jsonl(run_dir / "predictions.jsonl"):
        eid = rec["example_id"]
        if eid in preds:
            sys.exit(f"duplicate prediction for {eid}")
        if eid not in golds:
            sys.exit(f"prediction for unknown example_id {eid}")
        validate_prediction({k: v for k, v in rec.items() if k != "example_id"})
        preds[eid] = rec

    if not preds:
        sys.exit("no valid predictions to score")

    metrics = compute_metrics(preds, golds)
    complete = metrics["n_failed"] == 0
    metrics.update(
        run_id=config["run_id"],
        split=config["split"],
        complete=complete,
        failed_ids=[i for i in golds if i not in preds],
        tokens=token_usage(load_jsonl(run_dir / "raw_responses.jsonl")),
    )
    if not complete:
        metrics["note"] = "diagnostic only: not every sample has a valid prediction"

    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
