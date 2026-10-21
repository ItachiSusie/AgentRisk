"""Download train/dev from Hugging Face into data/raw and fill data/MANIFEST.json.

Usage: python src/download_data.py

If MANIFEST.json already pins a commit SHA, that revision is downloaded and the
file hashes are verified; otherwise the latest revision is used and recorded.
"""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "AgentRisk/agentrisk-data-2027"
FILES = ["train.jsonl", "dev.jsonl"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MANIFEST = DATA_DIR / "MANIFEST.json"


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def main():
    manifest = json.loads(MANIFEST.read_text())
    sha = manifest["hf_commit_sha"]
    if sha is None:
        info = json.loads(fetch(f"https://huggingface.co/api/datasets/{REPO}"))
        sha = info["sha"]

    raw_dir = DATA_DIR / "raw"
    raw_dir.mkdir(exist_ok=True)
    files = {}
    for name in FILES:
        content = fetch(f"https://huggingface.co/datasets/{REPO}/resolve/{sha}/data/{name}")
        digest = hashlib.sha256(content).hexdigest()
        pinned = manifest["files"][name]["sha256"]
        if pinned is not None and pinned != digest:
            raise SystemExit(f"{name}: SHA-256 {digest} does not match MANIFEST {pinned}")
        (raw_dir / name).write_bytes(content)
        rows = [json.loads(line) for line in content.decode("utf-8").splitlines() if line.strip()]
        files[name] = {"sha256": digest, "rows": len(rows), "ids": [r["example_id"] for r in rows]}
        print(f"{name}: {len(rows)} rows, sha256 {digest[:12]}")

    manifest["hf_commit_sha"] = sha
    manifest["downloaded_at"] = manifest["downloaded_at"] or datetime.now(timezone.utc).isoformat()
    manifest["files"] = {n: {"sha256": f["sha256"], "rows": f["rows"]} for n, f in files.items()}
    manifest["dev_example_ids"] = files["dev.jsonl"]["ids"]
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"revision {sha}; wrote {MANIFEST}")


if __name__ == "__main__":
    main()
