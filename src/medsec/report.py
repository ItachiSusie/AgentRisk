"""Recompute and aggregate explicitly paired MedSec runs without overwriting reports."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from .evaluate import recompute
from .runtime import digest
from .splits import validate_sample_split


def _rate(rows, predicate):
    return {"n": len(rows), "yes": sum(bool(predicate(row)) for row in rows)}


def build(pairs_path, runs_root, grader, tasks_path, splits_path):
    pairs_path, runs_root = Path(pairs_path), Path(runs_root)
    tasks = {t["id"]: t for t in json.loads(Path(tasks_path).read_text())}
    split = json.loads(Path(splits_path).read_text())
    if split["tasks_sha256"] != digest(Path(tasks_path).read_bytes()):
        raise ValueError("split/tasks fingerprint mismatch")
    pairs = json.loads(pairs_path.read_text())["pairs"]
    if len({p["pair_id"] for p in pairs}) != len(pairs):
        raise ValueError("duplicate pair id")
    rows = []
    for pair in pairs:
        clean_dir = runs_root / pair["clean_run_id"]
        attack_dir = runs_root / pair["attack_run_id"]
        cm = json.loads((clean_dir / "manifest.json").read_text())
        am = json.loads((attack_dir / "manifest.json").read_text())
        for field in ("task_id", "model", "fhir_base", "offline_patient_fixture",
                      "defense_prompt", "preload_skill", "presearch_document", "tasks_sha256", "tools_sha256",
                      "requester_role", "authorization_scope"):
            if cm.get(field) != am.get(field):
                raise ValueError(f"pair {pair['pair_id']} differs on {field}")
        if cm.get("attack_id") or not am.get("attack_id"):
            raise ValueError("pair must contain a clean and attacked run")
        if cm.get("offline_patient_fixture"):
            raise ValueError("fixture runs cannot enter official paired report")
        sample_path = Path(am["attack_path"])
        if digest(sample_path.read_bytes()) != am["attack_sha256"]:
            raise ValueError("attack sample changed")
        sample = json.loads(sample_path.read_text())
        validate_sample_split(sample, tasks, Path(am["attack_root"]), split)
        c = recompute(clean_dir, grader)
        a = recompute(attack_dir, grader)
        rows.append({"pair_id": pair["pair_id"], "task_id": cm["task_id"],
                     "split": sample["split"], "surface": "+".join(sorted({s["surface"] for s in sample["attack_steps"]})),
                     "goal": sample["goal_id"], "clean_run_id": cm["run_id"],
                     "attack_run_id": am["run_id"], "installed": a["security"]["installed"],
                     "exposed": a["security"]["exposed"],
                     "attack_success": a["security"]["attack_success"],
                     "clean_utility": c["official_utility_pass"],
                     "attack_utility": a["official_utility_pass"],
                     "clean_completed": c["official_utility_pass"] is not None,
                     "attack_completed": a["official_utility_pass"] is not None,
                     "clean_events_sha256": digest((clean_dir / "events.jsonl").read_bytes()),
                     "attack_events_sha256": digest((attack_dir / "events.jsonl").read_bytes())})
    buckets = defaultdict(list)
    for row in rows:
        for key in ("all", "split:" + row["split"], "surface:" + row["surface"], "goal:" + row["goal"]):
            buckets[key].append(row)
    summary = {}
    for key, group in sorted(buckets.items()):
        exposed = [row for row in group if row["exposed"]]
        summary[key] = {"pairs": len(group), "installed": _rate(group, lambda r: r["installed"]),
                        "exposed": _rate(group, lambda r: r["exposed"]),
                        "attack_success_overall": _rate(group, lambda r: r["attack_success"]),
                        "attack_success_given_exposure": _rate(exposed, lambda r: r["attack_success"]),
                        "clean_completed": _rate(group, lambda r: r["clean_completed"]),
                        "attack_completed": _rate(group, lambda r: r["attack_completed"]),
                        "clean_utility": _rate(group, lambda r: r["clean_utility"]),
                        "attack_utility": _rate(group, lambda r: r["attack_utility"])}
    return {"scope": "curated paired runs only; no population success-rate inference",
            "pairs_path": str(pairs_path.resolve()), "pairs_sha256": digest(pairs_path.read_bytes()),
            "split_sha256": digest(Path(splits_path).read_bytes()),
            "grader_sha256": digest(Path(grader).read_bytes()), "rows": rows, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("results/medsec"))
    parser.add_argument("--grader", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, default=Path("data/medsec/extended_tasks_v0_3.json"))
    parser.add_argument("--splits", type=Path, default=Path("data/medsec/splits_v0_3.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.pairs, args.runs_root, args.grader, args.tasks, args.splits)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": str(args.output), "pairs": len(result["rows"]),
                      "summary": result["summary"]["all"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
