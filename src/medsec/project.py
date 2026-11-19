"""Inspect and validate the MedSecBench project assets without calling an API."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .run_v0_5 import preflight
from .runtime import digest, validate_sample
from .splits import validate_sample_split


UPSTREAM_TASKS_SHA256 = "b6e89b2ef82f1bef27c5778a644a8a66c7b25738bbd6a48d03ab3e5182df6ca8"
UPSTREAM_TOOLS_SHA256 = "c977266db5eca75182c0d12cac1962b33ae6b5a54b9029ceb104e1a93b4c38c1"
ATTACK_DIRS = ("attacks_draft_v0_2", "attacks_additions_v0_3",
               "attacks_matrix_v0_4", "attacks_repair_v0_5")


def inspect(root: Path = Path("data/medsec")) -> dict:
    root = Path(root)
    upstream_tasks_path = root / "upstream/test_data_v2.json"
    tools_path = root / "upstream/funcs_v1.json"
    extended_path = root / "extended_tasks_v0_3.json"
    splits_path = root / "splits_v0_3.json"
    if digest(upstream_tasks_path.read_bytes()) != UPSTREAM_TASKS_SHA256:
        raise ValueError("upstream task snapshot fingerprint mismatch")
    if digest(tools_path.read_bytes()) != UPSTREAM_TOOLS_SHA256:
        raise ValueError("upstream tool snapshot fingerprint mismatch")
    upstream = json.loads(upstream_tasks_path.read_text())
    extended = json.loads(extended_path.read_text())
    tools = json.loads(tools_path.read_text())
    if len(upstream) != 300 or len(tools) != 9:
        raise ValueError("unexpected upstream task or tool count")
    upstream_by_id = {task["id"]: task for task in upstream}
    tasks = {task["id"]: task for task in extended}
    if len(upstream_by_id) != len(upstream) or len(tasks) != len(extended):
        raise ValueError("duplicate task ID")
    if len(extended) != 301 or any(tasks.get(task_id) != task for task_id, task in upstream_by_id.items()):
        raise ValueError("extended tasks must preserve all 300 upstream tasks and add one source task")
    split = json.loads(splits_path.read_text())
    if split["tasks_sha256"] != digest(extended_path.read_bytes()):
        raise ValueError("split/tasks fingerprint mismatch")
    files = sorted(path for folder in ATTACK_DIRS for path in (root / folder).glob("*.json"))
    if len(files) != 37:
        raise ValueError(f"expected 37 curated attacks, found {len(files)}")
    surfaces = Counter()
    goals = Counter()
    ids = set()
    for file in files:
        sample = json.loads(file.read_text())
        validate_sample(sample, tasks, root)
        validate_sample_split(sample, tasks, root, split)
        preflight(["--attack", str(file), "--tools", str(tools_path)])
        if sample["attack_id"] in ids:
            raise ValueError(f"duplicate attack ID: {sample['attack_id']}")
        ids.add(sample["attack_id"])
        surfaces.update({step["surface"] for step in sample["attack_steps"]})
        goals[sample["goal_id"]] += 1
    return {"upstream_tasks": len(upstream), "extended_tasks": len(extended),
            "upstream_tools": len(tools), "attack_tasks": len(files),
            "attack_surfaces": dict(sorted(surfaces.items())),
            "attack_goals": dict(sorted(goals.items())),
            "upstream_tasks_sha256": UPSTREAM_TASKS_SHA256,
            "upstream_tools_sha256": UPSTREAM_TOOLS_SHA256,
            "extended_tasks_sha256": digest(extended_path.read_bytes()),
            "splits_sha256": digest(splits_path.read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("data/medsec"))
    args = parser.parse_args()
    print(json.dumps(inspect(args.root), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
