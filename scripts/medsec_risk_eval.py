"""Read-only risk-category view of a replayed v12 Health experiment."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAXONOMY = ROOT / "data/medsec/medical_risks_v1.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def category_for(attack: dict, taxonomy: dict) -> str | None:
    matches = [category["risk_id"] for category in taxonomy["categories"]
               for rule in category["proxy_rules"]
               if all(attack.get(key) == value for key, value in rule.items())]
    if len(matches) > 1:
        raise ValueError(f"ambiguous clinical risk proxy: {attack['attack_id']}")
    return matches[0] if matches else None


def evaluate(run_dir: Path, taxonomy_path: Path = TAXONOMY) -> dict:
    run_dir = run_dir.resolve()
    taxonomy_path = taxonomy_path.resolve()
    taxonomy = json.loads(taxonomy_path.read_text())
    if taxonomy["schema_version"] != "medsec-medical-risk-taxonomy-v1":
        raise ValueError("unsupported taxonomy")
    completed = subprocess.run([sys.executable, str(ROOT / "src/evaluate.py"), str(run_dir)],
                               cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads(completed.stdout)
    if report["format"] != "medsec-health-container-v12":
        raise ValueError("risk evaluation currently requires a v12 Health run")
    selection = json.loads((run_dir / "selection.json").read_text())
    attacks = {}
    for row in selection["attacks"]:
        sample = json.loads(Path(row["attack_ref"]).read_text())
        if row["attack_id"] != sample["attack_id"] or row["attack_id"] in attacks:
            raise ValueError("invalid selected attack index")
        attacks[row["attack_id"]] = sample
    baselines = {(r["task_id"], r["condition"]): r["utility_pass"]
                 for r in report["records"] if r["condition"].startswith("clean_")}
    groups = defaultdict(list)
    unmapped = []
    for record in report["records"]:
        if not record["condition"].startswith("attack_"):
            continue
        attack = attacks[record["attack_id"]]
        risk_id = category_for(attack, taxonomy)
        if risk_id is None:
            unmapped.append(record["attack_id"])
            continue
        groups[(risk_id, record["condition"])].append(record)
    categories = []
    for category in taxonomy["categories"]:
        conditions = []
        for condition in ("attack_none", "attack_scope"):
            rows = groups[(category["risk_id"], condition)]
            capable = [r for r in rows if baselines.get((r["task_id"],
                         "clean_" + condition.split("_")[-1])) is True]
            unknown = sum(r["attack_success"] == "unknown" for r in rows)
            conditions.append({"condition": condition, "runs": len(rows),
                               "exposed": sum(r["exposed"] for r in rows),
                               "utility_passes": sum(r["utility_pass"] is True for r in rows),
                               "target_successes": sum(r["attack_success"] is True for r in rows),
                               "unknown": unknown, "decidable": len(rows) - unknown,
                               "baseline_capable_runs": len(capable),
                               "baseline_capable_successes": sum(r["attack_success"] is True for r in capable),
                               "trial_run_ids": [r["run_id"] for r in rows]})
        categories.append({"risk_id": category["risk_id"], "name_zh": category["name_zh"],
                           "checkpoint": category["checkpoint"],
                           "status": "proxy_evaluated" if any(c["runs"] for c in conditions) else "not_evaluated",
                           "conditions": conditions, "limitation": category.get("limitation")})
    return {"format": "medsec-medical-risk-evaluation-v1", "source_run_id": report["run_id"],
            "source_complete": report["complete"], "model": report["model"],
            "taxonomy_sha256": digest(taxonomy_path),
            "source_report_sha256": digest(run_dir / "report.json"),
            "selection_sha256": digest(run_dir / "selection.json"),
            "evaluation_code_sha256": digest(Path(__file__)),
            "risk_categories": categories, "unmapped_attack_runs": len(unmapped),
            "limitations": ["synthetic_development_candidates", "proxy_goals_not_clinically_adjudicated",
                            "surface_is_distinct_from_risk", "single_run_per_attack_condition"]}


def evaluate_med_pair(pair_path: Path, taxonomy_path: Path = TAXONOMY) -> dict:
    pair_path = pair_path.resolve()
    taxonomy_path = taxonomy_path.resolve()
    pair = json.loads(pair_path.read_text())
    if pair["format"] != "medsec-v08-pair" or pair["benchmark"] != "extension":
        raise ValueError("requires a Med synthetic extension pair")
    taxonomy = json.loads(taxonomy_path.read_text())
    attack_path = Path(pair["attack"])
    if not attack_path.is_absolute():
        attack_path = ROOT / attack_path
    attack = json.loads(attack_path.read_text())
    risk_id = category_for(attack, taxonomy)
    if risk_id is None:
        raise ValueError("Med pair has no mapped clinical risk proxy")
    rows = {}
    for saved in pair["conditions"]:
        run_dir = pair_path.parent / saved["run_id"]
        completed = subprocess.run([sys.executable, str(ROOT / "src/evaluate.py"), str(run_dir)],
                                   cwd=ROOT, check=True, capture_output=True, text=True)
        fresh = json.loads(completed.stdout)
        condition = saved["condition"]
        if saved != {"condition": condition, **fresh} or condition in rows:
            raise ValueError("pair condition differs from replay")
        rows[condition] = fresh
    if set(rows) != {"clean_none", "attack_none", "clean_scope", "attack_scope"}:
        raise ValueError("incomplete four-condition pair")
    categories = []
    for category in taxonomy["categories"]:
        conditions = []
        for condition in ("attack_none", "attack_scope"):
            row = rows[condition] if category["risk_id"] == risk_id else None
            baseline = rows["clean_" + condition.split("_")[-1]]
            exposed = bool(row and row["security"] and row["security"]["exposed"])
            decidable = bool(row and row["status"] == "completed" and exposed)
            success = bool(decidable and row["security"]["attack_success"])
            conditions.append({"condition": condition, "runs": int(row is not None),
                               "triggered": int(bool(row and row["security"] and row["security"]["triggered"])),
                               "exposed": int(exposed),
                               "utility_passes": int(bool(row and row["synthetic_utility_pass"] is True)),
                               "target_successes": int(success),
                               "unknown": int(bool(row and not decidable)),
                               "decidable": int(decidable),
                               "baseline_capable_runs": int(bool(row and baseline["synthetic_utility_pass"] is True)),
                               "baseline_capable_successes": int(bool(success and baseline["synthetic_utility_pass"] is True)),
                               "trial_run_ids": [row["run_id"]] if row else []})
        categories.append({"risk_id": category["risk_id"], "name_zh": category["name_zh"],
                           "checkpoint": category["checkpoint"],
                           "status": ("proxy_evaluated" if any(c["decidable"] for c in conditions) else
                                      "attempted_unscorable") if category["risk_id"] == risk_id else "not_evaluated",
                           "conditions": conditions, "limitation": category.get("limitation")})
    return {"format": "medsec-medical-risk-evaluation-v1", "source_kind": "med_pair",
            "source_run_id": pair["pair_id"], "source_complete": all(r["status"] == "completed" for r in rows.values()),
            "model": rows["clean_none"]["model"], "taxonomy_sha256": digest(taxonomy_path),
            "source_pair_sha256": digest(pair_path), "attack_sha256": digest(attack_path),
            "evaluation_code_sha256": digest(Path(__file__)), "risk_categories": categories,
            "limitations": ["synthetic_development_candidate", "single_attack_sample",
                            "invalid_or_unexposed_attack_is_unknown_for_risk_rate"]}


def recompute(evaluation_dir: Path) -> dict:
    evaluation_dir = evaluation_dir.resolve()
    manifest = json.loads((evaluation_dir / "manifest.json").read_text())
    if manifest["format"] != "medsec-medical-risk-evaluation-v1":
        raise ValueError("unsupported risk evaluation")
    report_path = evaluation_dir / "report.json"
    if digest(report_path) != manifest["report_sha256"]:
        raise ValueError("risk report changed")
    saved = json.loads(report_path.read_text())
    if "source_pair_path" in saved:
        fresh = evaluate_med_pair(Path(saved["source_pair_path"]))
    else:
        fresh = evaluate(Path(saved["source_run_dir"]))
    fresh["run_id"] = manifest["run_id"]
    if "source_pair_path" in saved:
        fresh["source_pair_path"] = saved["source_pair_path"]
    else:
        fresh["source_run_dir"] = saved["source_run_dir"]
    if saved != fresh:
        raise ValueError("risk classification or source evidence changed")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path, nargs="?")
    parser.add_argument("--med-pair", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    args = parser.parse_args()
    if (args.run_dir is None) == (args.med_pair is None):
        parser.error("provide exactly one Health run directory or --med-pair")
    result = evaluate_med_pair(args.med_pair) if args.med_pair else evaluate(args.run_dir)
    run_id = datetime.now(timezone.utc).strftime("v13-risk-eval-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    output = args.output_root / run_id
    output.mkdir(parents=True, exist_ok=False)
    result["run_id"] = run_id
    if args.med_pair:
        result["source_pair_path"] = str(args.med_pair.resolve())
    else:
        result["source_run_dir"] = str(args.run_dir.resolve())
    report_path = output / "report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"format": result["format"],
                                                      "run_id": run_id,
                                                      "report_sha256": digest(report_path)}, indent=2) + "\n")
    recompute(output)
    print(json.dumps({"run_id": run_id, "source_run_id": result["source_run_id"],
                      "report": str(output / "report.json"),
                      "evaluated_categories": [x["risk_id"] for x in result["risk_categories"]
                                               if x["status"] == "proxy_evaluated"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
