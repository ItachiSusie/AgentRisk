"""Run the v14 full Med protocol with a versioned v10 memory source contract."""
import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import medsec_full_med_v14 as core

OVERRIDE = ROOT / "data/medsec/v15_med_source_contract"
core.FORMAT = "medsec-med-full-v15"
_base_catalog = core.catalog


def catalog():
    tasks, attacks, inputs = _base_catalog()
    manifest_path = OVERRIDE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["format"] != "medsec-med-source-contract-v15":
        raise ValueError("source contract version changed")
    inputs[str(manifest_path)] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for row in manifest["tasks"]:
        path = OVERRIDE / row["task_ref"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != row["sha256"] or row["task_id"] not in tasks or tasks[row["task_id"]]["role"] != "source":
            raise ValueError("invalid source override")
        tasks[row["task_id"]]["path"] = str(path.resolve())
        inputs[str(path.resolve())] = actual
    return tasks, attacks, inputs


core.catalog = catalog


def make_plan(smoke: bool, output_root: Path) -> Path:
    tasks, attacks, inputs = catalog()
    if smoke:
        surfaces = sorted({a["surface"] for a in attacks})
        selected = [next(a for a in attacks if a["surface"] == surface) for surface in surfaces]
        selected.append(next(a for a in attacks if a["attack_id"].startswith("v11-") and a not in selected))
        attacks = sorted({a["attack_id"]: a for a in selected}.values(), key=lambda a: a["attack_id"])
    target_ids = {a["task_id"] for a in attacks}
    source_ids = {tasks[tid]["source_task_id"] for tid in target_ids if tasks[tid]["source_task_id"]}
    plan = {"format": core.FORMAT, "model": core.MODEL, "smoke": smoke,
            "tasks": {tid: tasks[tid] for tid in sorted(target_ids | source_ids)},
            "attacks": attacks, "inputs": inputs,
            "source_task_ids": sorted(source_ids), "target_task_ids": sorted(target_ids),
            "conditions": ["clean_none", "attack_none", "clean_scope", "attack_scope"],
            "baseline_policy": "one clean baseline per target task and defense"}
    run_id = datetime.now(timezone.utc).strftime("v15-med-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    root = output_root.resolve() / run_id
    root.mkdir(parents=True, exist_ok=False)
    core.write_new(root / "plan.json", plan)
    core.write_new(root / "manifest.json", {"format": core.FORMAT, "run_id": run_id,
                                            "plan_sha256": core.digest(root / "plan.json"),
                                            "runner_sha256": core.digest(Path(core.__file__)),
                                            "wrapper_sha256": core.digest(Path(__file__))})
    print(json.dumps({"run_id": run_id, "root": str(root), "smoke": smoke,
                      "sources": len(source_ids), "targets": len(target_ids),
                      "attacks": len(attacks),
                      "planned_trials": len(source_ids) + 2 * len(target_ids) + 2 * len(attacks)}), flush=True)
    return root


def recompute(root: Path) -> dict:
    manifest = json.loads((Path(root) / "manifest.json").read_text())
    if manifest.get("wrapper_sha256") != core.digest(Path(__file__)):
        raise ValueError("v15 wrapper changed")
    return core.recompute(root)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--smoke", action="store_true")
    plan.add_argument("--output-root", type=Path, default=ROOT / "results/medsec")
    run = sub.add_parser("run")
    run.add_argument("run_dir", type=Path)
    run.add_argument("--workers", type=int, default=4)
    score = sub.add_parser("score")
    score.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        make_plan(args.smoke, args.output_root)
    elif args.command == "run":
        result = core.run(args.run_dir, args.workers)
        print(json.dumps({"run_id": result["run_id"], "complete": result["complete"],
                          "planned_trials": result["planned_trials"],
                          "recorded_trials": result["recorded_trials"],
                          "source_passes": result["source_passes"],
                          "utility": result["utility"],
                          "attack_summary": result["attack_summary"]}), flush=True)
    else:
        print(json.dumps(recompute(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
