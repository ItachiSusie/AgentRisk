"""Run clean and attacked DeepSeek controls for one sealed MedSec split."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .runtime import digest
from .splits import validate_sample_split
from .lock import verify as verify_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attack-set", type=Path, required=True)
    parser.add_argument("--split", choices=("calibration", "frozen_test"), required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output-pairs", type=Path, required=True)
    parser.add_argument("--tasks", type=Path, default=Path("data/medsec/extended_tasks_v0_3.json"))
    parser.add_argument("--tools", type=Path, default=Path("data/medsec/upstream/funcs_v1.json"))
    parser.add_argument("--splits", type=Path, default=Path("data/medsec/splits_v0_3.json"))
    parser.add_argument("--attack-root", type=Path, default=Path("data/medsec"))
    parser.add_argument("--grader", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("results/medsec"))
    parser.add_argument("--only-task-id")
    parser.add_argument("--lock", type=Path, help="required for frozen_test; refuses any changed asset")
    args = parser.parse_args()
    if args.split == "frozen_test" and not args.lock:
        parser.error("frozen_test requires --lock")
    if args.lock:
        lock = json.loads(args.lock.read_text())
        verify_lock(lock)
        if lock.get("model") != "deepseek-flash":
            parser.error("unsupported locked model")
        if args.split == "frozen_test":
            if args.only_task_id or lock.get("frozen_batch_id") != args.batch_id or \
                    lock.get("frozen_pairs_path") != str(args.output_pairs.resolve()):
                parser.error("frozen batch arguments differ from the sealed protocol")
            for path in (args.attack_set, args.tasks, args.tools, args.splits, args.grader):
                if str(path.resolve()) not in lock["files_sha256"]:
                    parser.error(f"unlocked frozen input: {path}")
    if args.output_pairs.exists():
        parser.error("output pairs file already exists")
    tasks = {t["id"]: t for t in json.loads(args.tasks.read_text())}
    split = json.loads(args.splits.read_text())
    if split["tasks_sha256"] != digest(args.tasks.read_bytes()):
        parser.error("task fingerprint differs from split manifest")
    rows = [json.loads(line) for line in args.attack_set.read_text().splitlines() if line.strip()]
    selected = [r for r in rows if r["split"] == args.split and
                (not args.only_task_id or r["base_task_id"] == args.only_task_id)]
    if not selected:
        parser.error("no matching attack tasks")
    pairs = []
    common = ["--tasks", str(args.tasks), "--tools", str(args.tools), "--splits", str(args.splits),
              "--grader", str(args.grader), "--output-root", str(args.runs_root)]
    for row in selected:
        validate_sample_split(row, tasks, args.attack_root, split)
        task_id = row["base_task_id"]
        config = row.get("run_config", {})
        flags = ["--" + key.replace("_", "-") for key, value in config.items() if value]
        stem = f"{args.batch_id}-{task_id}"
        clean_id, attack_id = stem + "-clean", stem + "-attack"
        clean = [sys.executable, "-m", "src.medsec.run", *common,
                 "--task-id", task_id, "--run-id", clean_id, *flags]
        if row["attack_steps"][0]["surface"] == "malicious_user":
            clean += ["--requester-role", row["actor_role"],
                      "--authorization-scope", row["authorization_scope"],
                      "--user-message-file", str(args.attack_root / "payloads/clean_patient_portal_v0_4.txt")]
        attack_file = args.attack_root / "attacks_matrix_v0_4" / (row["attack_id"] + ".json")
        attacked = [sys.executable, "-m", "src.medsec.run", *common,
                    "--attack", str(attack_file), "--attack-root", str(args.attack_root),
                    "--run-id", attack_id, *flags]
        print(json.dumps({"task_id": task_id, "clean_run_id": clean_id,
                          "attack_run_id": attack_id}), flush=True)
        subprocess.run(clean, check=True)
        subprocess.run(attacked, check=True)
        pairs.append({"pair_id": row["attack_id"], "clean_run_id": clean_id,
                      "attack_run_id": attack_id})
    args.output_pairs.parent.mkdir(parents=True, exist_ok=True)
    with args.output_pairs.open("x") as handle:
        json.dump({"version": "v0.4", "split": args.split, "batch_id": args.batch_id,
                   "attack_set_sha256": digest(args.attack_set.read_bytes()), "pairs": pairs}, handle,
                  ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"pairs_file": str(args.output_pairs), "pairs": len(pairs)}))


if __name__ == "__main__":
    main()
