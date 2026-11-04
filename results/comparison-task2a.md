# 运行对比 — Task 2a 损害领域

由 `src/compare.py --task task2a` 生成，不要手改。数据：dev 143 条；指标：2a Jaccard（越高越好）。

> 单个运行只有 143 条样本，指标差 0.02–0.03 很可能是噪声；看方向是否一致，不要把小差异当结论。

## 1. 指标

| 运行 | version | selection | seed | k | run_id | 2a Jaccard | Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | answer-v1 | - | - | 0 | 20261104-085334 | 0.837 |  |
| few-shot-random-s0-k3-answer-v1 | answer-v1 | random | 0 | 3 | 20261104-085337 | 0.829 | -0.008 |
| few-shot-random-s0-k5-answer-v1 | answer-v1 | random | 0 | 5 | 20261104-085341 | 0.840 | +0.003 |
| few-shot-random-s0-k10-answer-v1 | answer-v1 | random | 0 | 10 | 20261104-085344 | 0.838 | +0.001 |
| few-shot-random-s0-k20-answer-v1 | answer-v1 | random | 0 | 20 | 20261104-085347 | 0.851 | +0.014 |
| few-shot-bm25-k3-answer-v1 | answer-v1 | bm25 | - | 3 | 20261104-085336 | 0.845 | +0.008 |
| few-shot-bm25-k5-answer-v1 | answer-v1 | bm25 | - | 5 | 20261104-085339 | 0.839 | +0.002 |
| few-shot-bm25-k10-answer-v1 | answer-v1 | bm25 | - | 10 | 20261104-085342 | 0.857 | +0.020 |
| few-shot-bm25-k20-answer-v1 | answer-v1 | bm25 | - | 20 | 20261104-085345 | 0.843 | +0.006 |
| zero-shot-answer-v2 | answer-v2 | - | - | 0 | 20261104-091349 | 0.862 | +0.026 |
| zero-shot-reason-v1 | reason-v1 | - | - | 0 | 20261104-085349 | 0.832 | -0.005 |
| few-shot-random-s0-k3-reason-v1 | reason-v1 | random | 0 | 3 | 20261104-085354 | 0.869 | +0.033 |
| few-shot-random-s0-k5-reason-v1 | reason-v1 | random | 0 | 5 | 20261104-085358 | 0.860 | +0.023 |
| few-shot-random-s0-k10-reason-v1 | reason-v1 | random | 0 | 10 | 20261104-085403 | 0.832 | -0.005 |
| few-shot-random-s0-k20-reason-v1 | reason-v1 | random | 0 | 20 | 20261104-085407 | 0.853 | +0.016 |
| few-shot-bm25-k3-reason-v1 | reason-v1 | bm25 | - | 3 | 20261104-085351 | 0.861 | +0.024 |
| few-shot-bm25-k5-reason-v1 | reason-v1 | bm25 | - | 5 | 20261104-085356 | 0.850 | +0.013 |
| few-shot-bm25-k10-reason-v1 | reason-v1 | bm25 | - | 10 | 20261104-085400 | 0.850 | +0.013 |
| few-shot-bm25-k20-reason-v1 | reason-v1 | bm25 | - | 20 | 20261104-085405 | 0.867 | +0.030 |
| zero-shot-reason-v2 | reason-v2 | - | - | 0 | 20261104-091409 | 0.866 | +0.029 |

Δ 是相对 `zero-shot-answer-v1` 的差（表里第一个 zero-shot 运行）。MAE 的 Δ 为负、Jaccard 的 Δ 为正表示变好。跨输出格式线的行（例如 reason-* 对 answer-* 的 zero-shot）也按这个基准算，要比同一条线内部的差，看第 2 节或用 `src/paired_bootstrap.py` 指定基准。

## 2. 逐条对比 zero-shot（1 − Jaccard）

| 运行 | 总损失 | 变好的样本 | 变差的样本 | 不变 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 23.33 | 0 | 0 | 143 |
| few-shot-random-s0-k3-answer-v1 | 24.50 | 5 | 6 | 132 |
| few-shot-random-s0-k5-answer-v1 | 22.83 | 7 | 5 | 131 |
| few-shot-random-s0-k10-answer-v1 | 23.17 | 9 | 8 | 126 |
| few-shot-random-s0-k20-answer-v1 | 21.33 | 12 | 9 | 122 |
| few-shot-bm25-k3-answer-v1 | 22.17 | 13 | 10 | 120 |
| few-shot-bm25-k5-answer-v1 | 23.00 | 14 | 12 | 117 |
| few-shot-bm25-k10-answer-v1 | 20.50 | 14 | 9 | 120 |
| few-shot-bm25-k20-answer-v1 | 22.50 | 13 | 12 | 118 |
| zero-shot-answer-v2 | 19.67 | 14 | 7 | 122 |
| zero-shot-reason-v1 | 24.00 | 16 | 16 | 111 |
| few-shot-random-s0-k3-reason-v1 | 18.67 | 16 | 9 | 118 |
| few-shot-random-s0-k5-reason-v1 | 20.00 | 16 | 9 | 118 |
| few-shot-random-s0-k10-reason-v1 | 24.00 | 13 | 13 | 117 |
| few-shot-random-s0-k20-reason-v1 | 21.00 | 16 | 11 | 116 |
| few-shot-bm25-k3-reason-v1 | 19.83 | 22 | 15 | 106 |
| few-shot-bm25-k5-reason-v1 | 21.50 | 20 | 16 | 107 |
| few-shot-bm25-k10-reason-v1 | 21.50 | 19 | 15 | 109 |
| few-shot-bm25-k20-reason-v1 | 19.00 | 20 | 13 | 110 |
| zero-shot-reason-v2 | 19.17 | 17 | 10 | 116 |

