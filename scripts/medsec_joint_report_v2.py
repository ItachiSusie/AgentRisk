"""Stitch blocked Med memory cases to a separately versioned source repair run."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import medsec_joint_report_v1 as base
from scripts.medsec_full_med_v15 import recompute as med_primary_recompute
from scripts.medsec_full_med_v16 import recompute as med_supp_recompute
from scripts import medsec_full_med_v14 as med_core

FORMAT = "medsec-joint-development-v2"


def evaluate(primary_dir: Path, supplement_dir: Path, health_dir: Path) -> dict:
    primary_dir, supplement_dir, health_dir = [Path(p).resolve() for p in (primary_dir, supplement_dir, health_dir)]
    med_core.FORMAT = "medsec-med-full-v15"
    report = base.evaluate(primary_dir, health_dir)
    primary = med_primary_recompute(primary_dir)
    med_core.FORMAT = "medsec-med-supplement-v16"
    supplement = med_supp_recompute(supplement_dir)
    if supplement["smoke"] or supplement["planned_attacks"] != 48:
        raise ValueError("requires full 48-candidate memory supplement")
    supplement_plan = json.loads((supplement_dir / "plan.json").read_text())
    if supplement_plan["parent_run_id"] != primary["run_id"]:
        raise ValueError("supplement parent run mismatch")
    taxonomy = json.loads(base.TAXONOMY.read_text())
    primary_plan = json.loads((primary_dir / "plan.json").read_text())
    rows = base._med_rows(primary, primary_plan, taxonomy)
    repaired = base._med_rows(supplement, supplement_plan, taxonomy)
    index = {(r["attack_id"], r["condition"]): i for i, r in enumerate(rows)}
    if len(index) != 1848 or len(repaired) != 96:
        raise ValueError("unexpected Med attack condition counts")
    for row in repaired:
        key = row["attack_id"], row["condition"]
        old = rows[index[key]]
        if old["state"] != "blocked_source":
            raise ValueError("supplement tries to replace an executed attack")
        rows[index[key]] = row
    if len({r["attack_id"] for r in rows}) != 924:
        raise ValueError("Med attack coverage mismatch")
    med_track = report["tracks"][0]
    if med_track["benchmark_id"] != "medagentbench_ext":
        raise ValueError("track order changed")
    med_track["supplement_run_id"] = supplement["run_id"]
    med_track["supplemented_attack_candidates"] = 48
    med_track["source_passes"] = primary["source_passes"] + supplement["source_passes"]
    for condition in ("none", "scope"):
        target = next(x for x in med_track["utility"] if x["defense"] == condition)
        addition = next(x for x in supplement["utility"] if x["defense"] == condition)
        target["attempted_targets"] += addition["attempted_targets"]
        target["passed_targets"] += addition["passed_targets"]
        target["utility"] = target["passed_targets"] / target["attempted_targets"] if target["attempted_targets"] else None
    med_track["conditions"] = [base.summarize(rows, c) for c in ("attack_none", "attack_scope")]
    med_track["paired"] = base._paired(rows)
    med_track["by_surface"] = base._grouped(rows, "surface")
    med_track["by_risk"] = base._grouped(rows, "risk_id")
    med_track["risk_coverage"] = [{"risk_id": category["risk_id"],
                                   "status": ("proxy_evaluated" if any(r["risk_id"] == category["risk_id"] and r["eligible"] for r in rows)
                                              else "attempted_unscorable" if any(r["risk_id"] == category["risk_id"] for r in rows)
                                              else "not_evaluated")}
                                  for category in taxonomy["categories"]]
    med_track["native_unknown_records"] = sum(r["native_unknown"] for r in rows)
    med_track["complete"] = (primary["recorded_trials"] == primary["planned_trials"] and
                              supplement["recorded_trials"] == supplement["planned_trials"] and
                              med_track["source_passes"] == med_track["source_tasks"] and
                              all(r["state"] == "complete" for r in rows))
    med_track["missing_jobs"] = len(primary["missing_jobs"]) + len(supplement["missing_jobs"])
    med_track["source_contract_versions"] = ["v10-v15-source-contract", "v11-v2-source-contract",
                                              "v11-v16-source-repair"]
    report["format"] = FORMAT
    report["med_supplement_dir"] = str(supplement_dir)
    report["base_scorer_sha256"] = report["scorer_sha256"]
    report["scorer_sha256"] = base.digest(Path(__file__))
    report["limitations"].append("mixed_version_memory_source_prompts_reported_separately")
    return report


def recompute(root: Path) -> dict:
    root = root.resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["format"] != FORMAT or base.digest(root / "report.json") != manifest["report_sha256"]:
        raise ValueError("joint v2 report changed")
    saved = json.loads((root / "report.json").read_text())
    fresh = evaluate(Path(saved["med_run_dir"]), Path(saved["med_supplement_dir"]), Path(saved["health_run_dir"]))
    fresh["run_id"] = root.name
    if saved != fresh:
        raise ValueError("joint v2 report differs from source replay")
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("med_run_dir", type=Path)
    parser.add_argument("med_supplement_dir", type=Path)
    parser.add_argument("health_run_dir", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    args = parser.parse_args()
    report = evaluate(args.med_run_dir, args.med_supplement_dir, args.health_run_dir)
    run_id = datetime.now(timezone.utc).strftime("v17-joint-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
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
