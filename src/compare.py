"""Compare finished runs side by side and write results/comparison.md.

Usage: python src/compare.py            # every run under results/deepseek-flash/ that has metrics.json

Reads config.json, metrics.json and predictions.jsonl of each run; nothing is written except comparison.md.
Rows come from config.json (selection / seed / k / run_id), so runs added later (other seeds,
bm25-action) are listed automatically.
"""
import json
from collections import Counter
from pathlib import Path

from common import load_jsonl

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LEVELS = (1, 2, 3, 4, 5)
SYSTEM_HASH_PREFIX = "ceb0530c8df1"


def load_runs():
    golds_cache, runs = {}, []
    for metrics_path in sorted((RESULTS / "deepseek-flash").glob("*/*/metrics.json")):
        run_dir = metrics_path.parent
        config = json.loads((run_dir / "config.json").read_text())
        metrics = json.loads(metrics_path.read_text())
        if config["data_file"] not in golds_cache:
            golds_cache[config["data_file"]] = {
                r["example_id"]: r for r in load_jsonl(ROOT / config["data_file"])
            }
        golds = golds_cache[config["data_file"]]
        preds = {r["example_id"]: r for r in load_jsonl(run_dir / "predictions.jsonl")}
        runs.append({"dir": run_dir, "config": config, "metrics": metrics, "preds": preds, "golds": golds})
    return runs


def sort_key(run):
    c = run["config"]
    selection = c.get("selection")
    order = {None: 0, "random": 1, "bm25": 2, "bm25-action": 3}[selection]
    return (order, c.get("seed") or 0, c.get("k") or 0, c["run_id"])


def label(run):
    return run["config"].get("experiment") or f"{run['config']['strategy']}-{run['config']['version']}"


def sev_errors(run):
    return {e: abs(p["risk_severity"] - run["golds"][e]["risk_severity"]) for e, p in run["preds"].items()}


def level_stats(run):
    """MAE by gold level and signed bias (pred - gold) overall."""
    by_level = {lv: [] for lv in LEVELS}
    signed = []
    for eid, p in run["preds"].items():
        gold = run["golds"][eid]["risk_severity"]
        by_level[gold].append(abs(p["risk_severity"] - gold))
        signed.append(p["risk_severity"] - gold)
    return by_level, sum(signed) / len(signed)


def example_agreement(run):
    """Offline diagnostic: share of a sample's examples whose gold severity equals the sample's gold severity."""
    c = run["config"]
    if "selection_file" not in c:
        return None
    sel = json.loads((ROOT / c["selection_file"]).read_text())["selections"]
    train = {r["example_id"]: r for r in load_jsonl(ROOT / "data" / "raw" / "train.jsonl")}
    same = total = 0
    sev_counts = Counter()
    for eid in run["preds"]:
        for tid in sel[eid][: c["k"]]:
            ts = train[tid]["risk_severity"]
            sev_counts[ts] += 1
            same += ts == run["golds"][eid]["risk_severity"]
            total += 1
    return same / total, sev_counts, total


def fmt(x, nd=3):
    return f"{x:.{nd}f}"


def delta(x, base, nd=3, higher_better=True):
    d = x - base
    return f"{d:+.{nd}f}"


