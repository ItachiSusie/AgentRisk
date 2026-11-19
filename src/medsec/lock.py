"""Seal the automated frozen-test protocol with source and data fingerprints."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import digest


def files_to_lock(attack_set, tasks, tools, splits, grader, calibration_report, attack_root):
    attack_set, attack_root = Path(attack_set), Path(attack_root)
    files = [attack_set, Path(tasks), Path(tools), Path(splits), Path(grader),
             Path(calibration_report), attack_root / "payloads/clean_patient_portal_v0_4.txt"]
    code = Path(__file__).resolve().parent
    files += [code / name for name in ("run.py", "runtime.py", "judge.py", "evaluate.py",
                                       "splits.py", "report.py", "run_matrix.py", "lock.py")]
    for row in (json.loads(line) for line in attack_set.read_text().splitlines() if line.strip()):
        if row["split"] != "frozen_test":
            continue
        files.append(attack_root / "attacks_matrix_v0_4" / (row["attack_id"] + ".json"))
        files += [attack_root / step["payload_ref"] for step in row["attack_steps"]]
        for reference in row.get("clean_artifact_refs", []):
            candidate = attack_root / reference
            if candidate.is_file():
                files.append(candidate)
    return sorted({path.resolve() for path in files})


def verify(lock):
    for name, sha in lock["files_sha256"].items():
        path = Path(name)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            raise ValueError(f"frozen lock mismatch: {name}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-set", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--splits", type=Path, required=True)
    parser.add_argument("--grader", type=Path, required=True)
    parser.add_argument("--calibration-report", type=Path, required=True)
    parser.add_argument("--attack-root", type=Path, required=True)
    parser.add_argument("--frozen-batch-id", required=True)
    parser.add_argument("--frozen-pairs-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    files = files_to_lock(args.attack_set, args.tasks, args.tools, args.splits, args.grader,
                          args.calibration_report, args.attack_root)
    lock = {"version": "v0.4", "status": "sealed automated protocol; clinical review remains separate",
            "model": "deepseek-flash", "temperature": 0, "max_tokens": 1800,
            "frozen_batch_id": args.frozen_batch_id,
            "frozen_pairs_path": str(args.frozen_pairs_path.resolve()),
            "files_sha256": {str(path): digest(path.read_bytes()) for path in files}}
    verify(lock)
    with args.output.open("x") as handle:
        json.dump(lock, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"path": str(args.output), "locked_files": len(files)}))


if __name__ == "__main__":
    main()
