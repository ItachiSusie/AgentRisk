# 运行对比 — Task 1 风险严重度

由 `src/compare.py --task task1` 生成，不要手改。数据：dev 143 条；指标：MAE（越低越好）。

> 单个运行只有 143 条样本，指标差 0.02–0.03 很可能是噪声；看方向是否一致，不要把小差异当结论。

## 1. 指标

| 运行 | version | selection | seed | k | run_id | MAE | Δ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | answer-v1 | - | - | 0 | 20261104-081736 | 0.266 |  |
| few-shot-random-s0-k3-answer-v1 | answer-v1 | random | 0 | 3 | 20261104-081739 | 0.287 | +0.021 |
| few-shot-random-s0-k5-answer-v1 | answer-v1 | random | 0 | 5 | 20261104-081742 | 0.259 | -0.007 |
| few-shot-random-s0-k10-answer-v1 | answer-v1 | random | 0 | 10 | 20261104-081745 | 0.224 | -0.042 |
| few-shot-random-s0-k20-answer-v1 | answer-v1 | random | 0 | 20 | 20261104-084301 | 0.224 | -0.042 |
| few-shot-bm25-k3-answer-v1 | answer-v1 | bm25 | - | 3 | 20261104-081738 | 0.273 | +0.007 |
| few-shot-bm25-k5-answer-v1 | answer-v1 | bm25 | - | 5 | 20261104-081741 | 0.238 | -0.028 |
| few-shot-bm25-k10-answer-v1 | answer-v1 | bm25 | - | 10 | 20261104-081743 | 0.196 | -0.070 |
| few-shot-bm25-k20-answer-v1 | answer-v1 | bm25 | - | 20 | 20261104-084259 | 0.203 | -0.063 |
| zero-shot-answer-v2 | answer-v2 | - | - | 0 | 20261104-084308 | 0.350 | +0.084 |
| zero-shot-reason-v1 | reason-v1 | - | - | 0 | 20261104-081746 | 0.238 | -0.028 |
| few-shot-random-s0-k3-reason-v1 | reason-v1 | random | 0 | 3 | 20261104-081750 | 0.189 | -0.077 |
| few-shot-random-s0-k5-reason-v1 | reason-v1 | random | 0 | 5 | 20261104-081754 | 0.252 | -0.014 |
| few-shot-random-s0-k10-reason-v1 | reason-v1 | random | 0 | 10 | 20261104-081758 | 0.217 | -0.049 |
| few-shot-random-s0-k20-reason-v1 | reason-v1 | random | 0 | 20 | 20261104-084305 | 0.231 | -0.035 |
| few-shot-bm25-k3-reason-v1 | reason-v1 | bm25 | - | 3 | 20261104-081748 | 0.273 | +0.007 |
| few-shot-bm25-k5-reason-v1 | reason-v1 | bm25 | - | 5 | 20261104-081752 | 0.210 | -0.056 |
| few-shot-bm25-k10-reason-v1 | reason-v1 | bm25 | - | 10 | 20261104-081756 | 0.189 | -0.077 |
| few-shot-bm25-k20-reason-v1 | reason-v1 | bm25 | - | 20 | 20261104-084303 | 0.154 | -0.112 |
| zero-shot-reason-v2 | reason-v2 | - | - | 0 | 20261104-084309 | 0.336 | +0.070 |

Δ 是相对 `zero-shot-answer-v1` 的差（表里第一个 zero-shot 运行）。MAE 的 Δ 为负、Jaccard 的 Δ 为正表示变好。跨输出格式线的行（例如 reason-* 对 answer-* 的 zero-shot）也按这个基准算，要比同一条线内部的差，看第 2 节或用 `src/paired_bootstrap.py` 指定基准。

## 2. 逐条对比 zero-shot（等级误差）

