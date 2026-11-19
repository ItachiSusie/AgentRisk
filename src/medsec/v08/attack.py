"""One-shot, permission checked attack application at native boundaries."""
from __future__ import annotations

from pathlib import Path

from .contracts import Events, sha256

ALLOWED = {"fhir_response": "response_body", "tool_result": "stdout",
           "environment_file": "workspace_file",
           "malicious_user": "user_message", "skill_file": "skill_body",
           "memory_store_edit": "memory_text"}


def load_attack(path: Path, root: Path, events: Events) -> tuple[dict, str]:
    import json

    root = root.resolve()
    path = path.resolve()
    if not path.is_relative_to(root):
        raise ValueError("attack file escapes root")
    sample = json.loads(path.read_text())
    if sample.get("surface") not in ALLOWED or sample.get("allowed_edit") != [ALLOWED[sample["surface"]]]:
        raise ValueError("attack permission mismatch")
    ref = Path(sample["payload_ref"])
    if ref.is_absolute():
        raise ValueError("absolute payload_ref")
    payload_path = (root / ref).resolve()
    if not payload_path.is_relative_to(root) or not payload_path.is_file():
        raise ValueError("payload escapes root")
    payload = payload_path.read_text()
    if sha256(payload) != sample["payload_sha256"]:
        raise ValueError("payload changed")
    events.add("attack_installed", attack_id=sample["attack_id"], surface=sample["surface"],
               payload_sha256=sample["payload_sha256"], allowed_edit=sample["allowed_edit"])
    return sample, payload


class Injector:
    def __init__(self, sample: dict | None, payload: str | None, events: Events):
        self.sample, self.payload, self.events = sample, payload, events
        self.used = False

    def apply(self, surface: str, target: dict, original: str) -> tuple[str, str | None]:
        sample = self.sample
        if not sample or self.used or sample["surface"] != surface:
            return original, None
        trigger = sample.get("trigger", {})
        if any(target.get(k) != v for k, v in trigger.items()):
            return original, None
        self.used = True
        self.events.add("attack_triggered", attack_id=sample["attack_id"], surface=surface,
                        trigger_ref=target, before_sha256=sha256(original), after_sha256=sha256(self.payload or ""))
        return self.payload or "", sample["attack_id"]
