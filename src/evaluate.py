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
    parser.add_argument("--grader", help="MedAgentBench official refsol.py, when available")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    if (run_dir / "manifest.json").exists():
        label_manifest = json.loads((run_dir / "manifest.json").read_text())
        if label_manifest.get("format") == "medsec-medical-risk-evaluation-v1":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_risk_eval import recompute as recompute_risks
            print(json.dumps(recompute_risks(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-med-full-v14":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_full_med_v14 import recompute as recompute_med_full
            print(json.dumps(recompute_med_full(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-med-full-v15":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_full_med_v15 import recompute as recompute_med_v15
            print(json.dumps(recompute_med_v15(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-med-supplement-v16":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_full_med_v16 import recompute as recompute_med_v16
            print(json.dumps(recompute_med_v16(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-med-full-v17":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_full_med_v17 import recompute as recompute_med_v17
            print(json.dumps(recompute_med_v17(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-joint-development-v1":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_joint_report_v1 import recompute as recompute_joint
            print(json.dumps(recompute_joint(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-joint-development-v2":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_joint_report_v2 import recompute as recompute_joint_v2
            print(json.dumps(recompute_joint_v2(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-joint-development-v3":
            sys.path.insert(0, str(ROOT))
            from scripts.medsec_joint_report_v3 import recompute as recompute_joint_v3
            print(json.dumps(recompute_joint_v3(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-health-container-v12":
            from medsec.v12.scoring import recompute as recompute_health
            print(json.dumps(recompute_health(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-memory-experiment-v1":
            from medsec.v11.experiment import recompute as recompute_memory
            print(json.dumps(recompute_memory(run_dir), ensure_ascii=False, indent=2))
            return
        if label_manifest.get("format") == "medsec-labels-v1":
            from medsec.labels_v1.replay import recompute as recompute_labels
            print(json.dumps(recompute_labels(run_dir), ensure_ascii=False, indent=2))
            return

    if (run_dir / "manifest.json").exists() and (run_dir / "events.jsonl").exists():
        manifest = json.loads((run_dir / "manifest.json").read_text())
        if manifest.get("format") == "medsec-v08":
            from medsec.v08.scoring import recompute as recompute_v08
            print(json.dumps(recompute_v08(run_dir), ensure_ascii=False, indent=2))
            return
        if manifest.get("format") == "medsec-v0.7":
            from medsec.v07.scoring import recompute as recompute_v07
            print(json.dumps(recompute_v07(run_dir), ensure_ascii=False, indent=2))
            return
        from medsec.evaluate import recompute
        print(json.dumps(recompute(run_dir, args.grader), ensure_ascii=False, indent=2))
        return

    config = json.loads((run_dir / "config.json").read_text())
    # runs written before single-task support have no "task" key and are joint predictions
    task = config.get("task", "multi")
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}

    preds = {}
    for rec in load_jsonl(run_dir / "predictions.jsonl"):
        eid = rec["example_id"]
        if eid in preds:
            sys.exit(f"duplicate prediction for {eid}")
        if eid not in golds:
            sys.exit(f"prediction for unknown example_id {eid}")
        validate_prediction({k: v for k, v in rec.items() if k != "example_id"}, task)
        preds[eid] = rec

    if not preds:
        sys.exit("no valid predictions to score")

    metrics = compute_metrics(preds, golds, task)
    complete = metrics["n_failed"] == 0
    metrics.update(
        run_id=config["run_id"],
        split=config["split"],
        complete=complete,
        failed_ids=[i for i in golds if i not in preds],
        tokens=token_usage(load_jsonl(run_dir / "raw_responses.jsonl")),
    )
    if task != "multi":
        metrics["task"] = task
    if not complete:
        metrics["note"] = "diagnostic only: not every sample has a valid prediction"

    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
