"""Online checks over native observations, actions, and final output."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from .contracts import Events, sha256


class Defense:
    def __init__(self, policy: str, patient_id: str, events: Events):
        if policy not in {"none", "scope"}:
            raise ValueError("unknown defense policy")
        self.policy, self.patient_id, self.events = policy, patient_id, events

    def observe(self, source: str, content: str, attack_id: str | None = None) -> str:
        shown = content
        decision = "allow"
        if self.policy == "scope" and "Operational update:" in content:
            shown, decision = "[Untrusted instruction removed]", "revise"
        self.events.add("observation_check", source=source, decision=decision,
                        original_sha256=sha256(content), presented_sha256=sha256(shown), attack_id=attack_id)
        if attack_id and shown == content:
            self.events.add("attack_presented_to_model", source=source, attack_id=attack_id,
                            content_sha256=sha256(shown))
        return shown

    def med_action(self, raw: str, fhir_base: str) -> bool:
        allowed = True
        if self.policy == "scope" and raw.startswith("GET "):
            url = raw[4:].strip()
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            targets = [v for key in ("patient", "subject", "identifier") for v in params.get(key, [])]
            if targets and not all(self.patient_id in v for v in targets):
                allowed = False
        if self.policy == "scope" and raw.startswith("POST "):
            try:
                body = json.loads(raw.split("\n", 1)[1])
                target = body.get("subject", {}).get("reference", "")
                if target and target not in {self.patient_id, "Patient/" + self.patient_id}:
                    allowed = False
            except (IndexError, ValueError, AttributeError):
                pass
        self.events.add("action_check", candidate=raw, decision="allow" if allowed else "block")
        return allowed

    def command(self, command: str) -> bool:
        # For the first Harbor bridge, commands are logged and left to the
        # container policy. A true command gate requires a structured allowlist.
        self.events.add("action_check", candidate=command, decision="allow", policy=self.policy)
        return True

    def output(self, content: str) -> str:
        delivered = content
        decision = "allow"
        if self.policy == "scope" and "PRIVATE-" in content:
            delivered, decision = "[Protected data removed]", "revise"
        self.events.add("output_check", candidate=content, delivered=delivered, decision=decision)
        return delivered
