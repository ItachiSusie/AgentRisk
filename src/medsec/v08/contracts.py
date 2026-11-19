"""Versioned events, artifact hashes, and upstream lock checks."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT / "data/medsec/v08/upstream.lock.json"


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def check_file(path: Path, expected: str) -> None:
    if not path.is_file() or sha256(path.read_bytes()) != expected:
        raise ValueError(f"missing or changed locked artifact: {path}")


def tree_hash(folder: Path) -> str:
    if not folder.is_dir():
        raise ValueError(f"task directory missing: {folder}")
    rows = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink in locked task directory: {path}")
        if path.is_file():
            rows.append((str(path.relative_to(folder)), sha256(path.read_bytes())))
    return sha256(canonical(rows))


def load_lock() -> dict:
    lock = json.loads(LOCK.read_text())
    check_file(ROOT / "data/medsec/upstream/test_data_v2.json", lock["medagentbench"]["task_sha256"])
    check_file(ROOT / "data/medsec/upstream/funcs_v1.json", lock["medagentbench"]["tool_sha256"])
    return lock


@dataclass
class Events:
    run_id: str
    benchmark_id: str
    episode_id: str
    items: list[dict] = field(default_factory=list)

    def add(self, kind: str, **fields: object) -> dict:
        row = {"schema_version": "medsec-v08-events-1", "run_id": self.run_id,
               "benchmark_id": self.benchmark_id, "episode_id": self.episode_id,
               "seq": len(self.items) + 1, "timestamp": datetime.now(timezone.utc).isoformat(),
               "kind": kind, **fields}
        self.items.append(row)
        return row


def code_hashes() -> dict[str, str]:
    folder = Path(__file__).parent
    return {str(path.relative_to(folder)): sha256(path.read_bytes())
            for path in sorted(folder.rglob("*.py"))}
