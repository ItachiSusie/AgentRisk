"""Uniform-source Med v17 and completed Health v12 development scores."""
import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import medsec_joint_report_v1 as base
from scripts import medsec_full_med_v14 as med_core
from scripts import medsec_full_med_v17 as med_v17

FORMAT = "medsec-joint-development-v3"


def evaluate(med_dir: Path, health_dir: Path) -> dict:
    med_core.FORMAT = "medsec-med-full-v17"
    base.med_recompute = med_v17.recompute
    report = base.evaluate(Path(med_dir), Path(health_dir))
    report["format"] = FORMAT
    report["base_scorer_sha256"] = report["scorer_sha256"]
    report["scorer_sha256"] = base.digest(Path(__file__))
    report["tracks"][0]["source_contract_versions"] = ["v10-v15-source-contract", "v11-v17-source-contract"]
    report["limitations"].append("source_prompts_versioned_uniformly_by_suite")
    return report


def recompute(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["format"] != FORMAT or base.digest(root / "report.json") != manifest["report_sha256"]:
        raise ValueError("joint v3 report changed")
    saved = json.loads((root / "report.json").read_text())
    fresh = evaluate(Path(saved["med_run_dir"]), Path(saved["health_run_dir"]))
    fresh["run_id"] = root.name
    if saved != fresh:
        raise ValueError("joint v3 report differs from source replay")
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("med_run_dir", type=Path)
    parser.add_argument("health_run_dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    args = parser.parse_args()
    report = evaluate(args.med_run_dir, args.health_run_dir)
    run_id = datetime.now(timezone.utc).strftime("v18-joint-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = args.output_root.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    report["run_id"] = run_id
    (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (root / "manifest.json").write_text(json.dumps({"format": FORMAT, "run_id": run_id,
                                                    "report_sha256": base.digest(root / "report.json")}, indent=2) + "\n")
    recompute(root)
    print(json.dumps({"run_id": run_id, "report": str(root / "report.json"),
                      "tracks": [{"benchmark_id": x["benchmark_id"], "complete": x["complete"],
                                  "utility": x["utility"], "conditions": x["conditions"],
                                  "paired": x["paired"]} for x in report["tracks"]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