| 运行 | 总损失 | 变好的样本 | 变差的样本 | 不变 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 38.00 | 0 | 0 | 143 |
| few-shot-random-s0-k3-answer-v1 | 41.00 | 5 | 8 | 130 |
| few-shot-random-s0-k5-answer-v1 | 37.00 | 7 | 6 | 130 |
| few-shot-random-s0-k10-answer-v1 | 32.00 | 9 | 3 | 131 |
| few-shot-random-s0-k20-answer-v1 | 32.00 | 8 | 2 | 133 |
| few-shot-bm25-k3-answer-v1 | 39.00 | 4 | 5 | 134 |
| few-shot-bm25-k5-answer-v1 | 34.00 | 9 | 5 | 129 |
| few-shot-bm25-k10-answer-v1 | 28.00 | 14 | 4 | 125 |
| few-shot-bm25-k20-answer-v1 | 29.00 | 15 | 6 | 122 |
| zero-shot-answer-v2 | 50.00 | 7 | 19 | 117 |
| zero-shot-reason-v1 | 34.00 | 15 | 11 | 117 |
| few-shot-random-s0-k3-reason-v1 | 27.00 | 19 | 8 | 116 |
| few-shot-random-s0-k5-reason-v1 | 36.00 | 13 | 11 | 119 |
| few-shot-random-s0-k10-reason-v1 | 31.00 | 15 | 8 | 120 |
| few-shot-random-s0-k20-reason-v1 | 33.00 | 16 | 11 | 116 |
| few-shot-bm25-k3-reason-v1 | 39.00 | 10 | 10 | 123 |
| few-shot-bm25-k5-reason-v1 | 30.00 | 14 | 6 | 123 |
| few-shot-bm25-k10-reason-v1 | 27.00 | 15 | 4 | 124 |
| few-shot-bm25-k20-reason-v1 | 22.00 | 20 | 4 | 119 |
| zero-shot-reason-v2 | 48.00 | 14 | 24 | 105 |

变好的样本明显多于变差的样本，比指标的差值更能说明改善是否稳定；两者相近则更可能是噪声。

## 3. 各标准等级的 MAE

| 运行 | gold 1 | gold 2 | gold 3 | gold 4 | gold 5 | 平均偏差（预测−标准） |
| --- | --- | --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 0.000 | 0.875 | 0.781 | 0.143 | 0.500 | +0.112 |
| few-shot-random-s0-k3-answer-v1 | 0.015 | 0.875 | 0.781 | 0.229 | 0.000 | +0.203 |
| few-shot-random-s0-k5-answer-v1 | 0.000 | 0.875 | 0.750 | 0.171 | 0.000 | +0.175 |
| few-shot-random-s0-k10-answer-v1 | 0.015 | 0.875 | 0.656 | 0.086 | 0.000 | +0.126 |
| few-shot-random-s0-k20-answer-v1 | 0.000 | 0.875 | 0.656 | 0.086 | 0.500 | +0.098 |
| few-shot-bm25-k3-answer-v1 | 0.000 | 0.875 | 0.781 | 0.200 | 0.000 | +0.147 |
| few-shot-bm25-k5-answer-v1 | 0.015 | 0.875 | 0.656 | 0.143 | 0.000 | +0.098 |
| few-shot-bm25-k10-answer-v1 | 0.000 | 0.750 | 0.562 | 0.114 | 0.000 | +0.056 |
| few-shot-bm25-k20-answer-v1 | 0.015 | 0.750 | 0.531 | 0.114 | 0.500 | +0.077 |
| zero-shot-answer-v2 | 0.242 | 0.625 | 0.781 | 0.086 | 0.500 | +0.266 |
| zero-shot-reason-v1 | 0.000 | 0.875 | 0.562 | 0.229 | 0.500 | -0.056 |
| few-shot-random-s0-k3-reason-v1 | 0.000 | 0.750 | 0.469 | 0.143 | 0.500 | -0.007 |
| few-shot-random-s0-k5-reason-v1 | 0.015 | 0.875 | 0.688 | 0.114 | 1.000 | +0.014 |
| few-shot-random-s0-k10-reason-v1 | 0.015 | 0.875 | 0.500 | 0.143 | 1.000 | -0.007 |
| few-shot-random-s0-k20-reason-v1 | 0.015 | 0.875 | 0.562 | 0.143 | 1.000 | -0.007 |
| few-shot-bm25-k3-reason-v1 | 0.015 | 0.875 | 0.719 | 0.200 | 0.500 | -0.007 |
| few-shot-bm25-k5-reason-v1 | 0.000 | 0.875 | 0.562 | 0.114 | 0.500 | +0.014 |
| few-shot-bm25-k10-reason-v1 | 0.000 | 0.750 | 0.531 | 0.086 | 0.500 | -0.007 |
| few-shot-bm25-k20-reason-v1 | 0.000 | 0.875 | 0.312 | 0.086 | 1.000 | +0.000 |
| zero-shot-reason-v2 | 0.242 | 0.625 | 0.719 | 0.057 | 1.000 | +0.210 |

