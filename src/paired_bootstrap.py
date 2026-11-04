"""Paired bootstrap between runs on the same split.

Two runs are compared sample by sample, so the comparison is not swamped by which samples
happen to be easy. Deterministic: the bootstrap resamples are seeded.

Usage:
    python src/paired_bootstrap.py BASE_RUN CAND_RUN [CAND_RUN ...] --metric mae

Prints, per candidate: the observed difference, the 95% interval and P(candidate better).
Anything whose interval crosses 0 is noise, not an improvement.
"""
import argparse
import json
import random
from pathlib import Path

from common import jaccard, load_jsonl, task_fields

ROOT = Path(__file__).resolve().parent.parent


def load_run(run_dir):
    run_dir = Path(run_dir)
    config = json.loads((run_dir / "config.json").read_text())
    golds = {r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])}
    preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}
    ids = [i for i in golds if i in preds]
    return config, golds, preds, ids


# Which field each metric reads, so a single-task run is never asked for a label it never
# predicted. "exact" means "every field this task predicts is right".
METRIC_FIELDS = {"mae": ("risk_severity",), "domain": ("risk_domains",),
                 "driver": ("risk_drivers",), "exact": None}
DEFAULT_METRIC = {"multi": "mae", "task1": "mae", "task2a": "domain", "task2b": "driver"}


def per_sample(golds, preds, ids, metric, task="multi"):
    fields = task_fields(task)
    out = []
    for i in ids:
        g, p = golds[i], preds[i]
        if metric == "mae":
            out.append(abs(p["risk_severity"] - g["risk_severity"]))
        elif metric == "exact":
            ok = all(p[f] == g[f] if f == "risk_severity" else set(p[f]) == set(g[f])
                     for f in fields)
            out.append(0.0 if ok else 1.0)
        elif metric == "domain":
            out.append(1.0 - jaccard(p["risk_domains"], g["risk_domains"]))
        elif metric == "driver":
            out.append(1.0 - jaccard(p["risk_drivers"], g["risk_drivers"]))
        else:
            raise SystemExit(f"unknown metric {metric}")
    return out


def bootstrap(diffs, iterations, seed=0):
    rng = random.Random(seed)
    n = len(diffs)
    obs = sum(diffs) / n
    means = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(iterations))
    lo = means[int(0.025 * iterations)]
    hi = means[int(0.975 * iterations)]
    better = sum(1 for m in means if m < 0) / iterations     # lower is better for all our metrics
    return obs, lo, hi, better


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--metric", choices=["mae", "exact", "domain", "driver"], default=None,
                    help="default: the metric of the base run's task")
    ap.add_argument("--iterations", type=int, default=3000)
    args = ap.parse_args()

    base_cfg, golds, base_preds, base_ids = load_run(args.base)
    task = base_cfg.get("task", "multi")   # runs predating single-task support are joint
    metric = args.metric or DEFAULT_METRIC[task]
    needed = METRIC_FIELDS[metric]
    if needed and not set(needed) <= set(task_fields(task)):
        raise SystemExit(f"metric {metric!r} needs {needed[0]}, which task {task!r} does not predict")
    print(f"base: {args.base}  n={len(base_ids)}  split={base_cfg['split']}  "
          f"task={task}  metric={metric}\n")

    base_vals = per_sample(golds, base_preds, base_ids, metric, task)
    print(f"{'candidate':38s} {'base':>7s} {'cand':>7s} {'diff':>8s} {'95% CI':>20s} {'P(better)':>10s}")
    for cand in args.candidates:
        _, g2, p2, _ = load_run(cand)
        shared = [i for i in base_ids if i in p2]
        if len(shared) != len(base_ids):
            print(f"  ! {cand}: only {len(shared)}/{len(base_ids)} shared ids, skipped")
            continue
        base_shared = per_sample(golds, base_preds, shared, metric, task)
        cand_vals = per_sample(golds, p2, shared, metric, task)
        diffs = [c - b for c, b in zip(cand_vals, base_shared)]
        obs, lo, hi, better = bootstrap(diffs, args.iterations)
        b = sum(base_shared) / len(shared)
        c = sum(cand_vals) / len(shared)
        verdict = "better" if hi < 0 else ("worse" if lo > 0 else "noise")
        print(f"{Path(cand).parent.name + '/' + Path(cand).name:38s} {b:7.3f} {c:7.3f} "
              f"{obs:+8.3f} [{lo:+.3f},{hi:+.3f}] {better:10.2f}  {verdict}")


if __name__ == "__main__":
    main()
