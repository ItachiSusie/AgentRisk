"""Fetch metadata/split_manifest.jsonl (example_id -> split + scenario group) at the pinned revision.

Why: scenario groups are needed to split train into evolve/validation folds without leaking
a scenario (a risky trajectory and its safe counterpart) across folds. train.jsonl and
dev.jsonl do not carry the group field.

Usage: python src/fetch_split_manifest.py
Writes data/raw/split_manifest.jsonl and prints a coverage check against data/raw/*.jsonl
"""
import json
import hashlib
import urllib.request
from pathlib import Path

REPO = "AgentRisk/agentrisk-data-2027"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST = DATA_DIR / "MANIFEST.json"
OUT = DATA_DIR / "raw" / "split_manifest.jsonl"


def main():
    manifest = json.loads(MANIFEST.read_text())
    sha = manifest["hf_commit_sha"]
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{sha}/metadata/split_manifest.jsonl"
    with urllib.request.urlopen(url, timeout=60) as resp:
        content = resp.read()

    digest = hashlib.sha256(content).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(content)
    print(f"wrote {OUT} ({len(content)} bytes, sha256 {digest[:12]})")

    rows = [json.loads(l) for l in content.decode("utf-8").splitlines() if l.strip()]
    print("fields:", sorted(rows[0]))
    by_split = {}
    for r in rows:
        by_split.setdefault(r.get("split"), set()).add(r["example_id"])
    for split, ids in by_split.items():
        print(f"  {split}: {len(ids)} ids")

    for name in ("train", "dev"):
        local = {json.loads(l)["example_id"]
                 for l in (DATA_DIR / "raw" / f"{name}.jsonl").read_text().splitlines() if l.strip()}
        remote = by_split.get(name, set())
        print(f"{name}: local={len(local)} manifest={len(remote)} "
              f"missing_in_manifest={len(local - remote)} missing_locally={len(remote - local)}")


if __name__ == "__main__":
    main()
