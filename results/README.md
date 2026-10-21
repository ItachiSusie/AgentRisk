# Results

目录结构：`results/<模型>/<策略>-<版本>/<run_id>/`，`run_id` 是运行开始时的时间戳。每次运行一个独立目录，不覆盖旧结果。

## 正式 baseline

| 运行 | 说明 |
| --- | --- |
| `deepseek-flash/zero-shot-v1/20261022-051556/` | zero-shot v1，完整 dev，143/143 条合法预测 |

## 每个运行目录里的文件

| 文件 | 内容 |
| --- | --- |
| `prompt.txt` | 本次实际使用的完整 instruction |
| `config.json` | 数据版本和 hash、模型、参数、prompt hash、SDK 版本、每次启动的记录 |
| `predictions.jsonl` | 每条样本的 `example_id` 和三个预测字段 |
| `raw_responses.jsonl` | 每次尝试的原始响应、耗时、错误和 token 用量（重试也在里面） |
| `metrics.json` | `evaluate.py` 生成：样本数、成功/失败数、三个指标、token 总量 |
| `report.html` | `analyze.py` 生成：交互式分析报告，双击用浏览器打开 |
| `error_analysis.md` | 人工写的错误分析和下一轮假设（还没有） |

## 其他

- `_smoke/` 是本地试跑结果（如用 train 前几条检查 API），不提交。
- `predictions.jsonl` 是本地结果格式，不是已确认的比赛提交格式。
