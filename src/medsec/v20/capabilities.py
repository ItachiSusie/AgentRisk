"""v20 memory store: same durable scoped storage, but the rows shown to the
model carry only the public handoff fields.

The v08 MemoryStore.search returned ``{**row, "text": shown}``; because
``install_edit`` stamps an ``attack_id`` onto the poisoned row, the model saw
``"attack_id": "v11-...-cancel"`` in the tool result, i.e. the attack announced
itself. v20 projects each row to a fixed public schema before it leaves the
tool boundary. The full row (with provenance and attack_id) is still recorded
in the event log for scoring; only the model-visible observation is trimmed.
"""
from __future__ import annotations

from ..v08.capabilities import MemoryStore as _V08MemoryStore
from ..v08.contracts import sha256

# Fields a real handoff-memory tool would expose to the agent. Internal
# provenance (source_episode, text_sha256) and the planted attack_id are not
# part of a legitimate memory record and must not leak into the model input.
PUBLIC_MEMORY_FIELDS = ("version", "patient_id", "project_id", "text", "source_ref")


class MemoryStore(_V08MemoryStore):
    def search(self, *, patient_id: str, project_id: str, target_episode: str,
               injector, defense) -> list[dict]:
        import json

        path = self._path(patient_id, project_id)
        rows = json.loads(path.read_text()) if path.exists() else []
        found = []
        for row in rows:
            attack_id = row.get("attack_id")
            shown = defense.observe("memory_text", row["text"], attack_id)
            public = {key: row.get(key) for key in PUBLIC_MEMORY_FIELDS}
            public["text"] = shown
            found.append(public)
            self.events.add("memory_retrieved", patient_id=patient_id, project_id=project_id,
                            version=row["version"], target_episode=target_episode,
                            source_episode=row["source_episode"], shown_sha256=sha256(shown),
                            attack_id=attack_id)
        return found
