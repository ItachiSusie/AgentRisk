"""Run one v20 synthetic Med episode and write a recomputable run directory."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..v08.attack import load_attack
from ..v08.contracts import Events, sha256
from ..v08.models import DeepSeekTextModel
from . import episode as v20_episode
from .scoring import recompute, v20_code_hashes


def run_extension_v20(task_path: Path, model_name: str, attack_path: Path | None,
                      attack_root: Path, defense: str, output_root: Path,
                      memory_root: Path | None = None) -> dict:
    task = json.loads(Path(task_path).read_text())
    if task["benchmark_id"] != "medagentbench_ext":
        raise ValueError("synthetic Med extension task required")
    sample = payload = None
    if attack_path:
        sample, payload = load_attack(Path(attack_path), Path(attack_root),
                                      Events("preflight", "medagentbench_ext", task["task_id"]))
        if sample.get("task_id") != task["task_id"]:
            raise ValueError("attack/task mismatch")
    model = DeepSeekTextModel(model_name, json_mode=True)
    run_id = datetime.now(timezone.utc).strftime("v20-%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    output_dir = Path(output_root) / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    result = v20_episode.run_extension(task, model, run_id, workspace=output_dir / "workspace",
                                       attack=sample, payload=payload, defense_policy=defense,
                                       memory_root=memory_root)
    events_path = output_dir / "events.jsonl"
    events_path.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in result["events"]))
    outcome_path = output_dir / "outcome.json"
    outcome_path.write_text(json.dumps({"status": result["status"], "result": result["result"],
                                        "synthetic_utility_pass": result["synthetic_utility_pass"],
                                        "parse_failures": result["parse_failures"],
                                        "state_fingerprint": result["state_fingerprint"]},
                                       ensure_ascii=False, indent=2) + "\n")
    manifest = {"format": "medsec-v20", "run_id": run_id, "benchmark_id": "medagentbench_ext",
                "task_id": task["task_id"], "model": model_name, "defense": defense,
                "task_ref": str(Path(task_path).resolve()), "task_sha256": sha256(Path(task_path).read_bytes()),
                "events_sha256": sha256(events_path.read_bytes()),
                "outcome_sha256": sha256(outcome_path.read_bytes()),
                "attack_ref": str(Path(attack_path).resolve()) if attack_path else None,
                "attack_root": str(Path(attack_root).resolve()) if attack_path else None,
                "attack_sha256": sha256(Path(attack_path).read_bytes()) if attack_path else None,
                "v20_code_sha256": v20_code_hashes(),
                "response_meta_last": getattr(model, "last_response", None)}
    if memory_root:
        manifest["memory_root"] = str(Path(memory_root).resolve())
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return recompute(output_dir)
