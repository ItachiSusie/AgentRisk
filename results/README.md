# Results

目录结构：`results/<模型>/<实验名>/<run_id>/`，`run_id` 是运行开始时的时间戳。每次运行一个独立目录，不覆盖旧结果。

实验名：

| 实验名 | 含义 |
| --- | --- |
| `zero-shot-v1` | zero-shot，prompt 版本 v1 |
| `few-shot-random-s<seed>-k<k>-v1` | 每条 dev 样本随机抽 k 个 train 示例，种子 `<seed>` |
| `few-shot-bm25-k<k>-v1` | 每条 dev 样本用 BM25（只用 `formatted_interaction`）检索 k 个最相似的 train 示例 |
| `few-shot-bm25-action-k<k>-v1` | 同上，检索文本加上 `proposed_action`（选择文件已备好，尚未运行） |
| `zero-shot-v2` / `few-shot-bm25-k10-v2` | 换成蒸馏版 instruction `prompts/zero_shot_v2.txt`（5 条规则），few-shot 规格见 `prompts/few_shot_v2.json` |

末尾的 `v1` 是 few-shot 拼装规范 `prompts/few_shot_v1.json` 的版本，不表示种子。换种子请看实验名里的 `s<seed>`。每个运行的 `config.json` 记录了 selection / seed / k 和选择文件的 SHA-256。

## 正式 baseline

| 运行 | 说明 |
| --- | --- |
| `deepseek-flash/zero-shot-v1/20261022-051556/` | zero-shot v1，完整 dev，143/143 条合法预测 |
| `deepseek-flash/few-shot-random-s0-k{3,5,10}-v1/` | few-shot 随机组，seed 0，各 143/143 |
| `deepseek-flash/few-shot-bm25-k{3,5,10}-v1/` | few-shot BM25 组，各 143/143 |
| `deepseek-flash/few-shot-random-s0-k20-v1/20261027-225811/` | 随机组 k=20（selection `random_seed0_top20.json`），143/143 |
| `deepseek-flash/few-shot-bm25-k20-v1/20261027-225802/` | BM25 组 k=20（selection `bm25_dev_top20.json`），143/143 |
| `deepseek-flash/zero-shot-v2/20261028-002357/` | zero-shot + 蒸馏规则 v2，143/143；MAE 0.287，与 v1 的差在噪声内 |
| `deepseek-flash/few-shot-bm25-k10-v2/20261028-095023/` | bm25 k=10 + 蒸馏规则 v2，143/143；与 bm25 k=10 + v1 完全相同（MAE 0.189） |

## 汇总

- **[EXPERIMENTS_ALL.md](EXPERIMENTS_ALL.md)：覆盖所有已归档开发集实验的大表**，每个任务并列无推理与有推理分数，含缺失配置、未完成运行说明和每格的 run_id 来源。[CSV 明细](EXPERIMENTS_ALL.csv) 保留未舍入分数；由 `python3 src/make_experiment_table.py` 生成，加 `--gold data/raw/dev.jsonl` 可复核全部指标且不修改历史运行。
- **[SUMMARY.md](SUMMARY.md)：单任务 vs 多任务的主表**（`python src/make_summary.py` 生成，不要手改）。
  每个子任务一张表，行是配置（zero-shot / few-shot random / few-shot BM25 / trace2skill），
  两列是无推理与有推理两条输出格式线，另有三任务合并后的「三字段全对」对照和 run_id 附录。
- [comparison-task1.md](comparison-task1.md) / [comparison-task2a.md](comparison-task2a.md) /
  [comparison-task2b.md](comparison-task2b.md)：单任务的逐条样本细表（`python src/compare.py --task <task>` 生成）。
- [comparison.md](comparison.md)：11 个配置并排对比（`python src/compare.py` 生成，不要手改）。
- [comparison.html](comparison.html)：同一批运行的交互版（`python src/compare_html.py` 生成）。k 曲线可切三个指标、排行榜可点开混淆矩阵、样本级对比可选任意两个运行。单文件，离线可开。
- [few-shot-error-analysis.md](few-shot-error-analysis.md)：10 月 25 日的错误分析草稿，**已被取代**，现行做法是每个 run 目录下的 `triage/summary.md`（`python src/triage.py <run_dir>`）。

## 每个运行目录里的文件

| 文件 | 内容 |
| --- | --- |
| `prompt.txt` | 本次实际使用的 system prompt |
| `prompt_preview.txt` | 仅 few-shot：第一条样本收到的完整消息，可读 |
| `messages.jsonl.gz` | 仅 few-shot：每条样本实际发出的完整消息（含示例）；用 `python src/fewshot.py render --run-dir <run_dir> --id <example_id>` 查看某一条。**本地生成，不入库**（k=20 时单个 3–4 MB），clone 后需自己重跑才有 |
| `config.json` | 数据版本和 hash、模型、参数、prompt hash、SDK 版本、每次启动的记录 |
| `predictions.jsonl` | 每条样本的 `example_id` 和三个预测字段 |
| `raw_responses.jsonl` | 每次尝试的原始响应、耗时、错误和 token 用量（重试也在里面） |
| `metrics.json` | `evaluate.py` 生成：样本数、成功/失败数、三个指标、token 总量 |
| `report.html` | `analyze.py` 生成：交互式分析报告，双击用浏览器打开 |
| `error_analysis.md` | 人工写的错误分析和下一轮假设（zero-shot 的还没有；few-shot 的见上面的汇总文件） |

## 其他

- `_smoke/` 是本地试跑结果（如用 train 前几条检查 API），不提交。
- `predictions.jsonl` 是本地结果格式，不是已确认的比赛提交格式。