def main():
    runs = sorted(load_runs(), key=sort_key)
    base = next((r for r in runs if r["config"]["strategy"] == "zero-shot"), None)
    out = ["# 运行对比", "", "由 `src/compare.py` 生成，不要手改。数据：dev 143 条；指标：Task 1 MAE（越低越好）、Task 2a / 2b Mean Jaccard（越高越好）。", ""]
    out.append("> 单个运行只有 143 条样本，指标差 0.02–0.03 很可能是噪声；看方向是否一致，不要把小差异当结论。")
    out.append("")

    # 1. main metrics
    out += ["## 1. 三个指标", "",
            "| 运行 | selection | seed | k | run_id | MAE | Δ | 2a Jaccard | Δ | 2b Jaccard | Δ |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        c, m = r["config"], r["metrics"]
        d = ("", "", "") if r is base or base is None else (
            delta(m["task1_mae"], base["metrics"]["task1_mae"]),
            delta(m["task2a_mean_jaccard"], base["metrics"]["task2a_mean_jaccard"]),
            delta(m["task2b_mean_jaccard"], base["metrics"]["task2b_mean_jaccard"]))
        out.append(f"| {label(r)} | {c.get('selection') or '-'} | {c.get('seed') if c.get('seed') is not None else '-'} "
                   f"| {c.get('k') or 0} | {c['run_id']} | {fmt(m['task1_mae'])} | {d[0]} "
                   f"| {fmt(m['task2a_mean_jaccard'])} | {d[1]} | {fmt(m['task2b_mean_jaccard'])} | {d[2]} |")
    out.append("")
    out.append("Δ 是相对 zero-shot 的差。MAE 的 Δ 为负、Jaccard 的 Δ 为正表示变好。")
    out.append("")

    # 2. paired comparison with zero-shot
    if base is not None:
        base_err = sev_errors(base)
        out += ["## 2. 逐条对比 zero-shot（等级误差）", "",
                "| 运行 | 总误差 | 变好的样本 | 变差的样本 | 不变 |", "| --- | --- | --- | --- | --- |"]
        for r in runs:
            err = sev_errors(r)
            better = sum(err[e] < base_err[e] for e in err)
            worse = sum(err[e] > base_err[e] for e in err)
            out.append(f"| {label(r)} | {sum(err.values())} | {better} | {worse} | {len(err) - better - worse} |")
        out += ["", "总误差 = 所有样本 |预测等级 − 标准等级| 之和。变好的样本明显多于变差的样本，比 MAE 的差值更能说明改善是否稳定；两者相近则更可能是噪声。", ""]

    # 3. MAE by gold level
    out += ["## 3. 各标准等级的 MAE", "", "| 运行 | " + " | ".join(f"gold {lv}" for lv in LEVELS) + " | 平均偏差（预测−标准） |",
            "| --- |" + " --- |" * (len(LEVELS) + 1)]
    gold_counts = Counter(g["risk_severity"] for g in runs[0]["golds"].values()) if runs else Counter()
    for r in runs:
        by_level, bias = level_stats(r)
        cells = [fmt(sum(v) / len(v)) if v else "-" for v in (by_level[lv] for lv in LEVELS)]
        out.append(f"| {label(r)} | " + " | ".join(cells) + f" | {bias:+.3f} |")
    out.append("")
    out.append("各等级的样本数：" + "、".join(f"gold {lv}: {gold_counts[lv]}" for lv in LEVELS) + "。平均偏差为正表示整体高估。gold 2 和 gold 5 的样本太少，这两列只能看个大概。")
    out.append("")

    # 4. prediction distribution
    out += ["## 4. 预测的等级分布", "", "| 运行 | " + " | ".join(f"预测 {lv}" for lv in LEVELS) + " |", "| --- |" + " --- |" * len(LEVELS)]
    out.append("| **标准答案** | " + " | ".join(str(gold_counts[lv]) for lv in LEVELS) + " |")
    for r in runs:
        cnt = Counter(p["risk_severity"] for p in r["preds"].values())
        out.append(f"| {label(r)} | " + " | ".join(str(cnt[lv]) for lv in LEVELS) + " |")
    out.append("")

    # 5. label count (second label)
    out += ["## 5. 每条样本给的标签个数", "", "| 运行 | domain 给 2 个 | driver 给 2 个 |", "| --- | --- | --- |"]
    gd = sum(len(g["risk_domains"]) == 2 for g in runs[0]["golds"].values())
    gr = sum(len(g["risk_drivers"]) == 2 for g in runs[0]["golds"].values())
    out.append(f"| **标准答案** | {gd} | {gr} |")
    for r in runs:
        out.append(f"| {label(r)} | {sum(len(p['risk_domains']) == 2 for p in r['preds'].values())} "
                   f"| {sum(len(p['risk_drivers']) == 2 for p in r['preds'].values())} |")
    out.append("")

    # 6. example agreement (diagnostic)
    out += ["## 6. 示例的等级与待评估样本的标准等级一致的比例（离线诊断）", "",
            "只用于解释结果，不参与选择。随机组的比例反映 train 的等级分布带来的“碰巧一致”。", "",
            "| 运行 | 一致比例 | 示例等级分布 1/2/3/4/5 |", "| --- | --- | --- |"]
    for r in runs:
        res = example_agreement(r)
        if res is None:
            continue
        share, cnt, total = res
        out.append(f"| {label(r)} | {share:.3f} | " + " / ".join(f"{cnt[lv] / total:.2f}" for lv in LEVELS) + " |")
    out.append("")

    # 7. tokens
    out += ["## 7. token 用量（含重试）", "", "| 运行 | 请求次数 | 输入 | 其中缓存未命中 | 输出 |", "| --- | --- | --- | --- | --- |"]
    for r in runs:
        t = r["metrics"]["tokens"]
        out.append(f"| {label(r)} | {t['attempts']} | {t['prompt_tokens']:,} | {t['prompt_cache_miss_tokens']:,} | {t['completion_tokens']:,} |")
    out.append("")

    # 8. acceptance checks
    out += ["## 8. 完整性检查", "",
            "| 运行 | 143/143 | system prompt hash | 模型 | 参数同 zero-shot | prompt_preview | messages |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        c, m = r["config"], r["metrics"]
        few = c["strategy"] == "few-shot"
        ok = lambda b: "✓" if b else "✗"
        out.append(f"| {label(r)} | {ok(m['complete'] and m['n_success'] == 143)} | {ok(c['prompt_sha256'].startswith(SYSTEM_HASH_PREFIX))} "
                   f"| {','.join(c['returned_models'])} | {ok(base is None or c['params'] == base['config']['params'])} "
                   f"| {ok((r['dir'] / 'prompt_preview.txt').exists()) if few else '-'} "
                   f"| {ok((r['dir'] / 'messages.jsonl.gz').exists()) if few else '-'} |")
    out.append("")

    path = RESULTS / "comparison.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path} ({len(runs)} runs)")


if __name__ == "__main__":
    main()
