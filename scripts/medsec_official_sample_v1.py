"""Run one pinned official MedAgentBench task from each of the ten families."""
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.medsec.v08.adapters.medagentbench import MedAgentBenchAdapter
from src.medsec.v08.cli import _run_med

TASK_IDS = [f"task{i}_1" for i in range(1, 11)]
SOURCE = Path("/tmp/medsec-upstream-medagentbench/src/server/tasks/medagentbench/__init__.py")
GRADER = ROOT / "data/medsec/private/refsol.py"


def main():
    root = ROOT / "results/medsec" / (datetime.now(timezone.utc).strftime("v19-official-sample-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    root.mkdir(parents=True, exist_ok=False)
    adapter = MedAgentBenchAdapter(SOURCE, GRADER)
    plan = {"format": "medsec-official-sample-v1", "run_id": root.name,
            "model": "deepseek-flash", "task_ids": TASK_IDS,
            "upstream_source": str(SOURCE), "grader": str(GRADER),
            "scope": "one original task per task1-task10 family; no attacks"}
    (root / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    for task_id in TASK_IDS:
        try:
            result = _run_med(adapter, task_id, "deepseek", "deepseek-flash", None,
                              ROOT, "none", root / "runs")
            row = {"task_id": task_id, "run_id": result["run_id"], "status": result["status"],
                   "official_utility_pass": result["official_utility_pass"],
                   "event_count": result["event_count"]}
        except Exception as exc:
            row = {"task_id": task_id, "error_type": type(exc).__name__, "error": str(exc)[:300]}
        with (root / "progress.jsonl").open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps({"batch_run_id": root.name, **row}, ensure_ascii=False), flush=True)
    rows = [json.loads(x) for x in (root / "progress.jsonl").read_text().splitlines()]
    summary = {"run_id": root.name, "planned": len(TASK_IDS), "recorded": len(rows),
               "with_run_id": sum(bool(x.get("run_id")) for x in rows),
               "official_utility_passes": sum(x.get("official_utility_pass") is True for x in rows),
               "rows": rows}
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}), flush=True)


if __name__ == "__main__":
    main()
