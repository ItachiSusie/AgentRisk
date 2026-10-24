"""Build an interactive, self-contained report.html for one run.

Usage: python src/analyze.py results/deepseek-flash/zero-shot-v1/<run_id>

Reads the run's predictions/raw responses and the gold labels, embeds everything
into src/report_template.html and writes <run_dir>/report.html (open it in a browser).
"""
import argparse
import json
import sys
from pathlib import Path

from common import DOMAINS, DRIVERS, compute_metrics, load_jsonl

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = Path(__file__).resolve().parent / "report_template.html"


def per_example_cost(raw_records):
    """attempts and token usage per example_id, retries included."""
    cost = {}
    for rec in raw_records:
        c = cost.setdefault(rec["example_id"], {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0})
        c["attempts"] += 1
        usage = (rec.get("response") or {}).get("usage") or {}
        c["prompt_tokens"] += usage.get("prompt_tokens") or 0
        c["completion_tokens"] += usage.get("completion_tokens") or 0
    return cost


def side(rec):
    return {"sev": rec["risk_severity"], "dom": rec["risk_domains"], "drv": rec["risk_drivers"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    config = json.loads((run_dir / "config.json").read_text())
    golds = load_jsonl(ROOT / config["data_file"])
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}
    cost = per_example_cost(load_jsonl(run_dir / "raw_responses.jsonl"))

    samples = []
    for g in golds:
        eid = g["example_id"]
        if eid not in preds:
            continue
        samples.append({
            "id": eid,
            "gold": side(g),
            "pred": side(preds[eid]),
            "action": g["proposed_action"],
            "interaction": g["formatted_interaction"],
            **cost.get(eid, {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0}),
        })
    if not samples:
        sys.exit("no predictions to report")

    metrics = compute_metrics(preds, {g["example_id"]: g for g in golds})
    data = {
        "meta": {
            "run_id": config["run_id"],
            "strategy": config.get("experiment", f"{config['strategy']}-{config['version']}"),
            "split": config["split"],
            "models": config["returned_models"],
            "prompt_sha256": config["prompt_sha256"],
            "data_commit": config["data_hf_commit_sha"],
            "n_total": metrics["n_total"],
            "n_success": metrics["n_success"],
            "failed_ids": [g["example_id"] for g in golds if g["example_id"] not in preds],
            "overall": {k: metrics[k] for k in ("task1_mae", "task2a_mean_jaccard", "task2b_mean_jaccard")},
            "prompt_tokens": sum(s["prompt_tokens"] for s in samples),
            "completion_tokens": sum(s["completion_tokens"] for s in samples),
        },
        "labels": {"dom": list(DOMAINS), "drv": list(DRIVERS)},
        "samples": samples,
    }
    # "<" is escaped so trajectory text can never close the <script> tag
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    html = TEMPLATE.read_text(encoding="utf-8").replace("__REPORT_DATA__", payload)
    out = Path(args.out) if args.out else run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB, {len(samples)} samples)")


if __name__ == "__main__":
    main()
