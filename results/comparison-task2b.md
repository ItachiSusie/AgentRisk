# 运行对比 — Task 2b 风险成因

由 `src/compare.py --task task2b` 生成，不要手改。数据：dev 143 条；指标：2b Jaccard（越高越好）。

> 单个运行只有 143 条样本，指标差 0.02–0.03 很可能是噪声；看方向是否一致，不要把小差异当结论。

## 1. 指标

| 运行 | version | selection | seed | k | run_id | 2b Jaccard | Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | answer-v1 | - | - | 0 | 20261104-092353 | 0.711 |  |
| few-shot-random-s0-k3-answer-v1 | answer-v1 | random | 0 | 3 | 20261104-092356 | 0.719 | +0.008 |
| few-shot-random-s0-k5-answer-v1 | answer-v1 | random | 0 | 5 | 20261104-092359 | 0.716 | +0.005 |
| few-shot-random-s0-k10-answer-v1 | answer-v1 | random | 0 | 10 | 20261104-092404 | 0.732 | +0.021 |
| few-shot-random-s0-k20-answer-v1 | answer-v1 | random | 0 | 20 | 20261104-092407 | 0.751 | +0.040 |
| few-shot-bm25-k3-answer-v1 | answer-v1 | bm25 | - | 3 | 20261104-092354 | 0.741 | +0.030 |
| few-shot-bm25-k5-answer-v1 | answer-v1 | bm25 | - | 5 | 20261104-092358 | 0.765 | +0.054 |
| few-shot-bm25-k10-answer-v1 | answer-v1 | bm25 | - | 10 | 20261104-092401 | 0.786 | +0.075 |
| few-shot-bm25-k20-answer-v1 | answer-v1 | bm25 | - | 20 | 20261104-092405 | 0.772 | +0.061 |
| zero-shot-answer-v2 | answer-v2 | - | - | 0 | 20261104-094630 | 0.716 | +0.005 |
| zero-shot-reason-v1 | reason-v1 | - | - | 0 | 20261104-092410 | 0.753 | +0.042 |
| few-shot-random-s0-k3-reason-v1 | reason-v1 | random | 0 | 3 | 20261104-092414 | 0.741 | +0.030 |
| few-shot-random-s0-k5-reason-v1 | reason-v1 | random | 0 | 5 | 20261104-092419 | 0.772 | +0.061 |
| few-shot-random-s0-k10-reason-v1 | reason-v1 | random | 0 | 10 | 20261104-092424 | 0.746 | +0.035 |
| few-shot-random-s0-k20-reason-v1 | reason-v1 | random | 0 | 20 | 20261104-092430 | 0.769 | +0.058 |
| few-shot-bm25-k3-reason-v1 | reason-v1 | bm25 | - | 3 | 20261104-092412 | 0.756 | +0.045 |
| few-shot-bm25-k5-reason-v1 | reason-v1 | bm25 | - | 5 | 20261104-092417 | 0.762 | +0.051 |
| few-shot-bm25-k10-reason-v1 | reason-v1 | bm25 | - | 10 | 20261104-092421 | 0.770 | +0.059 |
| few-shot-bm25-k20-reason-v1 | reason-v1 | bm25 | - | 20 | 20261104-092427 | 0.769 | +0.058 |
| zero-shot-reason-v2 | reason-v2 | - | - | 0 | 20261104-094648 | 0.703 | -0.008 |

Δ 是相对 `zero-shot-answer-v1` 的差（表里第一个 zero-shot 运行）。MAE 的 Δ 为负、Jaccard 的 Δ 为正表示变好。跨输出格式线的行（例如 reason-* 对 answer-* 的 zero-shot）也按这个基准算，要比同一条线内部的差，看第 2 节或用 `src/paired_bootstrap.py` 指定基准。

## 2. 逐条对比 zero-shot（1 − Jaccard）

| 运行 | 总损失 | 变好的样本 | 变差的样本 | 不变 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 41.33 | 0 | 0 | 143 |
| few-shot-random-s0-k3-answer-v1 | 40.17 | 10 | 6 | 127 |
| few-shot-random-s0-k5-answer-v1 | 40.67 | 10 | 7 | 126 |
| few-shot-random-s0-k10-answer-v1 | 38.33 | 15 | 7 | 121 |
| few-shot-random-s0-k20-answer-v1 | 35.67 | 19 | 7 | 117 |
| few-shot-bm25-k3-answer-v1 | 37.00 | 18 | 9 | 116 |
| few-shot-bm25-k5-answer-v1 | 33.67 | 21 | 6 | 116 |
| few-shot-bm25-k10-answer-v1 | 30.67 | 23 | 5 | 115 |
| few-shot-bm25-k20-answer-v1 | 32.67 | 22 | 6 | 115 |
| zero-shot-answer-v2 | 40.67 | 20 | 19 | 104 |
| zero-shot-reason-v1 | 35.33 | 15 | 5 | 123 |
| few-shot-random-s0-k3-reason-v1 | 37.00 | 15 | 7 | 121 |
| few-shot-random-s0-k5-reason-v1 | 32.67 | 20 | 4 | 119 |
| few-shot-random-s0-k10-reason-v1 | 36.33 | 18 | 6 | 119 |
| few-shot-random-s0-k20-reason-v1 | 33.00 | 20 | 5 | 118 |
| few-shot-bm25-k3-reason-v1 | 34.83 | 22 | 6 | 115 |
| few-shot-bm25-k5-reason-v1 | 34.00 | 18 | 4 | 121 |
| few-shot-bm25-k10-reason-v1 | 32.83 | 22 | 5 | 116 |
| few-shot-bm25-k20-reason-v1 | 33.00 | 22 | 4 | 117 |
| zero-shot-reason-v2 | 42.50 | 22 | 22 | 99 |