变好的样本明显多于变差的样本，比指标的差值更能说明改善是否稳定；两者相近则更可能是噪声。

## 5. 每条样本给的标签个数

| 运行 | domain 给 2 个 |
| --- | --- |
| **标准答案** | 29 |
| zero-shot-answer-v1 | 27 |
| few-shot-random-s0-k3-answer-v1 | 29 |
| few-shot-random-s0-k5-answer-v1 | 26 |
| few-shot-random-s0-k10-answer-v1 | 30 |
| few-shot-random-s0-k20-answer-v1 | 27 |
| few-shot-bm25-k3-answer-v1 | 35 |
| few-shot-bm25-k5-answer-v1 | 34 |
| few-shot-bm25-k10-answer-v1 | 30 |
| few-shot-bm25-k20-answer-v1 | 28 |
| zero-shot-answer-v2 | 18 |
| zero-shot-reason-v1 | 35 |
| few-shot-random-s0-k3-reason-v1 | 29 |
| few-shot-random-s0-k5-reason-v1 | 28 |
| few-shot-random-s0-k10-reason-v1 | 27 |
| few-shot-random-s0-k20-reason-v1 | 21 |
| few-shot-bm25-k3-reason-v1 | 30 |
| few-shot-bm25-k5-reason-v1 | 34 |
| few-shot-bm25-k10-reason-v1 | 30 |
| few-shot-bm25-k20-reason-v1 | 23 |
| zero-shot-reason-v2 | 12 |

## 7. token 用量（含重试）

| 运行 | 请求次数 | 输入 | 其中缓存未命中 | 输出 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 143 | 212,624 | 156,048 | 1,923 |
| few-shot-random-s0-k3-answer-v1 | 143 | 700,583 | 605,479 | 1,932 |
| few-shot-random-s0-k5-answer-v1 | 143 | 1,038,141 | 529,853 | 1,914 |
| few-shot-random-s0-k10-answer-v1 | 143 | 1,849,959 | 1,004,007 | 1,942 |
| few-shot-random-s0-k20-answer-v1 | 143 | 3,519,018 | 1,861,290 | 1,921 |
| few-shot-bm25-k3-answer-v1 | 143 | 761,799 | 625,479 | 1,968 |
| few-shot-bm25-k5-answer-v1 | 143 | 1,143,421 | 930,173 | 1,961 |
| few-shot-bm25-k10-answer-v1 | 143 | 2,037,132 | 1,861,900 | 1,939 |
| few-shot-bm25-k20-answer-v1 | 143 | 3,813,793 | 3,648,545 | 1,929 |
| zero-shot-answer-v2 | 143 | 267,822 | 156,590 | 1,875 |
| zero-shot-reason-v1 | 143 | 240,652 | 148,108 | 16,286 |
| few-shot-random-s0-k3-reason-v1 | 143 | 733,672 | 604,776 | 15,612 |
| few-shot-random-s0-k5-reason-v1 | 143 | 1,071,230 | 535,038 | 15,452 |
| few-shot-random-s0-k10-reason-v1 | 143 | 1,883,048 | 1,010,088 | 15,418 |
| few-shot-random-s0-k20-reason-v1 | 143 | 3,552,107 | 1,866,219 | 15,191 |
| few-shot-bm25-k3-reason-v1 | 143 | 794,888 | 624,776 | 15,682 |
| few-shot-bm25-k5-reason-v1 | 143 | 1,176,510 | 943,806 | 15,631 |
| few-shot-bm25-k10-reason-v1 | 143 | 2,070,221 | 1,864,781 | 15,720 |
| few-shot-bm25-k20-reason-v1 | 143 | 3,846,882 | 3,651,938 | 15,830 |
| zero-shot-reason-v2 | 143 | 333,745 | 151,345 | 15,873 |

## 8. 完整性检查

| 运行 | 143/143 | 同 prompts/single/task2a/zero_shot_answer_v1.txt | 模型 | 参数同 zero-shot | prompt_preview | messages |
| --- | --- | --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | - | - |
| few-shot-random-s0-k3-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k5-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k10-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k20-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k3-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k5-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k10-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k20-answer-v1 | ✓ | ✓ | deepseek-flash | ✓ | ✓ | ✓ |
| zero-shot-answer-v2 | ✓ | ✗ | deepseek-flash | ✓ | - | - |
| zero-shot-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | - | - |
| few-shot-random-s0-k3-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k5-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k10-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-random-s0-k20-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k3-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k5-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k10-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| few-shot-bm25-k20-reason-v1 | ✓ | ✗ | deepseek-flash | ✓ | ✓ | ✓ |
| zero-shot-reason-v2 | ✓ | ✗ | deepseek-flash | ✓ | - | - |
