"""Export paired action/observation/output items for defense evaluation."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .checkpoints import extract
from .runtime import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audited-report", type=Path, action="append", required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("results/medsec"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    pair_ids = set()
    for report_path in args.audited_report:
        report = json.loads(report_path.read_text())
        for pair in report["rows"]:
            if not pair["protocol_valid"]:
                continue
            if pair["pair_id"] in pair_ids:
                raise ValueError("duplicate pair across reports")
            pair_ids.add(pair["pair_id"])
            for variant, run_id in (("clean", pair["clean_run_id"]),
                                    ("attack", pair["attack_run_id"])):
                for item in extract(args.runs_root / run_id):
                    rows.append({"pair_id": pair["pair_id"], "variant": variant,
                                 "split": pair["split"], "attack_surface": pair["surface"],
                                 "attack_goal": pair["goal"], **item})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter(row["checkpoint"] for row in rows)
    manifest = {"scope": "targeted evidence only; no general safe/unsafe labels",
                "audited_reports": [{"path": str(p.resolve()), "sha256": digest(p.read_bytes())}
                                    for p in args.audited_report],
                "pairs": len(pair_ids), "items": len(rows), "checkpoint_counts": dict(counts),
                "output_sha256": digest(args.output.read_bytes())}
    manifest_path = args.output.with_suffix(".manifest.json")
    with manifest_path.open("x") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), **manifest}, ensure_ascii=False))


if __name__ == "__main__":
    main()
