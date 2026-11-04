"""Compare finished runs side by side and write a markdown table.

Usage:
    python src/compare.py                  # multi-task runs -> results/comparison.md
    python src/compare.py --task task1     # Task 1 runs     -> results/comparison-task1.md

Reads config.json, metrics.json and predictions.jsonl of each run under
results/deepseek-flash/<task_dir>/; nothing is written except the markdown file.
Rows come from config.json (selection / seed / k / version / run_id), so runs added later
are listed automatically. Sections that need a field the task does not predict are skipped.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from common import jaccard, load_jsonl, task_fields

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LEVELS = (1, 2, 3, 4, 5)
# The instruction every run of a task is compared against in the completeness table.
# For multi this is prompts/zero_shot_v1.txt, whose sha256 starts with ceb0530c8df1 —
# the value that used to be hard-coded here.
REFERENCE_PROMPT = {
    "multi": "prompts/zero_shot_v1.txt",
    "task1": "prompts/single/task1/zero_shot_answer_v1.txt",
    "task2a": "prompts/single/task2a/zero_shot_answer_v1.txt",
    "task2b": "prompts/single/task2b/zero_shot_answer_v1.txt",
}


def task_dir_name(task):
    return "multitask" if task == "multi" else task


def reference_hash(task):
    path = ROOT / REFERENCE_PROMPT[task]
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_runs(task="multi"):
    golds_cache, runs = {}, []
    for metrics_path in sorted((RESULTS / "deepseek-flash" / task_dir_name(task)).glob("*/*/metrics.json")):
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
    if c.get("task", "multi") == "multi":
        return ("", order, c.get("seed") or 0, c.get("k") or 0, c["run_id"])
    # single-task: all of answer-* first, then reason-*, each in the same shape as above
    return (c["version"], order, c.get("seed") or 0, c.get("k") or 0, c["run_id"])


def label(run):
    return run["config"].get("experiment") or f"{run['config']['strategy']}-{run['config']['version']}"


def sev_errors(run):
    return {e: abs(p["risk_severity"] - run["golds"][e]["risk_severity"]) for e, p in run["preds"].items()}


def sample_loss(run, task):
    """Per-sample loss in the task's own metric, so "better / worse" counts work for every task."""
    if "risk_severity" in task_fields(task):
        return sev_errors(run)
    field = "risk_domains" if task == "task2a" else "risk_drivers"
    return {e: 1.0 - jaccard(p[field], run["golds"][e][field]) for e, p in run["preds"].items()}


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


METRIC_LABEL = {"task1_mae": ("MAE", "越低越好"),
                "task2a_mean_jaccard": ("2a Jaccard", "越高越好"),
                "task2b_mean_jaccard": ("2b Jaccard", "越高越好")}
FIELD_METRIC = {"risk_severity": "task1_mae", "risk_domains": "task2a_mean_jaccard",
                "risk_drivers": "task2b_mean_jaccard"}
