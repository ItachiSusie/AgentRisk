"""Re-evaluate the fixed runs and regenerate this experiment's comparison artifacts."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from common import load_jsonl
from paired_bootstrap import load_run, per_sample, bootstrap

RUNS = [
    ("zero-shot v4", "zero-shot-v4/20261103-074636"),
    ("zero-shot v5", "zero-shot-v5/20261104-084436"),
    ("BM25 k=3 v4b", "few-shot-bm25-k3-v4b/20261104-084243"),
    ("BM25 k=5 v4b", "few-shot-bm25-k5-v4b/20261103-083817"),
    ("BM25 k=10 v4b", "few-shot-bm25-k10-v4b/20261103-084725"),
    ("random seed=0 k=3 v4b", "few-shot-random-s0-k3-v4b/20261104-084300"),
    ("random seed=0 k=5 v4b", "few-shot-random-s0-k5-v4b/20261104-084409"),
    ("random seed=0 k=10 v4b", "few-shot-random-s0-k10-v4b/20261104-084417"),
]
METRICS = ("task1_mae", "task2a_mean_jaccard", "task2b_mean_jaccard")
runs = []
for label, suffix in RUNS:
    path = ROOT / "results/deepseek-flash/multitask" / suffix
    cfg, gold, pred, ids = load_run(path)
    assert len(ids) == len(gold) == len(pred) == 143, (label, len(ids))
    assert len(load_jsonl(path / "predictions.jsonl")) == len(pred)
    for file_key, hash_key in (("data_file", "data_sha256"), ("prompt_file", "prompt_sha256"),
                               ("spec_file", "spec_sha256"), ("selection_file", "selection_sha256")):
        if file_key in cfg:
            assert hashlib.sha256((ROOT / cfg[file_key]).read_bytes()).hexdigest() == cfg[hash_key]
    subprocess.run([sys.executable, str(ROOT / "src/evaluate.py"), str(path)], check=True,
                   stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(ROOT / "src/analyze.py"), str(path)], check=True,
                   stdout=subprocess.DEVNULL)
    metrics = json.loads((path / "metrics.json").read_text())
    assert metrics["complete"] and metrics["n_failed"] == 0
    exact = sum(per_sample(gold, pred, ids, "exact"))
    runs.append(dict(label=label, path=path, cfg=cfg, gold=gold, pred=pred, ids=ids,
                     metrics=metrics, exact=int(len(ids)-exact)))

def contrast(a, b):
    assert a["cfg"]["data_sha256"] == b["cfg"]["data_sha256"]
    assert set(a["ids"]) == set(b["ids"])
    results = {}
    for metric in ("mae", "domain", "driver"):
        av = per_sample(a["gold"], a["pred"], a["ids"], metric)
        bv = per_sample(a["gold"], b["pred"], a["ids"], metric)
        obs, lo, hi, _ = bootstrap([y-x for x,y in zip(av,bv)], 10000, seed=0)
        if metric != "mae":
            obs, lo, hi = -obs, -hi, -lo
        results[metric] = dict(difference=obs, ci95=[lo,hi])
    return dict(base=a["label"], candidate=b["label"], metrics=results)

pairs = [(0,i) for i in range(1,8)] + [(5,2),(6,3),(7,4)]
pairs += [(2,3),(3,4),(2,4),(5,6),(6,7),(5,7)]
contrasts = [contrast(runs[a],runs[b]) for a,b in pairs]
(OUT / "paired-bootstrap.json").write_text(json.dumps(dict(iterations=10000, seed=0,
    comparisons=contrasts), ensure_ascii=False, indent=2)+"\n")
with (OUT / "comparison.csv").open("w",newline="") as f:
    writer=csv.writer(f)
    writer.writerow(["configuration","run_id","n_success",*METRICS,"exact_count","prompt_tokens","completion_tokens"])
    for r in runs:
        m=r["metrics"]
        writer.writerow([r["label"],r["cfg"]["run_id"],m["n_success"],*[m[k] for k in METRICS],
                         r["exact"],m["tokens"]["prompt_tokens"],m["tokens"]["completion_tokens"]])

lines=["# 多任务 v4、v4b 与 v5 对比", "", "## 实验口径", "",
"开发集（development set / dev，官方提供的开发评估数据）共 143 条；以下每组均完整评测。无示例提示（zero-shot，不提供已标注示例）对比少样本提示（few-shot，在输入中提供已标注示例）。",
"BM25（Best Matching 25，按文本相关性检索示例的方法）和 random（随机选择示例）均沿用固定选择文件；random 的随机种子（random seed，用于复现随机选择）为 0。",
"v4b 沿用 v4 系统指令，仅在待判断样本末尾增加输出格式提醒；v5 是 v4 加入提炼规则。模型参数和文件摘要见各运行 config.json。",
"平均绝对误差（Mean Absolute Error / MAE，预测等级与标准等级的绝对差取平均）越低越好；平均交并比（Mean Jaccard，逐条计算标签交集占并集比例再取平均）越高越好。三字段全对表示风险等级、风险领域标签集合和风险驱动标签集合同时正确。", "",
"## dev 完整结果", "",
"| 配置 | run_id / 来源 | 完成数 | MAE ↓ | 领域 Jaccard ↑ | 驱动 Jaccard ↑ | 三字段全对 |",
"|---|---|---:|---:|---:|---:|---:|"]
for r in runs:
    m=r["metrics"]
    # OUT is results/analysis/multitask/<name>; three parents lead to results.
    rel=Path("../../..") / r["path"].relative_to(ROOT/"results")
    lines.append(f"| {r['label']} | [{r['cfg']['run_id']}]({rel}/metrics.json) | {m['n_success']}/143 | "
                 + " | ".join(f"{m[k]:.4f}" for k in METRICS)+f" | {r['exact']}/143 |")
lines += ["", "## 结果分析", "",
"以下判断对应上表的固定 run_id，差异区间见下一节。",
"",
"- v5 在 dev 上三个指标均比 v4 退步，三个差异的逐项 95% 区间均不包含 0，方向与 train_val 一致。当前规则版本没有显示出改善；汇总结果不能单独定位到某条规则。",
"- BM25 k=5 的 MAE 最低；BM25 k=10 的三字段全对数最多。两者三个指标的配对差异区间均包含 0，不能据此认定其中一个稳定更好。k=5 使用较少示例，可作为成本优先的候选。",
"- random k=3 的领域指标最高，其相对 v4 的改善区间不包含 0；但其 MAE 与 v4 相同。当前没有一个配置在所有指标上同时最佳。",
"- 同 k 比较：k=5 时 BM25 的 MAE 优于 random，差异区间不包含 0；k=3 时 random 的领域指标优于 BM25，差异区间不包含 0。k=10 的三个差异区间都包含 0。因此不能概括为检索方法在所有设置下更好。",
"- 增加 k 并未带来一致改善：BM25 三个 k 间的差异区间都包含 0；random 从 k=3 增加到 k=5 或 k=10 时，领域指标反而降低，相关区间不包含 0。这里只检验了 random 种子 0。",
"- 相对 v4，BM25 k=5、10 的领域指标有改善证据；其风险等级和风险驱动的改善区间仍包含 0。上述区间均未进行多重比较校正，宜作为探索性证据。",
"", "## 配对差异", "",
"配对自举（paired bootstrap，在同一组样本上成对重复抽样以估计指标差异的不确定性）使用 10,000 次抽样、种子 0。置信区间（confidence interval / CI，描述重采样得到的差异范围）为逐项 95% 区间，未校正多重比较。差异均为候选减基准，MAE 负值较好，Jaccard 正值较好；区间跨越 0 时证据不足以判定稳定改善或退步。", "",
"| 基准 → 候选 | ΔMAE [95% CI] | Δ领域 [95% CI] | Δ驱动 [95% CI] |",
"|---|---:|---:|---:|"]
for c in contrasts:
    cells=[]
    for key in ("mae","domain","driver"):
        d=c["metrics"][key]; lo,hi=d["ci95"]
        cells.append(f"{d['difference']:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    lines.append(f"| {c['base']} → {c['candidate']} | "+" | ".join(cells)+" |")

lines += ["", "## v5 的训练内部验证结果", "",
"训练内部验证集（train_val，从训练数据划出且不用于规则提炼的数据子集）单独展示，不与 dev 合并。", "",
"| 配置 | run_id | 完成数 | MAE ↓ | 领域 Jaccard ↑ | 驱动 Jaccard ↑ |", "|---|---|---:|---:|---:|---:|"]
for version,run_id in (("v4","20261103-102236"),("v5","20261103-113649")):
    p=ROOT/f"results/_smoke/multitask/zero-shot-{version}/{run_id}"
    subprocess.run([sys.executable,str(ROOT/"src/evaluate.py"),str(p)],check=True,stdout=subprocess.DEVNULL)
    m=json.loads((p/"metrics.json").read_text())
    lines.append(f"| zero-shot {version} | [{run_id}](../../../_smoke/multitask/zero-shot-{version}/{run_id}/metrics.json) | {m['n_success']}/{m['n_total']} | "+" | ".join(f"{m[k]:.4f}" for k in METRICS)+" |")

lines += ["", "## 复算与限制", "",
"在仓库根目录执行：", "", "```bash",
".venv/bin/python results/analysis/multitask/v4-v4b-v5-20261104/reproduce.py", "```", "",
"该脚本逐组调用 src/evaluate.py 和 src/analyze.py，再生成本表、comparison.csv 和 paired-bootstrap.json；不会调用模型。单组分数可直接通过 src/evaluate.py <运行目录> 复算。",
"本次补充 v5 的 dev 结果是用户明确要求的事后对照：v5 在 train_val 上三个指标已退步，未通过原实验计划的验证关卡。dev 已用于历史实验选择，不能把这些比较当作独立隐藏测试结果；random 仅一个种子，尚不能评估随机选择的种子间波动。",
"BM25 k=3 初次在沙箱内连接失败，保留原始错误记录后在同一 run_id 联网继续；失败连接不产生有效预测，其 token 用量以服务响应记录为准。", ""]
(OUT/"comparison.md").write_text("\n".join(lines),encoding="utf-8")
print(OUT/"comparison.md")
for r in runs:
    print(r["label"],r["cfg"]["run_id"],*[round(r["metrics"][k],6) for k in METRICS])
