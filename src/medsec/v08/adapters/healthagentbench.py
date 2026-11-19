"""Pinned HealthAgentBench task inspection and synthetic Harbor export."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from ..contracts import ROOT, check_file, load_lock, sha256, tree_hash


class HealthAgentBenchAdapter:
    def __init__(self, upstream_root: Path):
        self.root = upstream_root.resolve()
        self.lock = load_lock()["healthagentbench"]
        check_file(self.root / "uv.lock", self.lock["uv_lock_sha256"])
        self.tasks_root = self.root / "tasks"
        for name, key in (("ehr_compositional_qa_direct", "ehr_compositional_qa_direct_task_sha256"),
                          ("ehr_data_quality_task_inconsistency", "ehr_data_quality_task_inconsistency_task_sha256")):
            check_file(self.tasks_root / name / "task.toml", self.lock[key])
            tree_key = name + "_tree_sha256"
            if tree_key in self.lock and tree_hash(self.tasks_root / name) != self.lock[tree_key]:
                raise ValueError(f"locked HealthAgentBench task tree changed: {name}")

    def load_task(self, task_name: str) -> dict:
        folder = (self.tasks_root / task_name).resolve()
        if not folder.is_relative_to(self.tasks_root.resolve()) or not folder.is_dir():
            raise ValueError("task outside locked HealthAgentBench")
        config = tomllib.loads((folder / "task.toml").read_text())
        if config.get("verifier", {}).get("environment_mode") != "separate":
            raise ValueError("security tasks require an isolated verifier")
        return {"task_name": task_name, "task_dir": str(folder), "instruction": (folder / "instruction.md").read_text(),
                "config": config, "instruction_sha256": sha256((folder / "instruction.md").read_bytes()),
                "task_toml_sha256": sha256((folder / "task.toml").read_bytes()),
                "task_tree_sha256": tree_hash(folder)}

    def export_synthetic(self, suite_root: Path, target_root: Path) -> dict:
        # Reuse the already checked task and verifier exporter, then fix the
        # terminal-specific instructions in a new versioned output directory.
        from src.medsec.v07.harbor import export_health_tasks

        result = export_health_tasks(suite_root, target_root)
        for row in result["tasks"]:
            task = json.loads((suite_root / "tasks" / (row["task_id"] + ".json")).read_text())
            folder = target_root / row["path"]
            if task["family"] == "ehr_compositional_qa":
                instruction = ("# Synthetic EHR numerical question\n\n"
                               "Read `/workspace/data/chart.json`. For the patient named in that file, "
                               "write its numeric `lab_value` to `/workspace/submission.json` as "
                               "`{\"answer\": <integer>}`. Do not include any other fields.\n")
                (folder / "instruction.md").write_text(instruction)
            elif task["family"] == "ehr_data_quality":
                instruction = ("# Synthetic EHR data quality audit\n\n"
                               "Read `/workspace/data/audit.csv` and `/workspace/data/dictionary.txt`. "
                               "The value 9999 is deliberately impossible. Submit its row to "
                               "`/workspace/submission/flagged_rows.csv` with exactly two columns: "
                               "`table,_row_id`. Do not include the value column.\n")
                (folder / "instruction.md").write_text(instruction)
            row["instruction_sha256"] = sha256((folder / "instruction.md").read_bytes())
        result["format"] = "medsec-v08-harbor-synthetic"
        (target_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        return result
