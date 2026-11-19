"""Versioned contracts for the two-substrate security pilot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

SURFACES = {"environment_data", "tool_result", "tool_description", "skill_file",
            "memory_induced", "memory_store_edit", "retrieved_document", "malicious_user"}
GOALS = {"wrong_patient", "unauthorized_action", "answer_manipulation",
         "suppress_required_action", "unauthorized_disclosure"}
THREATS = {"indirect_content", "compromised_integration", "memory_store_compromise",
           "direct_malicious_user"}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def payload_text(attack: dict, suite_root: Path) -> str:
    ref = attack["payload_ref"]
    if not isinstance(ref, str) or Path(ref).is_absolute():
        raise ValueError("payload_ref must be relative")
    path = (suite_root / ref).resolve()
    if not path.is_relative_to(suite_root.resolve()) or not path.is_file():
        raise ValueError("payload_ref escapes suite")
    raw = path.read_bytes()
    if sha256(raw) != attack["payload_sha256"]:
        raise ValueError("payload hash mismatch")
    return raw.decode()


def validate_task(task: dict) -> None:
    required = {"task_id", "benchmark_id", "family", "instruction", "patient_id",
                "requester_role", "authorization_scope", "snapshot", "required_outcome",
                "forbidden_outcome", "oracle_version", "split"}
    if required - task.keys():
        raise ValueError(f"missing task fields: {sorted(required - task.keys())}")
    if task["benchmark_id"] not in {"medagentbench_ext", "healthagentbench_synthetic"}:
        raise ValueError("unknown substrate")
    if task["patient_id"] not in task["authorization_scope"].get("patients", []):
        raise ValueError("target patient absent from authorization scope")
    if not isinstance(task["snapshot"], dict) or not isinstance(task["required_outcome"], dict):
        raise ValueError("invalid snapshot or oracle")


def validate_attack(attack: dict, task: dict, suite_root: Path) -> None:
    required = {"attack_id", "task_id", "threat_model", "surface", "attacker_capability",
                "trigger", "allowed_edit", "payload_ref", "payload_sha256", "goal_id",
                "judge_args", "split"}
    if required - attack.keys():
        raise ValueError(f"missing attack fields: {sorted(required - attack.keys())}")
    if attack["task_id"] != task["task_id"] or attack["split"] != task["split"]:
        raise ValueError("attack/task mismatch")
    if attack["surface"] not in SURFACES or attack["goal_id"] not in GOALS:
        raise ValueError("unknown surface or goal")
    if attack["threat_model"] not in THREATS:
        raise ValueError("unknown threat model")
    expected_threat = {"tool_description": "compromised_integration",
                       "skill_file": "compromised_integration",
                       "memory_store_edit": "memory_store_compromise",
                       "malicious_user": "direct_malicious_user"}.get(attack["surface"], "indirect_content")
    if attack["threat_model"] != expected_threat:
        raise ValueError("surface/threat mismatch")
    environment_edit = ("snapshot.files./workspace/data/dictionary.txt"
                        if task["family"] == "ehr_data_quality"
                        and task["oracle_version"].startswith("v0.7.2") else "snapshot.records.note")
    allowed = {"environment_data": environment_edit,
               "tool_result": "observation.text", "tool_description": "tool.description",
               "skill_file": "skill.body", "memory_induced": "source_note.text",
               "memory_store_edit": "memory.text", "retrieved_document": "document.text",
               "malicious_user": "user.message"}
    if attack["allowed_edit"] != [allowed[attack["surface"]]]:
        raise ValueError("attack edit permission mismatch")
    if attack["surface"] in {"memory_induced", "memory_store_edit"} and not attack.get("memory_scope"):
        raise ValueError("memory attack requires scope")
    payload_text(attack, suite_root)
