"""Offline checks behind docs/evolve/pilot-task2b.md. No API calls.

    python src/evolve_pilot_check.py noise  --a <run_dir> --b <run_dir>   # two identical zero-shot runs on train_evolve
    python src/evolve_pilot_check.py replay --run-dir results/evolve/task2b/20261111-100017

noise:  tau, the flip ledger and gates G1-G3 when the "candidate" is just a repeat of the seed
        (evaluation = all folds except fold 1, as in round 1).
replay: the G1 threshold each full-gate candidate would face under different tau rules.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evolve as E  # noqa: E402

TASK = "task2b"


def load_preds(path):
    out = {}
    for line in open(path):
        r = json.loads(line)
        out[r["example_id"]] = {"status": "ok", "labels": {"risk_drivers": r["risk_drivers"]}}
    return out


def cmd_noise(a_dir, b_dir):
    rows, folds, _ = E.load_data()
    a = load_preds(Path(a_dir) / "predictions.jsonl")
    b = load_preds(Path(b_dir) / "predictions.jsonl")
    ids = [i for f in folds for i in f]
    fold_of = {i: k for k, f in enumerate(folds) for i in f}
    tau = sum(set(a[i]["labels"]["risk_drivers"]) != set(b[i]["labels"]["risk_drivers"]) for i in ids)
    ev = [i for k, f in enumerate(folds) if k != 1 for i in f]
    tau_scaled = tau * len(ev) / len(ids)
    _, m = E.full_gate_metrics(TASK, rows, a, b, ev, fold_of, dict(E.DEFAULTS), tau_scaled)
    g = m["gates"]
    print(json.dumps({
        "n": len(ids), "tau": tau, "tau_share": round(tau / len(ids), 4),
        "eval_n": len(ev), "ledger": m["ledger"],
        "G1_need_net": round(g["G1_gain"]["need_net"], 1), "G1_p_better": round(g["G1_gain"]["p_better"], 3),
        "G2": g["G2_no_damage"], "G3_pass": g["G3_no_shift"]["pass"],
        "G3_swapped": g["G3_no_shift"]["swapped_labels"],
    }, ensure_ascii=False, indent=1))


def cmd_replay(run_dir):
    run = Path(run_dir)
    base = json.loads((run / "baseline.json").read_text())
    tau, n = base["tau"], base["n_items"]
    rl = base["repeat_ledger"]
    tau_loss = rl["improved"] + rl["worsened"]
    min_net = json.loads((run / "config.json").read_text())["params"]["min_net"]
    print(f"tau={tau}/{n}; repeat ledger improved={rl['improved']} worsened={rl['worsened']} net={rl['net']}")
    for gate in sorted(run.glob("rounds/round_*/full_gate.json")):
        doc = json.loads(gate.read_text())
        for c in doc if isinstance(doc, list) else doc.get("results", []):
            g1, s = c["gates"]["G1_gain"], c["ledger"]["n"] / n
            rules = {"2*tau": 2 * tau * s, "1*tau": tau * s, "1*tau_loss": tau_loss * s,
                     "2*sqrt(tau_loss)": 2 * math.sqrt(tau_loss * s), "min_net only": 0}
            print(f"{c['cand_id']}: net={g1['net']} p_better={g1['p_better']:.3f} diff={g1['diff']:.4f}")
            for name, v in rules.items():
                need = max(min_net, v)
                ok = g1["net"] >= need and g1["p_better"] >= 0.9
                print(f"    {name:18s} need {need:6.1f}  {'accept' if ok else 'reject'}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("noise")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p = sub.add_parser("replay")
    p.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    if args.cmd == "noise":
        cmd_noise(args.a, args.b)
    else:
        cmd_replay(args.run_dir)


if __name__ == "__main__":
    main()