变好的样本明显多于变差的样本，比指标的差值更能说明改善是否稳定；两者相近则更可能是噪声。

## 5. 每条样本给的标签个数

| 运行 | driver 给 2 个 |
| --- | --- |
| **标准答案** | 56 |
| zero-shot-answer-v1 | 70 |
| few-shot-random-s0-k3-answer-v1 | 70 |
| few-shot-random-s0-k5-answer-v1 | 70 |
| few-shot-random-s0-k10-answer-v1 | 69 |
| few-shot-random-s0-k20-answer-v1 | 69 |
| few-shot-bm25-k3-answer-v1 | 69 |
| few-shot-bm25-k5-answer-v1 | 68 |
| few-shot-bm25-k10-answer-v1 | 69 |
| few-shot-bm25-k20-answer-v1 | 67 |
| zero-shot-answer-v2 | 69 |
| zero-shot-reason-v1 | 70 |
| few-shot-random-s0-k3-reason-v1 | 70 |
| few-shot-random-s0-k5-reason-v1 | 69 |
| few-shot-random-s0-k10-reason-v1 | 69 |
| few-shot-random-s0-k20-reason-v1 | 69 |
| few-shot-bm25-k3-reason-v1 | 67 |
| few-shot-bm25-k5-reason-v1 | 69 |
| few-shot-bm25-k10-reason-v1 | 67 |
| few-shot-bm25-k20-reason-v1 | 65 |
| zero-shot-reason-v2 | 71 |

## 7. token 用量（含重试）

| 运行 | 请求次数 | 输入 | 其中缓存未命中 | 输出 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 143 | 209,621 | 152,661 | 2,367 |
| few-shot-random-s0-k3-answer-v1 | 144 | 703,358 | 604,542 | 2,400 |
| few-shot-random-s0-k5-answer-v1 | 143 | 1,037,150 | 530,654 | 2,396 |
| few-shot-random-s0-k10-answer-v1 | 143 | 1,850,849 | 1,005,025 | 2,388 |
| few-shot-random-s0-k20-answer-v1 | 143 | 3,523,938 | 1,865,186 | 2,386 |
| few-shot-bm25-k3-answer-v1 | 143 | 759,916 | 632,428 | 2,371 |
| few-shot-bm25-k5-answer-v1 | 143 | 1,142,285 | 931,469 | 2,372 |
| few-shot-bm25-k10-answer-v1 | 143 | 2,038,140 | 1,865,468 | 2,380 |
| few-shot-bm25-k20-answer-v1 | 143 | 3,819,107 | 3,656,163 | 2,374 |
| zero-shot-answer-v2 | 143 | 249,232 | 156,304 | 2,466 |
| zero-shot-reason-v1 | 143 | 236,505 | 158,041 | 16,751 |
| few-shot-random-s0-k3-reason-v1 | 143 | 730,701 | 612,813 | 15,984 |
| few-shot-random-s0-k5-reason-v1 | 143 | 1,069,095 | 535,335 | 16,051 |
| few-shot-random-s0-k10-reason-v1 | 143 | 1,882,794 | 1,011,498 | 15,877 |
| few-shot-random-s0-k20-reason-v1 | 143 | 3,555,883 | 1,870,379 | 15,737 |
| few-shot-bm25-k3-reason-v1 | 143 | 791,861 | 636,597 | 16,420 |
| few-shot-bm25-k5-reason-v1 | 143 | 1,174,230 | 946,390 | 16,316 |
| few-shot-bm25-k10-reason-v1 | 143 | 2,070,085 | 1,870,533 | 16,125 |
| few-shot-bm25-k20-reason-v1 | 143 | 3,851,052 | 3,661,996 | 16,170 |
| zero-shot-reason-v2 | 143 | 332,887 | 149,975 | 16,780 |

## 8. 完整性检查

| 运行 | 143/143 | 同 prompts/single/task2b/zero_shot_answer_v1.txt | 模型 | 参数同 zero-shot | prompt_preview | messages |
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