各等级的样本数：gold 1: 66、gold 2: 8、gold 3: 32、gold 4: 35、gold 5: 2。平均偏差为正表示整体高估。gold 2 和 gold 5 的样本太少，这两列只能看个大概。

## 4. 预测的等级分布

| 运行 | 预测 1 | 预测 2 | 预测 3 | 预测 4 | 预测 5 |
| --- | --- | --- | --- | --- | --- |
| **标准答案** | 66 | 8 | 32 | 35 | 2 |
| zero-shot-answer-v1 | 70 | 4 | 13 | 53 | 3 |
| few-shot-random-s0-k3-answer-v1 | 69 | 4 | 10 | 50 | 10 |
| few-shot-random-s0-k5-answer-v1 | 70 | 3 | 11 | 51 | 8 |
| few-shot-random-s0-k10-answer-v1 | 69 | 4 | 15 | 51 | 4 |
| few-shot-random-s0-k20-answer-v1 | 70 | 4 | 15 | 51 | 3 |
| few-shot-bm25-k3-answer-v1 | 70 | 4 | 12 | 50 | 7 |
| few-shot-bm25-k5-answer-v1 | 69 | 5 | 17 | 48 | 4 |
| few-shot-bm25-k10-answer-v1 | 70 | 5 | 19 | 46 | 3 |
| few-shot-bm25-k20-answer-v1 | 69 | 5 | 19 | 47 | 3 |
| zero-shot-answer-v2 | 51 | 20 | 14 | 57 | 1 |
| zero-shot-reason-v1 | 73 | 5 | 25 | 38 | 2 |
| few-shot-random-s0-k3-reason-v1 | 71 | 5 | 24 | 41 | 2 |
| few-shot-random-s0-k5-reason-v1 | 71 | 5 | 19 | 48 | 0 |
| few-shot-random-s0-k10-reason-v1 | 71 | 3 | 26 | 43 | 0 |
| few-shot-random-s0-k20-reason-v1 | 70 | 6 | 23 | 44 | 0 |
| few-shot-bm25-k3-reason-v1 | 72 | 5 | 21 | 43 | 2 |
| few-shot-bm25-k5-reason-v1 | 71 | 4 | 22 | 45 | 1 |
| few-shot-bm25-k10-reason-v1 | 72 | 4 | 22 | 44 | 1 |
| few-shot-bm25-k20-reason-v1 | 70 | 3 | 28 | 42 | 0 |
| zero-shot-reason-v2 | 52 | 22 | 14 | 55 | 0 |

## 6. 示例的等级与待评估样本的标准等级一致的比例（离线诊断）

只用于解释结果，不参与选择。随机组的比例反映 train 的等级分布带来的“碰巧一致”。

