"""Build a single-file, interactive results/comparison.html from the finished runs.

Usage:
    python src/compare_html.py

Reads config.json / metrics.json / predictions.jsonl of every run under
results/deepseek-flash/ (same discovery rule as compare.py) plus the gold labels,
embeds everything into src/comparison_template.html and writes results/comparison.html.

The page is self-contained: no CDN, no fonts to download, opens from file://.
Numbers come from the runs themselves; nothing is recomputed here except MAE-by-level
and the signed bias, which use the same definitions as compare.py.
"""
import json
from pathlib import Path

from compare import label, level_stats, load_runs, sort_key

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
TEMPLATE = Path(__file__).resolve().parent / "comparison_template.html"


def run_id_of(run):
    """Stable page-local id: experiment + run_id keeps collisions impossible."""
    return f"{label(run)}/{run['config']['run_id']}"


def main():
    runs = sorted(load_runs(), key=sort_key)
    if not runs:
        raise SystemExit("no finished runs under results/deepseek-flash/*/*/metrics.json")

    # --- label pool: domain/driver strings repeat a lot across 9 runs x 143 samples
    pool, index = [], {}

    def ref(text):
        if text not in index:
            index[text] = len(pool)
            pool.append(text)
        return index[text]

    golds_src = runs[0]["golds"]
    golds = {
        eid: {
            "sev": g["risk_severity"],
            "dom": [ref(d) for d in g["risk_domains"]],
            "drv": [ref(k) for k in g["risk_drivers"]],
            "action": g["proposed_action"][:220],
        }
        for eid, g in golds_src.items()
    }
    eids = sorted(golds)

    samples = []
    for eid in eids:
        preds = {}
        for run in runs:
            p = run["preds"].get(eid)
            if p is None:
                preds[run_id_of(run)] = None
                continue
            preds[run_id_of(run)] = [
                p["risk_severity"],
                [ref(d) for d in p["risk_domains"]],
                [ref(k) for k in p["risk_drivers"]],
            ]
        samples.append({"eid": eid, "pred": preds})

    out_runs = []
    for run in runs:
        c, m = run["config"], run["metrics"]
        _, bias = level_stats(run)
        out_runs.append({
            "id": run_id_of(run),
            "label": label(run),
            "selection": c.get("selection") or "zero-shot",
            "seed": c.get("seed"),
            "k": c.get("k") or 0,
            "run_id": c["run_id"],
            "metrics": {
                "task1_mae": m["task1_mae"],
                "task2a_mean_jaccard": m["task2a_mean_jaccard"],
                "task2b_mean_jaccard": m["task2b_mean_jaccard"],
                "n_total": m["n_total"],
                "n_success": m["n_success"],
                "complete": m["complete"],
            },
            "tokens": {
                "attempts": m["tokens"]["attempts"],
                "prompt_tokens": m["tokens"]["prompt_tokens"],
                "completion_tokens": m["tokens"]["completion_tokens"],
            },
            "bias": bias,
            "prompt_sha": c["prompt_sha256"],
        })

    manifest = json.loads((ROOT / "data" / "MANIFEST.json").read_text())
    data = {
        "meta": {
            "data_file": runs[0]["config"]["data_file"],
            "hf_commit": manifest["hf_commit_sha"],
            "n_samples": len(eids),
            "system_prompt_sha": runs[0]["config"]["prompt_sha256"],
        },
        "levels": [1, 2, 3, 4, 5],
        "pool": pool,
        "golds": golds,
        "samples": samples,
        "runs": out_runs,
    }

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # "</script>" inside a JSON string would end the data block early
    payload = payload.replace("</", "<\\/")

    html = TEMPLATE.read_text(encoding="utf-8")
    if "__DATA__" not in html:
        raise SystemExit(f"{TEMPLATE.name} has no __DATA__ placeholder")
    html = html.replace("__DATA__", payload)

    path = RESULTS / "comparison.html"
    path.write_text(html, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({len(html) / 1024:.0f} KB, {len(out_runs)} runs, "
          f"{len(samples)} samples, {len(pool)} distinct labels)")


if __name__ == "__main__":
    main()
