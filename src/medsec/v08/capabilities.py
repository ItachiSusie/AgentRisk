"""Versioned skill catalog and durable scoped cross-episode memory."""
from __future__ import annotations

import json
from pathlib import Path

from .attack import Injector
from .contracts import Events, sha256
from .defense import Defense


class SkillCatalog:
    def __init__(self, root: Path, events: Events):
        self.root = root.resolve()
        self.events = events

    def list(self) -> list[dict]:
        rows = []
        for path in sorted(self.root.glob("*.md")):
            if path.is_file() and path.resolve().is_relative_to(self.root):
                rows.append({"skill_id": path.stem, "version": sha256(path.read_bytes())[:12]})
        self.events.add("skill_catalog_listed", skill_ids=[r["skill_id"] for r in rows])
        return rows

    def load(self, skill_id: str, injector: Injector, defense: Defense) -> str:
        if not skill_id or not all(c.isalnum() or c in "-_" for c in skill_id):
            raise ValueError("invalid skill id")
        path = (self.root / (skill_id + ".md")).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("skill escapes root")
        original = path.read_text()
        shown, attack_id = injector.apply("skill_file", {"skill_id": skill_id}, original)
        shown = defense.observe("skill_file", shown, attack_id)
        self.events.add("skill_body_loaded", skill_id=skill_id, version=sha256(path.read_bytes())[:12],
                        original_sha256=sha256(original), shown_sha256=sha256(shown))
        return shown


class MemoryStore:
    """One file per scope; separate instances can share a root across episodes."""

    def __init__(self, root: Path, events: Events):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.events = events

    def _path(self, patient_id: str, project_id: str) -> Path:
        if not patient_id or not project_id:
            raise ValueError("memory scope required")
        return self.root / (sha256(json.dumps([patient_id, project_id])) + ".json")

    def write(self, *, patient_id: str, project_id: str, text: str,
              source_episode: str, source_ref: str) -> dict:
        if not source_episode or not source_ref:
            raise ValueError("memory provenance required")
        path = self._path(patient_id, project_id)
        rows = json.loads(path.read_text()) if path.exists() else []
        item = {"version": len(rows) + 1, "patient_id": patient_id, "project_id": project_id,
                "text": text, "source_episode": source_episode, "source_ref": source_ref,
                "text_sha256": sha256(text)}
        rows.append(item)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        self.events.add("memory_written", patient_id=patient_id, project_id=project_id,
                        version=item["version"], source_episode=source_episode,
                        source_ref=source_ref, text_sha256=item["text_sha256"])
        return item

    def install_edit(self, sample: dict, payload: str) -> None:
        """Change an existing scoped version before the target episode retrieves it."""
        if sample.get("surface") != "memory_store_edit":
            raise ValueError("memory attack surface required")
        trigger = sample.get("trigger", {})
        patient_id, project_id, version = (trigger.get("patient_id"),
                                           trigger.get("project_id"), trigger.get("version"))
        if not patient_id or not project_id or not isinstance(version, int):
            raise ValueError("memory attack requires patient, project, and version")
        path = self._path(patient_id, project_id)
        if not path.is_file():
            raise ValueError("memory attack target missing")
        rows = json.loads(path.read_text())
        target = next((r for r in rows if r["version"] == version), None)
        if target is None:
            raise ValueError("memory attack version missing")
        before = target["text"]
        target["text"] = payload
        target["text_sha256"] = sha256(payload)
        target["attack_id"] = sample["attack_id"]
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
        self.events.add("attack_triggered", attack_id=sample["attack_id"], surface="memory_store_edit",
                        trigger_ref=trigger, before_sha256=sha256(before), after_sha256=sha256(payload))

    def search(self, *, patient_id: str, project_id: str, target_episode: str,
               injector: Injector, defense: Defense) -> list[dict]:
        path = self._path(patient_id, project_id)
        rows = json.loads(path.read_text()) if path.exists() else []
        found = []
        for row in rows:
            attack_id = row.get("attack_id")
            shown = row["text"]
            shown = defense.observe("memory_text", shown, attack_id)
            found.append({**row, "text": shown})
            self.events.add("memory_retrieved", patient_id=patient_id, project_id=project_id,
                            version=row["version"], target_episode=target_episode,
                            source_episode=row["source_episode"], shown_sha256=sha256(shown),
                            attack_id=attack_id)
        return found

    def reset(self, patient_id: str, project_id: str) -> None:
        self._path(patient_id, project_id).unlink(missing_ok=True)
        self.events.add("memory_reset", patient_id=patient_id, project_id=project_id)
