"""Derive "given gold labels" copies of a split for the domain<->driver upper-bound experiment.

For each row, adds given_risk_domains (for task2b prompts *_v3) and given_risk_drivers
(for task2a prompts *_v3), copied from the row's own gold labels. run.py puts these keys
into the user payload only when present, so ordinary splits are unaffected.

Usage: python src/make_oracle_splits.py data/splits/train_val.jsonl [...]
Writes <name>_given.jsonl next to each input (gitignored like the other derived splits).
"""
import json
import sys
from pathlib import Path

for path in map(Path, sys.argv[1:]):
    out = path.with_name(path.stem + "_given.jsonl")
    with path.open() as src, out.open("w") as dst:
        for line in src:
            row = json.loads(line)
            row["given_risk_domains"] = row["risk_domains"]
            row["given_risk_drivers"] = row["risk_drivers"]
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(out)
