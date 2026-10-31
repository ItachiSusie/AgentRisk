"""Split train into evolve / validation folds at the scenario-group level.

Why groups: items derived from the same scenario (a risky trajectory and its safe
counterpart) must stay in one fold, otherwise the validation score is inflated by leakage.
`data/raw/split_manifest.jsonl` provides example_id -> scenario_group (see
src/fetch_split_manifest.py).

Deterministic: groups are ordered by sha256(group), so the split is reproducible without
storing a seed.

Usage:
    python src/make_splits.py --target-val 100
Writes data/splits/train_evolve.json and data/splits/train_val.json
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def load_jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def dist(rows, field):
    c = Counter()
    for r in rows:
        v = r[field]
        for x in (v if isinstance(v, list) else [v]):
            c[x] += 1
    total = len(rows)
    return {k: v / total for k, v in c.most_common()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target-val", type=int, default=100)
    ap.add_argument("--max-overshoot", type=float, default=0.15)
    ap.add_argument("--check", action="store_true",
                    help="recompute and compare with the files on disk; write nothing")
    args = ap.parse_args()

    manifest = load_jsonl(RAW / "split_manifest.jsonl")
    train = {r["example_id"]: r for r in load_jsonl(RAW / "train.jsonl")}
    dev_ids = {r["example_id"] for r in manifest if r["split"] == "dev"}

    groups = {}
    for r in manifest:
        if r["split"] != "train":
            continue
        groups.setdefault(r["scenario_group"], []).append(r["example_id"])
    assert not (set(train) & dev_ids), "train/dev overlap"

    # Stratify by the group's majority severity so val keeps the same label mix as train,
    # then take groups in hash order inside each stratum until its quota is met.
    strata = {}
    for g, ids in groups.items():
        sev = Counter(str(train[i]["risk_severity"]) for i in ids).most_common(1)[0][0]
        strata.setdefault(sev, []).append(g)
    frac = args.target_val / len(train)
    cap = int(args.target_val * (1 + args.max_overshoot))

    val_ids, val_groups = [], []
    for sev in sorted(strata):
        quota = frac * sum(len(groups[g]) for g in strata[sev])
        taken = 0
        for g in sorted(strata[sev], key=h):
            if taken >= quota or len(val_ids) >= cap:
                break
            if len(val_ids) + len(groups[g]) > cap:
                continue
            val_ids.extend(groups[g])
            val_groups.append(g)
            taken += len(groups[g])
    val_set = set(val_ids)
    evolve_ids = [i for i in train if i not in val_set]

    out = ROOT / "data" / "splits"
    if args.check:
        drift = 0
        for name, ids in (("train_evolve", evolve_ids), ("train_val", val_ids)):
            path = out / f"{name}.json"
            if not path.exists():
                print(f"{name}: MISSING ({path})")
                drift += 1
                continue
            on_disk = json.loads(path.read_text())["example_ids"]
            if on_disk != ids:
                print(f"{name}: DRIFT ({len(set(on_disk) ^ set(ids))} ids differ)")
                drift += 1
            else:
                print(f"{name}: ok ({len(ids)} ids)")
        raise SystemExit(1 if drift else 0)
    out.mkdir(parents=True, exist_ok=True)
    for name, ids in (("train_evolve", evolve_ids), ("train_val", val_ids)):
        payload = {
            "n": len(ids),
            "groups": len(groups) - len(val_groups) if name == "train_evolve" else len(val_groups),
            "target_val": args.target_val,
            "manifest_sha256": hashlib.sha256((RAW / "split_manifest.jsonl").read_bytes()).hexdigest(),
            "train_sha256": hashlib.sha256((RAW / "train.jsonl").read_bytes()).hexdigest(),
            "example_ids": ids,
        }
        (out / f"{name}.json").write_text(json.dumps(payload, indent=2) + "\n")
        # materialized rows, so run.py can point --data-file at it
        with (out / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for i in ids:
                fh.write(json.dumps(train[i], ensure_ascii=False) + "\n")
        print(f"{name}: {len(ids)} samples, {payload['groups']} scenario groups -> {out / (name + '.json')}")

    print(f"\nval share: {len(val_ids) / len(train):.1%} of train")
    leaked = [g for g in val_groups if set(groups[g]) & set(evolve_ids)]
    print(f"leakage check: groups spanning both folds = {len(leaked)} (expect 0)")

    print("\nlabel balance (share of rows):")
    ev = [train[i] for i in evolve_ids]
    va = [train[i] for i in val_ids]
    for field in ("risk_severity",):
        print(f"  {field}:")
        de, dv = dist(ev, field), dist(va, field)
        for k in sorted(set(de) | set(dv)):
            print(f"    {k}: evolve {de.get(k, 0):.1%} / val {dv.get(k, 0):.1%}")


if __name__ == "__main__":
    main()
