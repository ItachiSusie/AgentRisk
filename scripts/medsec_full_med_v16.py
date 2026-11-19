"""Supplement blocked v15 memory attacks with versioned model-written sources."""
import argparse
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import medsec_full_med_v15 as previous

core = previous.core
core.FORMAT = "medsec-med-supplement-v16"
OVERRIDE = ROOT / "data/medsec/v16_med_memory_sources"
_base_catalog = previous.catalog


def catalog():
    tasks, attacks, inputs = _base_catalog()
    manifest_path = OVERRIDE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["format"] != "medsec-med-source-repair-v16":
        raise ValueError("source repair manifest changed")
    inputs[str(manifest_path)] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    repaired = set()
    for row in manifest["tasks"]:
        path = OVERRIDE / row["task_ref"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != row["sha256"] or row["task_id"] not in tasks or tasks[row["task_id"]]["role"] != "source":
            raise ValueError("invalid source repair")
        tasks[row["task_id"]]["path"] = str(path.resolve())
        inputs[str(path.resolve())] = actual
        repaired.add(row["task_id"])
    if len(repaired) != 12:
        raise ValueError("expected 12 repaired sources")
    attacks = [a for a in attacks if tasks[a["task_id"]]["source_task_id"] in repaired]
    if len(attacks) != 48 or len({a["task_id"] for a in attacks}) != 12:
        raise ValueError("repair attack selection changed")
    return tasks, attacks, inputs, manifest["parent_run_id"]


def make_plan(smoke: bool, output_root: Path) -> Path:
    tasks, attacks, inputs, parent_id = catalog()
    if smoke:
        source = tasks[attacks[0]["task_id"]]["source_task_id"]
        attacks = [a for a in attacks if tasks[a["task_id"]]["source_task_id"] == source]
    target_ids = {a["task_id"] for a in attacks}
    source_ids = {tasks[tid]["source_task_id"] for tid in target_ids}
    plan = {"format": core.FORMAT, "model": core.MODEL, "smoke": smoke,
            "parent_run_id": parent_id, "tasks": {tid: tasks[tid] for tid in sorted(target_ids | source_ids)},
            "attacks": attacks, "inputs": inputs,
            "source_task_ids": sorted(source_ids), "target_task_ids": sorted(target_ids),
            "conditions": ["clean_none", "attack_none", "clean_scope", "attack_scope"],
            "baseline_policy": "one clean baseline per target task and defense"}
    run_id = datetime.now(timezone.utc).strftime("v16-med-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
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
        raise ValueError("v16 wrapper changed")
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
                          "utility": result["utility"], "attack_summary": result["attack_summary"]}), flush=True)
    else:
        print(json.dumps(recompute(args.run_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
