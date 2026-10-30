"""Pick few-shot examples from train for every dev sample and write data/fewshot/<name>.json.

Usage:
    python src/select_examples.py --method random --seed 0   -> data/fewshot/random_seed0.json
    python src/select_examples.py --method bm25              -> data/fewshot/bm25_dev_top10.json
    python src/select_examples.py --method bm25-action       -> data/fewshot/bm25_action_dev_top10.json
    python src/select_examples.py --method bm25 --top-n 20   -> data/fewshot/bm25_dev_top20.json

Each output maps a dev example_id to TOP_N (default 10) train example_ids. k<=top_n uses
the first k, so the subsets are nested. For bm25 the list is ordered by descending similarity.
bm25 matches on formatted_interaction only; bm25-action also appends proposed_action.
Selection uses text only; no label is read.
"""
import argparse
import hashlib
import json
import random
import re
from importlib.metadata import version
from pathlib import Path

from rank_bm25 import BM25Okapi

from common import load_jsonl

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TOP_N = 10
BM25_K1, BM25_B = 1.5, 0.75


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interaction_text(row):
    return row["formatted_interaction"]


def interaction_action_text(row):
    # formatted_interaction already ends with the proposed action; appending it again
    # gives the action twice the term weight of the rest of the trajectory
    return row["formatted_interaction"] + "\n" + row["proposed_action"]


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def select_random(train, dev, seed, top_n=TOP_N):
    train_ids = [r["example_id"] for r in train]
    # the seed includes example_id, so a sample's picks don't depend on the other dev samples
    return {
        r["example_id"]: random.Random(f"{seed}:{r['example_id']}").sample(train_ids, top_n)
        for r in dev
    }


def select_bm25(train, dev, doc_text, top_n=TOP_N):
    bm25 = BM25Okapi([tokenize(doc_text(r)) for r in train], k1=BM25_K1, b=BM25_B)
    selections = {}
    for r in dev:
        scores = bm25.get_scores(tokenize(doc_text(r)))
        # ties go to the earlier train row
        order = sorted(range(len(train)), key=lambda i: (-scores[i], i))[:top_n]
        selections[r["example_id"]] = [train[i]["example_id"] for i in order]
    return selections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["random", "bm25", "bm25-action"], required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--top-n", type=int, default=TOP_N,
                        help=f"examples per dev sample (default {TOP_N}; 10 keeps the original file names)")
    args = parser.parse_args()
    top_n = args.top_n
    if top_n < 1 or top_n > 100:
        parser.error("--top-n must be between 1 and 100")

    manifest = json.loads((DATA_DIR / "MANIFEST.json").read_text())
    files = {}
    for name in ("train.jsonl", "dev.jsonl"):
        digest = sha256(DATA_DIR / "raw" / name)
        if digest != manifest["files"][name]["sha256"]:
            raise SystemExit(f"{name} does not match MANIFEST.json; run download_data.py")
        files[name] = digest
    train = load_jsonl(DATA_DIR / "raw" / "train.jsonl")
    dev = load_jsonl(DATA_DIR / "raw" / "dev.jsonl")

    if args.method == "random":
        selections = select_random(train, dev, args.seed, top_n)
        # top_n=10 keeps the original name so already-committed selections stay byte-identical
        out_name = (f"random_seed{args.seed}.json" if top_n == TOP_N
                    else f"random_seed{args.seed}_top{top_n}.json")
        params = {"seed": args.seed,
                  "sampling": f"random.Random(f'{{seed}}:{{example_id}}').sample(train_ids, {top_n})"}
    else:
        action = args.method == "bm25-action"
        selections = select_bm25(train, dev, interaction_action_text if action else interaction_text, top_n)
        out_name = f"bm25_{'action_' if action else ''}dev_top{top_n}.json"
        params = {
            "library": f"rank_bm25 {version('rank_bm25')}", "k1": BM25_K1, "b": BM25_B,
            "text_fields": (
                "formatted_interaction + proposed_action (the action counted twice)"
                if action else "formatted_interaction"
            ), "tokenizer": "lowercase, split on non-alphanumeric",
            "stopwords": "none", "ties": "earlier train row first", "order": "descending similarity",
        }

    out = {
        "meta": {
            "method": args.method, "top_n": top_n, **params,
            "data_hf_commit_sha": manifest["hf_commit_sha"],
            "train_sha256": files["train.jsonl"], "dev_sha256": files["dev.jsonl"],
        },
        "selections": selections,
    }
    out_dir = DATA_DIR / "fewshot"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / out_name
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(selections)} dev samples x {top_n}); sha256 {sha256(out_path)[:12]}")


if __name__ == "__main__":
    main()
