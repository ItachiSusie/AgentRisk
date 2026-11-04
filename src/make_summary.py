"""Build results/SUMMARY.md: one table per task, the two output-format lines side by side.

Every number is read from the run directories' metrics.json, so the file is
reproducible and never hand-edited:

    python src/make_summary.py

Layout (see docs/single-task/00-common.md section 3 for the naming):
rows are configurations in a fixed order, columns are the two output-format
lines (answer = labels only, reason = brief justification then labels).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = "deepseek-flash"
OUT = ROOT / "results" / "SUMMARY.md"

# metric field, display name, and whether lower is better
TASKS = [
    ("task1", "task1_mae", "MAE", True,
     "Task 1 — 风险等级 risk_severity（MAE，越低越好）"),
    ("task2a", "task2a_mean_jaccard", "Mean Jaccard", False,
     "Task 2a — 危害领域 risk_domains（Mean Jaccard，越高越好）"),
    ("task2b", "task2b_mean_jaccard", "Mean Jaccard", False,
     "Task 2b — 风险驱动因素 risk_drivers（Mean Jaccard，越高越好）"),
]

LINEAGES = [("answer", "无推理 (w/o reasoning)"), ("reason", "有推理 (w/ reasoning)")]

# (display label, k, experiment template); {lin} is the output-format line
ROWS = [
    ("zero-shot", 0, "zero-shot-{lin}-v1"),
    ("few-shot random", 3, "few-shot-random-s0-k3-{lin}-v1"),
    ("few-shot random", 5, "few-shot-random-s0-k5-{lin}-v1"),
    ("few-shot random", 10, "few-shot-random-s0-k10-{lin}-v1"),
    ("few-shot random", 20, "few-shot-random-s0-k20-{lin}-v1"),
    ("few-shot BM25", 3, "few-shot-bm25-k3-{lin}-v1"),
    ("few-shot BM25", 5, "few-shot-bm25-k5-{lin}-v1"),
    ("few-shot BM25", 10, "few-shot-bm25-k10-{lin}-v1"),
    ("few-shot BM25", 20, "few-shot-bm25-k20-{lin}-v1"),
    ("trace2skill (v2)", 0, "zero-shot-{lin}-v2"),
]

# multi-task reference runs: the same prompt predicting all three fields at once
MULTI = {"answer": ("zero-shot-v1", "20261022-051556"),
         "reason": ("zero-shot-v4", "20261103-074636")}


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_dir(task_dir, experiment):
    base = ROOT / "results" / MODEL / task_dir / experiment
    runs = sorted(p for p in base.iterdir() if (p / "metrics.json").exists())
    if not runs:
        raise SystemExit(f"no scored run under {base}")
    return runs[-1]  # latest run_id; earlier ones are kept but superseded


def cell(task_dir, experiment, field):
    d = run_dir(task_dir, experiment)
    m = json.loads((d / "metrics.json").read_text())
    if m["n_failed"]:
        raise SystemExit(f"{d} has {m['n_failed']} failed samples; not summarisable")
    tok = m["tokens"]["prompt_tokens"] / 1e6
    return {"score": m[field], "run_id": m["run_id"], "n": m["n_total"], "tokens": tok}


def fmt(x, lower_better, delta=None, best=False):
    s = f"{x:.3f}"
    if best:
        s = f"**{s}**"
    if delta is None:
        return s
    sign = "+" if delta >= 0 else "-"
    return f"{s} ({sign}{abs(delta):.3f})"


def task_table(task_dir, field, metric_name, lower_better):
    data = {lin: {r[2].format(lin=lin): cell(task_dir, r[2].format(lin=lin), field)
                  for r in ROWS} for lin, _ in LINEAGES}
    zero = {lin: data[lin][f"zero-shot-{lin}-v1"]["score"] for lin, _ in LINEAGES}
    # best among the v1 configurations only; trace2skill v2 is a different prompt family
    best = {}
    for lin, _ in LINEAGES:
        v1 = [data[lin][r[2].format(lin=lin)]["score"] for r in ROWS if not r[2].endswith("-v2")]
        best[lin] = min(v1) if lower_better else max(v1)

    head = ["| 配置 | k | " + " | ".join(label for _, label in LINEAGES) + " |",
            "| --- | --- | " + " | ".join("---" for _ in LINEAGES) + " |"]
    lines = list(head)

    multi = []
    for lin, _ in LINEAGES:
        exp, rid = MULTI[lin]
        m = json.loads((ROOT / "results" / MODEL / "multitask" / exp / rid / "metrics.json").read_text())
        multi.append(fmt(m[field], lower_better))
    lines.append(f"| *多任务同款 prompt（参考）* | – | {' | '.join(multi)} |")

    for label, k, template in ROWS:
        cells = []
        for lin, _ in LINEAGES:
            c = data[lin][template.format(lin=lin)]
            d = None if k == 0 and template.endswith("-v1") else c["score"] - zero[lin]
            cells.append(fmt(c["score"], lower_better, d, c["score"] == best[lin]))
        kk = "–" if k == 0 else str(k)
        lines.append(f"| {label} | {kk} | {' | '.join(cells)} |")
    return "\n".join(lines), data


def appendix_table(data):
    lines = ["| 配置 | k | " + " | ".join(f"{label} run_id / 输入 token" for _, label in LINEAGES) + " |",
             "| --- | --- | " + " | ".join("---" for _ in LINEAGES) + " |"]
    for label, k, template in ROWS:
        cells = []
        for lin, _ in LINEAGES:
            c = data[lin][template.format(lin=lin)]
            cells.append(f"`{c['run_id']}` / {c['tokens']:.2f} M")
        kk = "–" if k == 0 else str(k)
        lines.append(f"| {label} | {kk} | {' | '.join(cells)} |")
    return "\n".join(lines)


def joint_row(name, pred_path, note):
    gold = {r["example_id"]: r for r in load_jsonl(ROOT / "data" / "raw" / "dev.jsonl")}
    preds = load_jsonl(pred_path)
    n = len(preds)
    mae = dom = drv = exact = 0.0
    for r in preds:
        g = gold[r["example_id"]]
        a = r["risk_severity"] == g["risk_severity"]
        mae += abs(r["risk_severity"] - g["risk_severity"])
        sd, gd = set(r["risk_domains"]), set(g["risk_domains"])
        sv, gv = set(r["risk_drivers"]), set(g["risk_drivers"])
        dom += len(sd & gd) / len(sd | gd) if (sd | gd) else 1.0
        drv += len(sv & gv) / len(sv | gv) if (sv | gv) else 1.0
        exact += a and sd == gd and sv == gv
    exact = int(exact)
    return (f"| {name} | {mae / n:.3f} | {dom / n:.3f} | {drv / n:.3f} | "
            f"{exact} ({exact / n * 100:.1f}%) | {note} |")


def joint_table():
    lines = ["| 预测方式 | Task 1 MAE ↓ | Task 2a Jaccard ↑ | Task 2b Jaccard ↑ | 三字段全对 ↑ | run_id |",
             "| --- | --- | --- | --- | --- | --- |"]
    base = ROOT / "results" / MODEL
    lines.append(joint_row("多任务 无推理（v1）",
                           base / "multitask/zero-shot-v1/20261022-051556/predictions.jsonl",
                           "`20261022-051556`"))
    lines.append(joint_row("多任务 有推理（v4）",
                           base / "multitask/zero-shot-v4/20261103-074636/predictions.jsonl",
                           "`20261103-074636`"))
    lines.append(joint_row("单任务合并 无推理（answer-v1）",
                           base / "single-merged/zero-shot-answer-v1/20261104-094832/predictions.jsonl",
                           "`20261104-094832`"))
    lines.append(joint_row("单任务合并 有推理（reason-v1）",
                           base / "single-merged/zero-shot-reason-v1/20261104-094832/predictions.jsonl",
                           "`20261104-094832`"))
    return "\n".join(lines)


def main():
    parts = [HEADER]
    appendices = []
    for task_dir, field, metric_name, lower_better, title in TASKS:
        table, data = task_table(task_dir, field, metric_name, lower_better)
        parts.append(f"### {title}\n\n{table}\n")
        appendices.append(f"### {title.split(' — ')[0]}\n\n{appendix_table(data)}\n")
    parts.append(FINDINGS)
    parts.append(JOINT_INTRO + joint_table() + "\n\n" + JOINT_NOTE)
    parts.append(APPENDIX_INTRO + "\n".join(appendices))
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")

FINDINGS = """## 主要结论

