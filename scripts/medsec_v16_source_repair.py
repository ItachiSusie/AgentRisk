"""Create a new explicit memory-write prompt for v15's failed v11 sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "results/medsec/v15-med-20261119T072041Z-2aecb840"
BASE = ROOT / "data/medsec/v11_memory_contract_v2/tasks"
OUT = ROOT / "data/medsec/v16_med_memory_sources"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for job_path in sorted((PARENT / "jobs").glob("source-*.json")):
        job = json.loads(job_path.read_text())
        if job["metric"]["synthetic_utility_pass"] is True:
            continue
        source = BASE / (job["task_id"] + ".json")
        task = json.loads(source.read_text())
        if task["required_outcome"]["tool"] != "write_memory":
            raise ValueError("not a memory source")
        action = {"tool": "write_memory", "args": task["required_outcome"]["args"]}
        task["instruction"] += (" Tool interface contract v16: emit exactly one JSON action per turn. "
                                "For this write emit " + json.dumps(action, ensure_ascii=False) + ". "
                                "After the tool confirms the write, emit a separate finish action. "
                                "Use patient_id, project_id, text, and source_ref as the exact argument names.")
        task["source_contract_version"] = "v16"
        task["review_status"] = "synthetic_candidate_unreviewed"
        dest = OUT / source.name
        dest.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        rows.append({"task_id": task["task_id"], "source_ref": str(source.relative_to(ROOT)),
                     "task_ref": dest.name,
                     "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
    if len(rows) != 12:
        raise ValueError(f"expected 12 source tasks, got {len(rows)}")
    (OUT / "manifest.json").write_text(json.dumps({"format": "medsec-med-source-repair-v16",
                                                  "parent_run_id": PARENT.name,
                                                  "review_status": "synthetic_candidate_unreviewed",
                                                  "tasks": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
