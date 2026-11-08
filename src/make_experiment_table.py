"""Build the complete paired experiment table without modifying archived runs.

python3 src/make_experiment_table.py --gold data/raw/dev.jsonl
Omit --gold to summarize archived metrics without recomputing them.
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from common import compute_metrics, load_jsonl, validate_prediction

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "results/deepseek-flash"
KEYS = ("task1_mae", "task2a_mean_jaccard", "task2b_mean_jaccard")


def collect(gold_path=None):
    manifest = json.loads((ROOT / "data/MANIFEST.json").read_text())
    expected_ids = set(manifest["dev_example_ids"])
    golds = None
    if gold_path:
        content = gold_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != manifest["files"]["dev.jsonl"]["sha256"]:
            raise ValueError("gold data hash differs from data/MANIFEST.json")
        golds = {r["example_id"]: r for r in load_jsonl(gold_path)}
    records = []
    for config_path in sorted(BASE.glob("*/*/*/config.json")):
        directory = config_path.parent
        config = json.loads(config_path.read_text())
        config.setdefault("experiment", directory.parent.name)
        if config["split"] != "dev":
            continue
        metrics = json.loads((directory / "metrics.json").read_text())
        task = config.get("task", "multi")
        predictions = load_jsonl(directory / "predictions.jsonl")
        ids = [p["example_id"] for p in predictions]
        assert len(set(ids)) == len(ids), directory
        assert set(ids) <= expected_ids, directory
        assert config["data_sha256"] == manifest["files"]["dev.jsonl"]["sha256"], directory
        assert config["run_id"] == directory.name == metrics["run_id"], directory
        assert metrics["n_total"] == len(expected_ids), directory
        assert metrics["n_success"] == len(ids), directory
        assert metrics["n_failed"] == len(expected_ids - set(ids)), directory
        for p in predictions:
            validate_prediction({k: v for k, v in p.items() if k != "example_id"}, task)
        if golds is not None:
            # The exact scoring function used by src/evaluate.py; no archive writes.
            recalculated = compute_metrics({p["example_id"]: p for p in predictions}, golds, task)
            for key, value in recalculated.items():
                assert math.isclose(value, metrics[key], abs_tol=1e-12), (directory, key)
        records.append(dict(
            ref=f"R{len(records) + 1:02}", directory=directory,
            group=directory.relative_to(BASE).parts[0], config=config, metrics=metrics,
            verified=golds is not None,
        ))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path)
    args = parser.parse_args()
    records = collect(args.gold)
    index = {(r["group"], r["config"]["experiment"]): r for r in records}
    assert len(index) == len(records), "Multiple runs per experiment require explicit selection"
    counts = Counter(r["group"] for r in records)
    complete = [r for r in records if r["metrics"]["n_failed"] == 0]
    used = set()

    def score(group, experiment, field):
        record = index.get((group, experiment))
        if record is None:
            return "—"
        assert record["metrics"]["n_failed"] == 0, experiment
        used.add(record["ref"])
        return f'[{record["metrics"][field]:.3f}](#{record["ref"].lower()})'

    lines = [
        "# 已完成实验总表",
        "",
        "由 `python3 src/make_experiment_table.py` 生成；所有分数来自归档运行的 `metrics.json`。",
        "加 `--gold data/raw/dev.jsonl` 可用 `src/evaluate.py` 的同一评分函数复核，且不改写历史结果。",
        "",
        f"本表扫描到 {len(records)} 份开发集结果：多任务 {counts['multitask']} 份、单任务 {sum(counts[t] for t in ('task1', 'task2a', 'task2b'))} 份、单任务合并 {counts['single-merged']} 份。",
        f"其中 {len(complete)} 份覆盖完整数据，{len(records) - len(complete)} 份预测不完整；合并结果复用已有预测，不算新的模型实验。",
        "开发集（development set / dev，用于开发比较的已标注数据）固定为 `data/MANIFEST.json` 中的 143 条样本。",
        "",
        "口径：",
        "",
        "- 无推理（without reasoning / w/o）：只输出标签；有推理（with reasoning / w/）：先输出简短判断依据再给标签。这里比较回答格式，配置中的服务端思考模式 `thinking.type` 均为 `disabled`。",
        "- 多任务联合预测（multi-task prediction）：一次调用同时预测三个任务；单任务独立预测（single-task prediction）：每个任务单独调用，同一行的三个任务来自三份运行。",
        "- Task 1 风险等级用平均绝对误差（Mean Absolute Error / MAE，预测等级与标准等级之差的绝对值均值），越低越好。Task 2a 危害领域和 Task 2b 风险驱动因素用交并比均值（Mean Jaccard，预测标签集合与标准集合交集大小除以并集大小后取均值），越高越好。",
        "- 零样本（zero-shot）：不提供标注示例。少样本（few-shot）：提供 k 个标注训练示例；随机选择（random selection）固定种子为 0；BM25（Best Matching 25，按词项匹配相关性排序的文本检索方法）用于选择相似示例；加动作表示检索文本包含待执行动作。",
        "- 轨迹规则提炼（trace2skill，从训练轨迹及错误归因中提炼可复用判断规则）记为“+规则”；两种回答格式的规则分别提炼，因此该行比较两套完整方案，不能单独归因于推理格式。",
        "- 每个分数可点击定位到运行编号（run_id，标识一次运行的目录名）与原始文件；`—` 表示没有完整运行，不补值。",
        "- 每格依次为 **无推理 / 有推理 / Δ**；差值（delta / Δ）按未舍入分数计算：有推理 − 无推理。T1 的 Δ 为负表示改善；T2a、T2b 的 Δ 为正表示改善。",
        "",
        "| 预测方式 | 方法 | k | T1 MAE↓（w/o / w/ / Δ） | T2a J↑（w/o / w/ / Δ） | T2b J↑（w/o / w/ / Δ） |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    def row(mode, method, k, groups, experiments):
        cells = []
        for group, field in zip(groups, KEYS):
            pair = [score(group, exp, field) for exp in experiments]
            runs = [index.get((group, exp)) for exp in experiments]
            delta = "—"
            if all(runs):
                difference = runs[1]["metrics"][field] - runs[0]["metrics"][field]
                delta = f"{difference:+.3f}" if abs(difference) >= 0.0005 else "0.000"
            cells.append(" / ".join([*pair, delta]))
        lines.append(f"| {mode} | {method} | {k or '—'} | " + " | ".join(cells) + " |")

    for mode in ("多任务联合", "单任务独立"):
        groups = ("multitask",) * 3 if mode == "多任务联合" else ("task1", "task2a", "task2b")
        suffixes = ("v1", "v4") if mode == "多任务联合" else ("answer-v1", "reason-v1")
        row(mode, "零样本", 0, groups, [f"zero-shot-{v}" for v in suffixes])
        for selection, label in (("random-s0", "少样本·随机"), ("bm25", "少样本·BM25")):
            for k in (3, 5, 10, 20):
                suffixes = ("v1", "v4b") if mode == "多任务联合" else ("answer-v1", "reason-v1")
                row(mode, label, k, groups, [f"few-shot-{selection}-k{k}-{v}" for v in suffixes])
        suffixes = ("v2", "v5") if mode == "多任务联合" else ("answer-v2", "reason-v2")
        row(mode, "零样本+规则", 0, groups, [f"zero-shot-{v}" for v in suffixes])
        if mode == "多任务联合":
            for selection, label, ks in (("random-s0", "少样本·随机+规则", (10,)), ("bm25", "少样本·BM25+规则", (3, 5, 10, 20)), ("bm25-action", "少样本·BM25加动作", (3, 5, 10))):
                for k in ks:
                    row(mode, label, k, groups, [f"few-shot-{selection}-k{k}-v2" if '规则' in label else f"few-shot-{selection}-k{k}-v1", "NOT_RUN"])

    lines += [
        "",
        "版本对应：多任务基础无推理为 v1、有推理零样本为 v4、少样本为 v4b（在最后的用户消息增加回答格式提醒）；多任务+规则为无推理 v2、有推理 v5。单任务分别为 answer-v1 / reason-v1；+规则为 answer-v2 / reason-v2。所以多任务少样本的对照还包含格式提醒差异。",
        "",
        "从表中可以直接观察到：",
        "",
        "- 有推理并非所有方法、所有任务都更好。例如单任务零样本：T1 从 0.266 降至 0.238，T2a 从 0.837 降至 0.832，T2b 从 0.711 升至 0.753（见该行各格运行）。",
        "- 已完成配置中，T1 最低为单任务 BM25 k=20 有推理的 0.154；T2a 最高为多任务随机 k=3 有推理的 0.880；T2b 最高为多任务 BM25 k=5 +规则无推理的 0.795（见相应各格）。这些最优值来自不同配置。",
        "- 单任务+规则相对各自零样本基础版：T1 两种格式都变差；T2a 两种格式都变好；T2b 无推理小幅变好、有推理变差。多任务有推理加规则后，三个指标均变差。",
        "- 以上是已观察分数的方向比较；本表未进行显著性检验。开发集已被反复比较，最优配置不代表隐藏测试集上的成绩。",
        "",
        "已保存的单任务合并结果也列在下面。合并（assembly）指按样本编号拼接三个任务的已有预测，不再调用模型。",
        "",
        "| 来源 | 格式 | T1 MAE↓ | T2a J↑ | T2b J↑ | 运行 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for lineage, label in (("answer", "w/o"), ("reason", "w/")):
        exp = f"zero-shot-{lineage}-v1"
        record = index[("single-merged", exp)]
        cells = [score("single-merged", exp, key) for key in KEYS]
        lines.append(f"| 单任务零样本合并 | {label} | " + " | ".join(cells) + f' | [{record["config"]["run_id"]}](#{record["ref"].lower()}) |')

    incomplete = [r for r in records if r["metrics"]["n_failed"]]
    lines += ["", "预测不完整的运行不进入主表：", ""]
    for r in incomplete:
        m = r["metrics"]
        lines.append(f'- `{r["config"]["experiment"]}`，run_id `{r["config"]["run_id"]}`：仅 {m["n_success"]}/{m["n_total"]} 条有效，缺 {m["n_failed"]} 条。其已有分数只基于成功样本，不能直接对照完整数据；主表采用已完成的 v4b。')
    assert used == {r["ref"] for r in complete}, "A completed run was omitted"
    lines += ["", "运行来源与核验：", "", f"本次{'已' if args.gold else '未'}用固定版本标准答案逐份复算指标；同时检查预测格式、样本编号、覆盖率与配置中的数据版本。未改写任何历史运行。", "", "| 编号 | 目录 / 方法 | run_id | 有效样本 | 原始文件 |", "| --- | --- | --- | --- | --- |"]
    for r in records:
        directory = r["directory"].relative_to(ROOT / "results")
        m = r["metrics"]
        lines.append(f'| <a id="{r["ref"].lower()}"></a>{r["ref"]} | `{r["group"]}/{r["config"]["experiment"]}` | `{r["config"]["run_id"]}` | {m["n_success"]}/{m["n_total"]} | [指标]({directory}/metrics.json) · [配置]({directory}/config.json) · [预测]({directory}/predictions.jsonl) |')
    output = ROOT / "results/EXPERIMENTS_ALL.md"
    output.write_text("\n".join(lines) + "\n")
    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["ref", "group", "experiment", "run_id", "format", "n_success", "n_total", *KEYS, "verified", "run_dir"])
        writer.writeheader()
        for r in records:
            c, m = r["config"], r["metrics"]
            writer.writerow(dict(ref=r["ref"], group=r["group"], experiment=c["experiment"], run_id=c["run_id"], format="w/" if c.get("output_format") == "reasoning-answer-v1" or c["version"].startswith("reason-") else "w/o", n_success=m["n_success"], n_total=m["n_total"], **{key: m.get(key, "") for key in KEYS}, verified=r["verified"], run_dir=str(r["directory"].relative_to(ROOT))))
    print(f"Wrote {output.relative_to(ROOT)} and {csv_path.relative_to(ROOT)}; {len(records)} runs, {len(complete)} complete, verified={args.gold is not None}")


if __name__ == "__main__":
    main()