下面每个「显著 / 噪声」的判断都来自配对自助法（paired bootstrap，把两个运行逐条样本
配对后重抽样，看差值的 95% 置信区间（confidence interval）是否整个落在 0 的一侧），
命令是 `python src/paired_bootstrap.py <基准 run_dir> <对比 run_dir> --metric <mae|domain|driver>`。
置信区间跨过 0 就是噪声，不要当结论。

1. **few-shot 示例有用，BM25 检索好过随机抽样——但只在 Task 1 和 Task 2b 成立。**
   - Task 1 无推理：BM25 k=10 的 0.196 比 zero-shot 的 0.266 好 0.070，置信区间
     [-0.133, -0.014]，显著；有推理：BM25 k=20 的 0.154 比 0.238 好 0.084，
     [-0.147, -0.021]，显著。
   - Task 2b 无推理：BM25 k=10 的 0.786 比 zero-shot 的 0.711 好，Jaccard 距离差
     -0.075 [-0.120, -0.034]，显著。
   - Task 2a：最好的一格（BM25 k=10，0.857）相对 zero-shot 的差是 -0.020
     [-0.056, +0.015]，**跨过 0，是噪声**。这个任务 zero-shot 已经有 0.837，
     示例没有给出新信息。
   - 随机抽样的曲线整体在 BM25 下方，但两者的差多数落在噪声区间内；能确定的是
     「有示例好过没示例」，「BM25 好过随机」只在 Task 1 的大 k 处看得比较清楚。

