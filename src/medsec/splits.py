"""Build and audit patient-disjoint MedSec development/calibration/frozen splits."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from .runtime import digest

MRN_PATTERN = re.compile(r"S\d{7}")
SEED = "medsec-v0.3"
COUNTS = {"development": 60, "calibration": 19, "frozen_test": 19}


def sample_patients(sample, tasks, attack_root):
    patients = set(MRN_PATTERN.findall(json.dumps(sample, ensure_ascii=False)))
    for task_id in (sample["base_task_id"], sample.get("source_task_id")):
        if task_id:
            patient = tasks[task_id].get("eval_MRN")
            if patient:
                patients.add(patient)
    for step in sample["attack_steps"]:
        patients.update(MRN_PATTERN.findall((Path(attack_root) / step["payload_ref"]).read_text()))
    return patients


def create(tasks_path, sample_dirs, attack_root):
    tasks_path, attack_root = Path(tasks_path), Path(attack_root)
    tasks = {row["id"]: row for row in json.loads(tasks_path.read_text())}
    patients = {row["eval_MRN"] for row in tasks.values() if row.get("eval_MRN")}
    if len(patients) != sum(COUNTS.values()):
        raise ValueError("patient count changed; revise the frozen split protocol")
    sample_files = sorted(path for folder in sample_dirs for path in Path(folder).glob("*.json"))
    pinned = set()
    for path in sample_files:
        pinned |= sample_patients(json.loads(path.read_text()), tasks, attack_root)
    if not pinned <= patients or len(pinned) > COUNTS["development"]:
        raise ValueError("invalid development patient pins")
    remaining = sorted(patients - pinned,
                       key=lambda patient: hashlib.sha256((SEED + ":" + patient).encode()).hexdigest())
    development = pinned | set(remaining[:COUNTS["development"]-len(pinned)])
    calibration = set(remaining[COUNTS["development"]-len(pinned):
                                COUNTS["development"]-len(pinned)+COUNTS["calibration"]])
    frozen = patients - development - calibration
    groups = {"development": development, "calibration": calibration, "frozen_test": frozen}
    if any(len(groups[name]) != count for name, count in COUNTS.items()):
        raise AssertionError("split count mismatch")
    owner = {patient: name for name, group in groups.items() for patient in group}
    return {"version": "v0.3", "seed": SEED, "tasks_sha256": digest(tasks_path.read_bytes()),
            "source_sample_sha256": {str(path): digest(path.read_bytes()) for path in sample_files},
            "pinned_development_patients": sorted(pinned),
            "patients": {name: sorted(group) for name, group in groups.items()},
            "tasks": {task_id: owner[row["eval_MRN"]] for task_id, row in tasks.items()
                      if row.get("eval_MRN")},
            "excluded_tasks": sorted(task_id for task_id, row in tasks.items() if not row.get("eval_MRN"))}


def validate_sample_split(sample, tasks, attack_root, split):
    declared = sample["split"]
    if declared not in split["patients"]:
        raise ValueError("unknown split")
    allowed = set(split["patients"][declared])
    used = sample_patients(sample, tasks, attack_root)
    if not used or not used <= allowed:
        raise ValueError(f"patient split leakage in {sample['attack_id']}: {sorted(used-allowed)}")
    if split["tasks"].get(sample["base_task_id"]) != declared:
        raise ValueError("base task split mismatch")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, action="append", required=True)
    parser.add_argument("--attack-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    split = create(args.tasks, args.source_dir, args.attack_root)
    with args.output.open("x") as handle:
        json.dump(split, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": str(args.output), "patients":
                      {key: len(value) for key, value in split["patients"].items()},
                      "excluded_tasks": split["excluded_tasks"]}))


if __name__ == "__main__":
    main()
