"""Build a few-shot selection file for a non-dev query split (default: train_val).

The existing data/fewshot/*.json all map **dev** queries to **train** pools, so they cannot be
reused for validation runs: selecting examples from a pool that contains the query sample
itself would leak the answer into the prompt.

This script does the same selection as select_examples.py, but takes an explicit
query split and candidate pool split:
    query = data/splits/train_val.json      (107 samples)
    pool  = data/splits/train_evolve.json   (461 samples)

Usage:
    python src/select_examples_for_split.py --method bm25 --top-n 10
    python src/select_examples_for_split.py --method random --seed 0 --top-n 10
Writes data/fewshot/bm25_train_val_top10.json (or random_train_val_s0_top10.json).
"""
import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from common import load_jsonl
from select_examples import BM25_B, BM25_K1, interaction_action_text, interaction_text, select_bm25, select_random, sha256

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def ids_of(path):
    return json.loads(Path(path).read_text())["example_ids"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", choices=["random", "bm25", "bm25-action"], required=True)
    ap.add_argument("--query-split", default="train_val")
    ap.add_argument("--pool-split", default="train_evolve")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-name", default=None)
    args = ap.parse_args()

    query_path = DATA / "splits" / f"{args.query_split}.json"
    pool_path = DATA / "splits" / f"{args.pool_split}.json"
    query_ids, pool_ids = ids_of(query_path), ids_of(pool_path)
    overlap = set(query_ids) & set(pool_ids)
    if overlap:
        raise SystemExit(f"query/pool overlap: {len(overlap)} ids — refusing to leak")

    rows = {r["example_id"]: r for r in load_jsonl(DATA / "raw" / "train.jsonl")}
    missing = [i for i in query_ids + pool_ids if i not in rows]
    if missing:
        raise SystemExit(f"{len(missing)} ids not found in train.jsonl, e.g. {missing[:3]}")
    pool = [rows[i] for i in pool_ids]
    queries = [rows[i] for i in query_ids]

    if args.method == "random":
        selections = select_random(pool, queries, args.seed, args.top_n)
        out_name = args.out_name or f"random_{args.query_split}_s{args.seed}_top{args.top_n}.json"
        params = {"seed": args.seed,
                  "sampling": f"random.Random(f'{{seed}}:{{example_id}}').sample(pool_ids, {args.top_n})"}
    else:
        action = args.method == "bm25-action"
        selections = select_bm25(pool, queries, interaction_action_text if action else interaction_text, args.top_n)
        out_name = args.out_name or f"bm25{'_action' if action else ''}_{args.query_split}_top{args.top_n}.json"
        params = {
            "library": f"rank_bm25 {version('rank_bm25')}", "k1": BM25_K1, "b": BM25_B,
            "text_fields": ("formatted_interaction + proposed_action (the action counted twice)"
                            if action else "formatted_interaction"),
            "tokenizer": "lowercase, split on non-alphanumeric",
            "stopwords": "none", "ties": "earlier pool row first", "order": "descending similarity",
        }

    out = {
        "meta": {
            "method": args.method, "top_n": args.top_n, **params,
            "query_split": args.query_split, "pool_split": args.pool_split,
            "query_split_sha256": sha256(query_path), "pool_split_sha256": sha256(pool_path),
            "train_sha256": sha256(DATA / "raw" / "train.jsonl"),
            "n_query": len(query_ids), "n_pool": len(pool_ids),
        },
        "selections": selections,
    }
    out_path = DATA / "fewshot" / out_name
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    vals = [v for vs in selections.values() for v in vs]
    print(f"wrote {out_path.name}: {len(selections)} queries x {args.top_n} examples")
    print(f"  queries ⊆ {args.query_split}: {set(selections) <= set(query_ids)}")
    print(f"  pool ⊆ {args.pool_split}: {set(vals) <= set(pool_ids)}")
    print(f"  self-selected: {sum(1 for k, vs in selections.items() if k in vs)} (expect 0)")
    print(f"  sha256 {sha256(out_path)[:12]}")


if __name__ == "__main__":
    main()