| 运行 | 一致比例 | 示例等级分布 1/2/3/4/5 |
| --- | --- | --- |
| few-shot-random-s0-k3-answer-v1 | 0.333 | 0.48 / 0.06 / 0.22 / 0.22 / 0.01 |
| few-shot-random-s0-k5-answer-v1 | 0.326 | 0.47 / 0.06 / 0.22 / 0.23 / 0.02 |
| few-shot-random-s0-k10-answer-v1 | 0.329 | 0.47 / 0.07 / 0.21 / 0.24 / 0.02 |
| few-shot-random-s0-k20-answer-v1 | 0.328 | 0.45 / 0.06 / 0.22 / 0.25 / 0.01 |
| few-shot-bm25-k3-answer-v1 | 0.417 | 0.50 / 0.06 / 0.16 / 0.25 / 0.02 |
| few-shot-bm25-k5-answer-v1 | 0.410 | 0.50 / 0.05 / 0.18 / 0.25 / 0.02 |
| few-shot-bm25-k10-answer-v1 | 0.403 | 0.49 / 0.05 / 0.18 / 0.26 / 0.02 |
| few-shot-bm25-k20-answer-v1 | 0.386 | 0.48 / 0.05 / 0.21 / 0.25 / 0.01 |
| few-shot-random-s0-k3-reason-v1 | 0.333 | 0.48 / 0.06 / 0.22 / 0.22 / 0.01 |
| few-shot-random-s0-k5-reason-v1 | 0.326 | 0.47 / 0.06 / 0.22 / 0.23 / 0.02 |
| few-shot-random-s0-k10-reason-v1 | 0.329 | 0.47 / 0.07 / 0.21 / 0.24 / 0.02 |
| few-shot-random-s0-k20-reason-v1 | 0.328 | 0.45 / 0.06 / 0.22 / 0.25 / 0.01 |
| few-shot-bm25-k3-reason-v1 | 0.417 | 0.50 / 0.06 / 0.16 / 0.25 / 0.02 |
| few-shot-bm25-k5-reason-v1 | 0.410 | 0.50 / 0.05 / 0.18 / 0.25 / 0.02 |
| few-shot-bm25-k10-reason-v1 | 0.403 | 0.49 / 0.05 / 0.18 / 0.26 / 0.02 |
| few-shot-bm25-k20-reason-v1 | 0.386 | 0.48 / 0.05 / 0.21 / 0.25 / 0.01 |

## 7. token 用量（含重试）

| 运行 | 请求次数 | 输入 | 其中缓存未命中 | 输出 |
| --- | --- | --- | --- | --- |
| zero-shot-answer-v1 | 143 | 215,198 | 157,982 | 1,287 |
| few-shot-random-s0-k3-answer-v1 | 143 | 701,247 | 604,863 | 1,287 |
| few-shot-random-s0-k5-answer-v1 | 143 | 1,037,475 | 528,547 | 1,287 |
| few-shot-random-s0-k10-answer-v1 | 143 | 1,845,988 | 1,000,036 | 1,287 |
| few-shot-random-s0-k20-answer-v1 | 143 | 3,508,355 | 1,854,723 | 1,287 |
| few-shot-bm25-k3-answer-v1 | 143 | 762,395 | 626,587 | 1,287 |
| few-shot-bm25-k5-answer-v1 | 143 | 1,142,749 | 929,117 | 1,287 |
| few-shot-bm25-k10-answer-v1 | 143 | 2,033,269 | 1,858,549 | 1,287 |
| few-shot-bm25-k20-answer-v1 | 143 | 3,803,572 | 3,578,932 | 1,287 |
| zero-shot-answer-v2 | 143 | 268,108 | 153,676 | 1,287 |
| zero-shot-reason-v1 | 143 | 241,653 | 149,237 | 14,471 |
| few-shot-random-s0-k3-reason-v1 | 143 | 732,763 | 603,611 | 14,355 |
| few-shot-random-s0-k5-reason-v1 | 143 | 1,068,991 | 533,695 | 14,296 |
| few-shot-random-s0-k10-reason-v1 | 143 | 1,877,504 | 1,006,208 | 13,975 |
| few-shot-random-s0-k20-reason-v1 | 143 | 3,539,871 | 1,859,743 | 14,273 |
| few-shot-bm25-k3-reason-v1 | 143 | 793,911 | 623,671 | 14,518 |
| few-shot-bm25-k5-reason-v1 | 143 | 1,174,265 | 931,961 | 14,389 |
| few-shot-bm25-k10-reason-v1 | 145 | 2,108,137 | 1,860,585 | 14,779 |
| few-shot-bm25-k20-reason-v1 | 144 | 3,862,213 | 3,584,709 | 14,730 |
| zero-shot-reason-v2 | 143 | 319,302 | 151,238 | 15,636 |

## 8. 完整性检查

| 运行 | 143/143 | 同 prompts/single/task1/zero_shot_answer_v1.txt | 模型 | 参数同 zero-shot | prompt_preview | messages |
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
