"""Pick few-shot examples from train for every dev sample and write data/fewshot/<name>.json.

Usage:
    python src/select_examples.py --method random --seed 0   -> data/fewshot/random_seed0.json
    python src/select_examples.py --method bm25              -> data/fewshot/bm25_dev_top10.json
    python src/select_examples.py --method bm25-action       -> data/fewshot/bm25_action_dev_top10.json

Each output maps a dev example_id to 10 train example_ids. k=3/5/10 use the first 3/5/10,
so the subsets are nested. For bm25 the list is ordered by descending similarity.
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


def select_random(train, dev, seed):
    train_ids = [r["example_id"] for r in train]
    # the seed includes example_id, so a sample's picks don't depend on the other dev samples
    return {
        r["example_id"]: random.Random(f"{seed}:{r['example_id']}").sample(train_ids, TOP_N)
        for r in dev
    }


def select_bm25(train, dev, doc_text):
    bm25 = BM25Okapi([tokenize(doc_text(r)) for r in train], k1=BM25_K1, b=BM25_B)
    selections = {}
    for r in dev:
        scores = bm25.get_scores(tokenize(doc_text(r)))
        # ties go to the earlier train row
        order = sorted(range(len(train)), key=lambda i: (-scores[i], i))[:TOP_N]
        selections[r["example_id"]] = [train[i]["example_id"] for i in order]
    return selections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=["random", "bm25", "bm25-action"], required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

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
        selections = select_random(train, dev, args.seed)
        out_name = f"random_seed{args.seed}.json"
        params = {"seed": args.seed, "sampling": "random.Random(f'{seed}:{example_id}').sample(train_ids, 10)"}
    else:
        action = args.method == "bm25-action"
        selections = select_bm25(train, dev, interaction_action_text if action else interaction_text)
        out_name = f"bm25_{'action_' if action else ''}dev_top{TOP_N}.json"
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
            "method": args.method, "top_n": TOP_N, **params,
            "data_hf_commit_sha": manifest["hf_commit_sha"],
            "train_sha256": files["train.jsonl"], "dev_sha256": files["dev.jsonl"],
        },
        "selections": selections,
    }
    out_dir = DATA_DIR / "fewshot"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / out_name
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({len(selections)} dev samples x {TOP_N}); sha256 {sha256(out_path)[:12]}")


if __name__ == "__main__":
    main()
