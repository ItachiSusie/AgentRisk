"""Split train_evolve into K cross-fitting folds at the scenario-group level.

Why: rules / prompt edits are proposed from K-1 folds and scored on the held-out fold, so
every train_evolve item gets an out-of-fold (OOF) score from a prompt that never saw it.
train_val stays a one-shot confirmation set; dev stays the final test.

Same conventions as src/make_splits.py:
- a scenario group (a risky trajectory and its safe counterpart) never spans two folds;
- groups are stratified by their majority risk_severity;
- deterministic: groups are ordered by sha256(group), no seed to store.

Assignment: groups are taken largest first (ties in hash order) — two groups hold 41 and
36 rows, so they must land in different folds. Each goes to the fold, among those still
under ceil(n/k)+2 rows, that has the fewest rows of the group's severity stratum (ties:
fewest rows overall, then lowest fold index).

Usage:
    python src/make_folds.py              # writes data/splits/train_evolve_folds.json (+ fold jsonl)
    python src/make_folds.py --check      # recompute and compare with the file on disk
Needs data/raw/split_manifest.jsonl (src/fetch_split_manifest.py) and data/splits/train_evolve.json.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SPLITS = ROOT / "data" / "splits"
OUT = SPLITS / "train_evolve_folds.json"


def load_jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(k):
    evolve = json.loads((SPLITS / "train_evolve.json").read_text())
    evolve_ids = evolve["example_ids"]
    evolve_set = set(evolve_ids)
    train = {r["example_id"]: r for r in load_jsonl(RAW / "train.jsonl")}
    manifest = load_jsonl(RAW / "split_manifest.jsonl")

    groups = {}
    for r in manifest:
        if r["example_id"] in evolve_set:
            groups.setdefault(r["scenario_group"], []).append(r["example_id"])
    covered = {i for ids in groups.values() for i in ids}
    assert covered == evolve_set, f"{len(evolve_set - covered)} train_evolve ids lack a scenario group"

    strata = {}
    for g, ids in groups.items():
        sev = Counter(train[i]["risk_severity"] for i in ids).most_common(1)[0][0]
        strata.setdefault(sev, []).append(g)

    sev_of = {g: sev for sev, gs in strata.items() for g in gs}
    cap = -(-len(evolve_ids) // k) + 2   # ceil(n/k) plus a little slack
    fold_groups = [[] for _ in range(k)]
    stratum_rows = [Counter() for _ in range(k)]
    total_rows = [0] * k
    # Largest groups first (a few groups hold 10-41 rows), then the many 1-2 row groups fill
    # in. Among folds with room under the cap, pick the one with the fewest rows of this
    # group's severity stratum; if none has room, the least-loaded fold.
    for g in sorted(groups, key=lambda g: (-len(groups[g]), h(g))):
        size, sev = len(groups[g]), sev_of[g]
        room = [j for j in range(k) if total_rows[j] + size <= cap]
        if room:
            f = min(room, key=lambda j: (stratum_rows[j][sev], total_rows[j], j))
        else:
            f = min(range(k), key=lambda j: (total_rows[j], j))
        fold_groups[f].append(g)
        stratum_rows[f][sev] += size
        total_rows[f] += size

    # keep each fold's ids in train_evolve order, so files diff cleanly
    order = {i: n for n, i in enumerate(evolve_ids)}
    folds = []
    for f in range(k):
        ids = sorted((i for g in fold_groups[f] for i in groups[g]), key=order.get)
        folds.append({"fold": f, "n": len(ids), "groups": len(fold_groups[f]),
                      "scenario_groups": sorted(fold_groups[f]), "example_ids": ids})
    payload = {
        "k": k,
        "n": len(evolve_ids),
        "source": "data/splits/train_evolve.json",
        "train_evolve_sha256": sha_file(SPLITS / "train_evolve.json"),
        "manifest_sha256": sha_file(RAW / "split_manifest.jsonl"),
        "train_sha256": sha_file(RAW / "train.jsonl"),
        "folds": folds,
    }
    return payload, train, groups


def report(payload, train, groups):
    seen = {}
    for fold in payload["folds"]:
        for g in fold["scenario_groups"]:
            seen.setdefault(g, set()).add(fold["fold"])
    spanning = sum(len(v) > 1 for v in seen.values())
    all_ids = [i for fold in payload["folds"] for i in fold["example_ids"]]
    print(f"k={payload['k']}  rows={len(all_ids)} (unique {len(set(all_ids))})  "
          f"groups={len(seen)}  groups spanning folds={spanning} (expect 0)")
    fields = [("risk_severity", None), ("risk_domains", 2), ("risk_drivers", 2)]
    sev_levels = sorted({train[i]["risk_severity"] for i in all_ids})
    print("fold   n  groups  severity " + "/".join(map(str, sev_levels)) + "   n_domains=2  n_drivers=2")
    for fold in payload["folds"]:
        rows = [train[i] for i in fold["example_ids"]]
        sev = Counter(r["risk_severity"] for r in rows)
        d2 = sum(len(r["risk_domains"]) == 2 for r in rows) / len(rows)
        r2 = sum(len(r["risk_drivers"]) == 2 for r in rows) / len(rows)
        print(f"{fold['fold']:>4} {fold['n']:>3} {fold['groups']:>7}  "
              + "/".join(f"{sev[s]:>3}" for s in sev_levels)
              + f"        {d2:5.1%}       {r2:5.1%}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--check", action="store_true",
                    help="recompute and compare with the file on disk; write nothing")
    args = ap.parse_args()

    payload, train, groups = build(args.k)
    if args.check:
        if not OUT.exists():
            print(f"MISSING {OUT}")
            raise SystemExit(1)
        on_disk = json.loads(OUT.read_text())
        same = [f["example_ids"] for f in on_disk["folds"]] == [f["example_ids"] for f in payload["folds"]]
        print("train_evolve_folds: ok" if same else "train_evolve_folds: DRIFT")
        raise SystemExit(0 if same else 1)

    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    # materialized rows per fold (gitignored like the other split jsonl files)
    for fold in payload["folds"]:
        held = SPLITS / f"train_evolve_fold{fold['fold']}.jsonl"
        with held.open("w", encoding="utf-8") as fh:
            for i in fold["example_ids"]:
                fh.write(json.dumps(train[i], ensure_ascii=False) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} and train_evolve_fold{{0..{args.k - 1}}}.jsonl")
    report(payload, train, groups)


if __name__ == "__main__":
    main()
