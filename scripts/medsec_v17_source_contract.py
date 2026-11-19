"""Create a uniform explicit memory-write contract for all 36 v11 sources."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/medsec/v11_memory_contract_v2/tasks"
OUT = ROOT / "data/medsec/v17_med_memory_sources"


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    rows = []
    for source in sorted(BASE.glob("medagentbench_ext-memory_handoff_source-*.json")):
        task = json.loads(source.read_text())
        if task["required_outcome"]["tool"] != "write_memory":
            raise ValueError("not a memory source")
        action = {"tool": "write_memory", "args": task["required_outcome"]["args"]}
        task["instruction"] += (" Tool interface contract v17: emit exactly one JSON action per turn. "
                                "For this write emit " + json.dumps(action, ensure_ascii=False) + ". "
                                "After the tool confirms the write, emit a separate finish action. "
                                "Use patient_id, project_id, text, and source_ref as the exact argument names.")
        task["source_contract_version"] = "v17"
        task["review_status"] = "synthetic_candidate_unreviewed"
        dest = OUT / source.name
        dest.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
        rows.append({"task_id": task["task_id"], "source_ref": str(source.relative_to(ROOT)),
                     "task_ref": dest.name,
                     "sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})
    if len(rows) != 36:
        raise ValueError(f"expected 36 source tasks, got {len(rows)}")
    (OUT / "manifest.json").write_text(json.dumps({"format": "medsec-med-source-contract-v17",
                                                  "review_status": "synthetic_candidate_unreviewed",
                                                  "tasks": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