TASK_TITLE = {"multi": "多任务联合预测", "task1": "Task 1 风险严重度",
              "task2a": "Task 2a 损害领域", "task2b": "Task 2b 风险成因"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="multi", choices=list(REFERENCE_PROMPT),
                    help="which task's runs to compare (default: the historical joint prediction)")
    args = ap.parse_args()
    task = args.task
    fields = task_fields(task)
    metrics_shown = [FIELD_METRIC[f] for f in fields]

    runs = sorted(load_runs(task), key=sort_key)
    if not runs:
        raise SystemExit(f"no finished runs under results/deepseek-flash/{task_dir_name(task)}/*/*/metrics.json")
    base = next((r for r in runs if r["config"]["strategy"] == "zero-shot"), None)
    n_samples = runs[0]["metrics"]["n_total"]

    out = [f"# 运行对比 — {TASK_TITLE[task]}", "",
           f"由 `src/compare.py --task {task}` 生成，不要手改。数据：dev {n_samples} 条；"
           + "指标：" + "、".join(f"{METRIC_LABEL[m][0]}（{METRIC_LABEL[m][1]}）" for m in metrics_shown) + "。", "",
           f"> 单个运行只有 {n_samples} 条样本，指标差 0.02–0.03 很可能是噪声；看方向是否一致，不要把小差异当结论。", ""]

    # 1. main metrics
    cols = "".join(f" {METRIC_LABEL[m][0]} | Δ |" for m in metrics_shown)
    out += ["## 1. 指标", "",
            "| 运行 | version | selection | seed | k | run_id |" + cols,
            "| --- | --- | --- | --- | --- | --- |" + " --- | --- |" * len(metrics_shown)]
    for r in runs:
        c, m = r["config"], r["metrics"]
        cells = ""
        for key in metrics_shown:
            d = "" if r is base or base is None else delta(m[key], base["metrics"][key])
            cells += f" {fmt(m[key])} | {d} |"
        out.append(f"| {label(r)} | {c.get('version', '-')} | {c.get('selection') or '-'} "
                   f"| {c.get('seed') if c.get('seed') is not None else '-'} "
                   f"| {c.get('k') or 0} | {c['run_id']} |" + cells)
    base_name = label(base) if base is not None else "—"
    out += ["", f"Δ 是相对 `{base_name}` 的差（表里第一个 zero-shot 运行）。"
            "MAE 的 Δ 为负、Jaccard 的 Δ 为正表示变好。"
            "跨输出格式线的行（例如 reason-* 对 answer-* 的 zero-shot）也按这个基准算，"
            "要比同一条线内部的差，看第 2 节或用 `src/paired_bootstrap.py` 指定基准。", ""]

    # 2. paired comparison with zero-shot, in the task's own metric
    if base is not None:
        base_loss = sample_loss(base, task)
        unit = "等级误差" if "risk_severity" in fields else "1 − Jaccard"
        out += [f"## 2. 逐条对比 zero-shot（{unit}）", "",
                "| 运行 | 总损失 | 变好的样本 | 变差的样本 | 不变 |", "| --- | --- | --- | --- | --- |"]
        for r in runs:
            loss = sample_loss(r, task)
            better = sum(loss[e] < base_loss[e] - 1e-9 for e in loss)
            worse = sum(loss[e] > base_loss[e] + 1e-9 for e in loss)
            out.append(f"| {label(r)} | {fmt(sum(loss.values()), 2)} | {better} | {worse} "
                       f"| {len(loss) - better - worse} |")
        out += ["", "变好的样本明显多于变差的样本，比指标的差值更能说明改善是否稳定；两者相近则更可能是噪声。", ""]

    gold_counts = Counter(g["risk_severity"] for g in runs[0]["golds"].values())

    if "risk_severity" in fields:
        # 3. MAE by gold level
        out += ["## 3. 各标准等级的 MAE", "",
                "| 运行 | " + " | ".join(f"gold {lv}" for lv in LEVELS) + " | 平均偏差（预测−标准） |",
                "| --- |" + " --- |" * (len(LEVELS) + 1)]
        for r in runs:
            by_level, bias = level_stats(r)
            cells = [fmt(sum(v) / len(v)) if v else "-" for v in (by_level[lv] for lv in LEVELS)]
            out.append(f"| {label(r)} | " + " | ".join(cells) + f" | {bias:+.3f} |")
        out += ["", "各等级的样本数：" + "、".join(f"gold {lv}: {gold_counts[lv]}" for lv in LEVELS)
                + "。平均偏差为正表示整体高估。gold 2 和 gold 5 的样本太少，这两列只能看个大概。", ""]

        # 4. prediction distribution
        out += ["## 4. 预测的等级分布", "", "| 运行 | " + " | ".join(f"预测 {lv}" for lv in LEVELS) + " |",
                "| --- |" + " --- |" * len(LEVELS),
                "| **标准答案** | " + " | ".join(str(gold_counts[lv]) for lv in LEVELS) + " |"]
        for r in runs:
            cnt = Counter(p["risk_severity"] for p in r["preds"].values())
            out.append(f"| {label(r)} | " + " | ".join(str(cnt[lv]) for lv in LEVELS) + " |")
        out.append("")

    # 5. label count (second label)
    multi_fields = [f for f in fields if f != "risk_severity"]
    if multi_fields:
        names = {"risk_domains": "domain", "risk_drivers": "driver"}
        out += ["## 5. 每条样本给的标签个数", "",
                "| 运行 |" + "".join(f" {names[f]} 给 2 个 |" for f in multi_fields),
                "| --- |" + " --- |" * len(multi_fields)]
        out.append("| **标准答案** |" + "".join(
            f" {sum(len(g[f]) == 2 for g in runs[0]['golds'].values())} |" for f in multi_fields))
        for r in runs:
            out.append(f"| {label(r)} |" + "".join(
                f" {sum(len(p[f]) == 2 for p in r['preds'].values())} |" for f in multi_fields))
        out.append("")

    if "risk_severity" in fields:
        # 6. example agreement (diagnostic)
        out += ["## 6. 示例的等级与待评估样本的标准等级一致的比例（离线诊断）", "",
                "只用于解释结果，不参与选择。随机组的比例反映 train 的等级分布带来的“碰巧一致”。", "",
                "| 运行 | 一致比例 | 示例等级分布 1/2/3/4/5 |", "| --- | --- | --- |"]
        for r in runs:
            res = example_agreement(r)
            if res is None:
                continue
            share, cnt, total = res
            out.append(f"| {label(r)} | {share:.3f} | "
                       + " / ".join(f"{cnt[lv] / total:.2f}" for lv in LEVELS) + " |")
        out.append("")

    # 7. tokens
    out += ["## 7. token 用量（含重试）", "", "| 运行 | 请求次数 | 输入 | 其中缓存未命中 | 输出 |",
            "| --- | --- | --- | --- | --- |"]
    for r in runs:
        t = r["metrics"]["tokens"]
        out.append(f"| {label(r)} | {t['attempts']} | {t['prompt_tokens']:,} "
                   f"| {t['prompt_cache_miss_tokens']:,} | {t['completion_tokens']:,} |")
    out.append("")

    # 8. acceptance checks
    ref_hash = reference_hash(task)
    out += ["## 8. 完整性检查", "",
            f"| 运行 | {n_samples}/{n_samples} | 同 {REFERENCE_PROMPT[task]} | 模型 | 参数同 zero-shot | prompt_preview | messages |",
            "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in runs:
        c, m = r["config"], r["metrics"]
        few = c["strategy"] == "few-shot"
        ok = lambda b: "✓" if b else "✗"
        out.append(f"| {label(r)} | {ok(m['complete'] and m['n_success'] == m['n_total'])} "
                   f"| {ok(ref_hash is not None and c['prompt_sha256'] == ref_hash)} "
                   f"| {','.join(c['returned_models'])} "
                   f"| {ok(base is None or c['params'] == base['config']['params'])} "
                   f"| {ok((r['dir'] / 'prompt_preview.txt').exists()) if few else '-'} "
                   f"| {ok((r['dir'] / 'messages.jsonl.gz').exists()) if few else '-'} |")
    out.append("")

    name = "comparison.md" if task == "multi" else f"comparison-{task}.md"
    path = RESULTS / name
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path} ({len(runs)} runs, task {task})")


if __name__ == "__main__":
    main()
