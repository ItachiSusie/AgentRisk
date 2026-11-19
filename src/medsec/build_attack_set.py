"""Validate curated attack tasks and freeze them as a JSONL attack set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import validate_sample
from .splits import validate_sample_split


def build(source_dir, tasks_path, attack_root, output, splits_path=None):
    tasks = {row["id"]: row for row in json.loads(Path(tasks_path).read_text())}
    split = json.loads(Path(splits_path).read_text()) if splits_path else None
    files = sorted(Path(source_dir).glob("*.json"))
    if not files:
        raise ValueError("no attack task files")
    records = []
    ids = set()
    for path in files:
        row = json.loads(path.read_text())
        validate_sample(row, tasks, Path(attack_root))
        if split:
            validate_sample_split(row, tasks, attack_root, split)
        if row["attack_id"] in ids:
            raise ValueError(f"duplicate attack_id: {row['attack_id']}")
        ids.add(row["attack_id"])
        decoy = row.get("judge_args", {}).get("decoy_patient")
        if decoy and decoy == tasks[row["base_task_id"]].get("eval_MRN"):
            raise ValueError(f"decoy equals target patient: {path}")
        records.append(row)
    versions = {r["attack_set_version"] for r in records}
    if len(versions) != 1:
        raise ValueError("one attack set must have one version")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return {"version": versions.pop(), "tasks": len(records), "path": str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--attack-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--splits", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source_dir, args.tasks, args.attack_root, args.output, args.splits)))


if __name__ == "__main__":
    main()
