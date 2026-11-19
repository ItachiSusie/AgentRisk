"""Run all curated MedSec attacks with matched clean DeepSeek controls.

This is a diagnostic retest. It never replaces sealed calibration or frozen
results; each invocation requires a new batch ID and new run directories.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .runtime import digest, validate_sample
from .splits import validate_sample_split
from .run_v0_5 import preflight

SAMPLE_DIRS = ("attacks_draft_v0_2", "attacks_additions_v0_3",
               "attacks_matrix_v0_4", "attacks_repair_v0_5")


def _sample_files(root):
    return sorted(path for folder in SAMPLE_DIRS for path in (root / folder).glob("*.json"))


def _flags(sample):
    surfaces = {step["surface"] for step in sample["attack_steps"]}
    config = sample.get("run_config", {})
    enabled = {key for key, value in config.items() if value}
    if "skill_file" in surfaces:
        enabled.add("preload_skill")
    if "retrieved_document" in surfaces:
        enabled.add("presearch_document")
    if "memory_store_edit" in surfaces:
        enabled.add("seed_default_memory")
    return ["--" + key.replace("_", "-") for key in sorted(enabled)]


def _clean_extra(sample, root):
    surfaces = {step["surface"] for step in sample["attack_steps"]}
    if "malicious_user" in surfaces:
        return ["--requester-role", sample["actor_role"],
                "--authorization-scope", str(sample["authorization_scope"]),
                "--user-message-file", str(root / "payloads/clean_patient_portal_v0_4.txt")]
    if "memory_induced" in surfaces:
        extra = ["--source-task-id", sample["source_task_id"]]
        for ref in sample.get("clean_artifact_refs", []):
            path = root / ref
            if path.is_file():
                extra += ["--source-note-file", str(path)]
                break
        return extra
    return []


def _run(command, result_dir):
    if (result_dir / "result.json").is_file():
        return {"status": "existing", "result": json.loads((result_dir / "result.json").read_text())}
    if result_dir.exists():
        return {"status": "incomplete_existing_run", "error": "directory exists without result.json"}
    try:
        process = subprocess.run(command, text=True, capture_output=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "runner exceeded 900 seconds"}
    if process.returncode != 0:
        return {"status": "runner_error", "error": process.stderr[-1200:]}
    if not (result_dir / "result.json").is_file():
        return {"status": "missing_result", "error": process.stdout[-1200:]}
    return {"status": "completed", "result": json.loads((result_dir / "result.json").read_text())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--attack-root", type=Path, default=Path("data/medsec"))
    parser.add_argument("--tasks", type=Path, default=Path("data/medsec/extended_tasks_v0_3.json"))
    parser.add_argument("--tools", type=Path, default=Path("data/medsec/upstream/funcs_v1.json"))
    parser.add_argument("--splits", type=Path, default=Path("data/medsec/splits_v0_3.json"))
    parser.add_argument("--grader", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, default=Path("results/medsec"))
    parser.add_argument("--output-pairs", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-flash")
    args = parser.parse_args()
    if args.output_pairs.exists():
        parser.error("output pairs file already exists")
    root = args.attack_root
    files = _sample_files(root)
    if len(files) != 37:
        parser.error(f"expected 37 curated samples, found {len(files)}")
    tasks = {task["id"]: task for task in json.loads(args.tasks.read_text())}
    split = json.loads(args.splits.read_text())
    if split["tasks_sha256"] != digest(args.tasks.read_bytes()):
        parser.error("split/tasks fingerprint mismatch")
    samples = []
    for file in files:
        sample = json.loads(file.read_text())
        validate_sample(sample, tasks, root)
        validate_sample_split(sample, tasks, root, split)
        preflight(["--attack", str(file), "--tools", str(args.tools)])
        samples.append((file, sample))
    if len({sample["attack_id"] for _, sample in samples}) != len(samples):
        parser.error("duplicate attack ID")
    common = ["--tasks", str(args.tasks), "--tools", str(args.tools),
              "--splits", str(args.splits), "--grader", str(args.grader),
              "--output-root", str(args.runs_root), "--model", args.model]
    records = []
    for index, (file, sample) in enumerate(samples, 1):
        stem = args.batch_id + "__" + sample["attack_id"]
        clean_id, attack_id = stem + "__clean", stem + "__attack"
        flags = _flags(sample)
        clean = [sys.executable, "-m", "src.medsec.run_v0_5", *common,
                 "--task-id", sample["base_task_id"], "--run-id", clean_id,
                 *flags, *_clean_extra(sample, root)]
        attacked = [sys.executable, "-m", "src.medsec.run_v0_5", *common,
                    "--attack", str(file), "--attack-root", str(root),
                    "--run-id", attack_id, *flags]
        print(json.dumps({"index": index, "total": len(samples),
                          "attack_id": sample["attack_id"], "phase": "clean"}), flush=True)
        clean_result = _run(clean, args.runs_root / clean_id)
        print(json.dumps({"index": index, "total": len(samples),
                          "attack_id": sample["attack_id"], "phase": "attack"}), flush=True)
        attack_result = _run(attacked, args.runs_root / attack_id)
        records.append({"pair_id": sample["attack_id"], "clean_run_id": clean_id,
                        "attack_run_id": attack_id, "clean_status": clean_result["status"],
                        "attack_status": attack_result["status"],
                        "clean_official_utility": clean_result.get("result", {}).get("official_utility_pass"),
                        "attack_official_utility": attack_result.get("result", {}).get("official_utility_pass"),
                        "attack_success": attack_result.get("result", {}).get("security", {}).get("attack_success"),
                        "attack_exposed": attack_result.get("result", {}).get("security", {}).get("exposed")})
        print(json.dumps(records[-1], ensure_ascii=False), flush=True)
    args.output_pairs.parent.mkdir(parents=True, exist_ok=True)
    with args.output_pairs.open("x") as handle:
        json.dump({"version": "v0.5-diagnostic", "batch_id": args.batch_id,
                   "model": args.model, "tasks_sha256": digest(args.tasks.read_bytes()),
                   "tools_sha256": digest(args.tools.read_bytes()),
                   "splits_sha256": digest(args.splits.read_bytes()),
                   "grader_sha256": digest(args.grader.read_bytes()),
                   "pairs": records}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"pairs_file": str(args.output_pairs), "samples": len(records),
                      "completed_pairs": sum(r["clean_status"] in {"completed", "existing"}
                                             and r["attack_status"] in {"completed", "existing"}
                                             for r in records)}), flush=True)


if __name__ == "__main__":
    main()