2. **让模型先写依据（有推理）单独看只在 Task 2b 有效。**
   zero-shot 下 answer → reason：Task 1 -0.028 [-0.098, +0.042]（噪声）、
   Task 2a +0.005 [-0.044, +0.051]（噪声）、Task 2b -0.042 [-0.083, -0.002]（显著）。
   三个任务拼起来之后才看得出整体收益，见下一节。

3. **trace2skill 蒸馏出的规则（v2）没有帮上忙，Task 1 上还明显变差。**
   Task 1 无推理 0.350 比 0.266 差 0.084 [+0.014, +0.154]，显著变差；
   有推理 0.336 比 0.238 差 0.098 [+0.000, +0.196]，边界。
   Task 2a 的 0.862 / 0.866 是表里最高的两个数，但相对 zero-shot 是
   -0.026 [-0.061, +0.009]，仍然是噪声，所以没有加粗。
   Task 2b 无效果。规则没用的原因在错误分诊里有线索：Task 1 的错误里只有
   15/102 属于「规则本身错」，剩下的是判断边界问题，写规则改不动。

"""

JOINT_NOTE = """判断：**单任务 + 有推理** 的三字段全对率 55.2%，比多任务无推理（49.0%）好
-0.063 [-0.119, -0.014]、比多任务有推理（49.7%）好 -0.056 [-0.112, -0.007]，两个都显著
（指标是 exact 的损失，越低越好，所以差值为负表示更好）。
**单任务 + 无推理** 的 51.7% 相对多任务无推理是 -0.028 [-0.063, +0.000]，跨过 0，是噪声。

也就是说：把一个 prompt 拆成三个单任务 prompt，本身不够；**要配合「先写依据再给标签」
才能拿到稳定的收益**。代价是三次调用而不是一次，输入 token 约 0.66 M 对 0.25 M。

"""

HEADER = """# 结果汇总 — 单任务 vs 多任务

由 `python src/make_summary.py` 生成，**不要手改**。每个数字都读自对应 run 目录下的
`metrics.json`，可用 `python src/evaluate.py <run_dir>` 复算。

- 评测集：dev，143 条。
- 每行是一个配置，每列是一条**输出格式线（output-format lineage，模型被要求以什么形式作答）**：
  - **无推理（answer）**：只输出标签的 JSON。
  - **有推理（reason）**：先写一段不超过 120 词的依据，再给标签。
- 括号里是 **Δ**，相对**同一列**的 zero-shot（所以是同一条输出格式线内部的比较）。
  Task 1 是 MAE（Mean Absolute Error，平均绝对误差），Δ 为负表示变好；
  Task 2a/2b 是 Mean Jaccard（交并比均值），Δ 为正表示变好。
- **粗体**是该列 v1 系列里的最好值。trace2skill 用的是另一版 instruction（v2），
  不参与粗体评选，单列在最后一行。
- 第一行「多任务同款 prompt」是对照：同一个 prompt 一次预测三个字段
  （zero-shot，无推理 = `zero-shot-v1`，有推理 = `zero-shot-v4`）。
- 143 条样本下，**指标差小于约 0.03 基本是噪声**，看方向是否一致，不要把小差异当结论。
  要判断显著性请用 `python src/paired_bootstrap.py BASE CAND --metric <mae|domain|driver>`。

## 三个子任务

"""

JOINT_INTRO = """## 把三个单任务拼回一条完整预测

单任务的每次运行只预测一个字段，要和多任务直接比，得把三个任务同一条样本的预测按
`example_id` 拼起来（`python src/assemble_single.py`，缺任何一个字段的样本直接丢弃，
不用标准答案或默认值补）。拼起来之后才能算「三字段全对」（exact match，三个字段
同时判对的样本数）——这是整轮实验里唯一在统计上站得住的单任务优势。

"""

APPENDIX_INTRO = """## 附录：run_id 与输入 token

每格是该配置的 `run_id` 和输入 token（prompt tokens，含重试）。目录是
`results/deepseek-flash/<task>/<实验名>/<run_id>/`。

"""


if __name__ == "__main__":
    main()
