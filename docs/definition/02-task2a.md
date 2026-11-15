# Task 2a（危害领域）：补上官方 domain 描述

创建日期：2026-11-10 · 状态：prompt 已建，zero-shot 运行中 · 共用设计见 [00-common.md](00-common.md)

指标是 Mean Jaccard（交并比均值），越高越好，由 `python src/evaluate.py <run_dir>` 复算。

## 1. 这个任务为什么要改

和 Task 1 不同，2a 的 prompt 里**一句定义都没有**：`zero_shot_facts_v1.txt:12-26` 只列了 11 个标签名，
后面跟两句通用指引（「选直接受影响的领域」「No Material Harm 必须单独出现」）。
模型要靠标签名本身去猜 `Operational / Service` 和 `Security / System Integrity` 的分界。

这一轮的诊断把 107 条错例分成两类
（[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §7，Opus 5.5 独立跑两次）：

| | cardinality | confusable_pair | reading | missed_harm | gold_questionable | unexplained |
| --- | --- | --- | --- | --- | --- | --- |
| 第 1 次 | 36 | 13 | 36 | 5 | 14 | 3 |
| 第 2 次 | 43 | 13 | 26 | 13 | 10 | 2 |

**补定义主要冲着 `confusable_pair`（易混标签选错）去，它只有 13 条。**
2a 最大的一块是 `cardinality`（标签个数不对，两次都判为选法类的有 43 条），补定义**修不了它**——
那是「该选一个还是两个」的问题，不是「这个标签什么意思」的问题。

所以对 2a 的预期要放低：**定义能修的那部分不大。** 本轮仍然做，理由有三条：

1. 它是官方材料，漏掉是失误，补回来不需要理由；
2. 三个任务同一个改动，结果可以互相印证（如果定义缺失是普遍原因，三者应同向改善）；
3. 它是 v4 蒸馏的新起点——在标签有定义的前提下蒸馏，规则写得出「什么时候该加 X」而不只是「不要加 X」。

### 已知的最大一块：标签个数

误差拆解（train_evolve，reason-v1，[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §1.1）：

| 真实 → 预测 | 条数 | 平均 Jaccard | 占总损失 |
| --- | --- | --- | --- |
| 1 → 1 | 314 | 0.92 | 28% |
| **1 → 2** | 56 | 0.46 | **36%** |
| 2 → 1 | 27 | 0.39 | 20% |
| 2 → 2 | 64 | 0.78 | 17% |

注意方向在 facts 线上翻过来了：facts-v1 的 61 条 cardinality 错例里，**以「两个标签只答了一个」为主（41 条）**
（同文档 §7）。reason 线是多答，facts 线是少答。
这意味着 [agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §2 草拟的那句
「Give one harm domain by default」加到 facts 线上方向是反的。**这一条留给下一轮，本轮不碰**，
但 v3 的结果要顺带记录 cardinality 的方向有没有变。

## 2. 改了什么

`prompts/single/task2a/zero_shot_facts_v3.txt` = `zero_shot_facts_v1.txt`，在 11 个标签名各自后面补上官方
Description，其余逐字不动。569 → 687 词。**不加 Examples**（见 [00-common.md](00-common.md) §5）。

原有的两句通用指引（「Add a second label only for an additional direct harm」「No Material Harm must be
used alone」）保留不动——它们不是官方文字，但删掉就不是单变量了。

## 3. 运行矩阵

| 步 | 数据 | 运行 | run_id |
| --- | --- | --- | --- |
| 1 | dev（143） | `facts-v3` zero-shot | 待回填 |
| 2 | train_evolve（461） | `facts-v3` zero-shot | 待回填 |

```bash
.venv/bin/python src/run.py --task task2a --version facts-v3 --strategy zero-shot --split dev --concurrency 8
```

## 4. 对照基线与决策规则

已有的 zero-shot 结果（[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §7）：

| 数据 | answer-v1 | reason-v1 | facts-v1 | facts-v2 | reason-v2 | answer-v2 |
| --- | --- | --- | --- | --- | --- | --- |
| dev | 0.837 | 0.832 | 0.824 | 0.840（`20261109-205141`） | 0.866 | 0.862 |
| train_evolve | — | 0.817 | 0.843（`20261109-164727`） | 0.871（`20261109-204423`） | — | — |

主要比较是 **facts-v3 对 facts-v1**。

| 结果 | 读法与下一步 |
| --- | --- |
| v3 显著优于 v1 | 出乎预期（confusable_pair 只有 13 条），要去查提升来自哪些标签，别急着归因于定义 |
| v3 略优于 v1 但在噪声内 | 与诊断一致。仍保留 v3 作基础层，蒸馏改在 v3 上做 |
| v3 劣于 v1 | 查是不是更长的定义段挤占了注意力，或 cardinality 方向被推得更偏 |

**要专门看的分项**：

1. 按标签的召回率和精确率，尤其是诊断里点名的易混对（Security ↔ Operational、Privacy ↔ Security）；
2. **标签个数的方向**：1→2 和 2→1 各多少条，和 facts-v1 比有没有变；
3. `No Material Harm` 的召回率不得下降（它和 Task 1 的 1 级是同一批 262 条样本）。

**回测标准的已知问题**：facts-v1 原样重跑一次（temperature 0），Operational 精确率就能掉 9.5 个百分点
（[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §7 的噪声基线）。
按标签看分项时必须记住这个波动幅度，不要把噪声当结论。
估噪声基线这件事列在 [agentic-distill/05-status.md](../agentic-distill/05-status.md) §3 的未决事项里，仍未做。

## 5. 结果（2026-11-10）

**结论：三个任务里 2a 的总分改善最大，接近显著——而 §1 预期它收益最小。**

| 数据 | facts-v1 | facts-v2 | **facts-v3** | v3 − v1（Jaccard） | P(v3 更好) |
| --- | --- | --- | --- | --- | --- |
| dev（143） | 0.824 | 0.840 | **0.854** | +0.030 [-0.002, +0.066] | **0.96**，噪声（CI 差一点点不含 0） |
| train_evolve（461） | 0.843 | **0.871** | 0.856 | +0.013 [-0.008, +0.033] | 0.89，噪声 |

run_id：dev `20261110-040840`、train_evolve `20261110-041236`，143/143 与 461/461 全部合法。
配对自助法报的是 Jaccard 距离（1 − Jaccard），上表已换算成 Jaccard 差，正值表示 v3 更好。

### 改善是分散的，不是某一对标签

按标签的召回率和精确率（train_evolve，v1 → v3）：

| 标签 | n | 召回 | 精确 |
| --- | --- | --- | --- |
| **Legal / Compliance** | 13 | 0.077 → **0.308** | 0.167 → **0.571** |
| **Security / System Integrity** | 49 | 0.429 → **0.510** | 0.875 → 0.806 |
| Financial / Assets | 41 | 0.634 → 0.610 | 0.667 → **0.781** |
| Physical / Health | 39 | 0.795 → 0.744 | 0.886 → 0.935 |
| Operational / Service | 37 | 0.595 → 0.541 | 1.000 → 0.952 |
| Privacy / Confidentiality | 149 | 0.953 → 0.953 | 0.922 → 0.940 |
| No Material Harm（闸门） | 213 | 0.972 → **0.991** | 0.900 → 0.898 |

dev 上 Security 的召回 0.562 → **0.812**（n=16）是最大的一格。

**没有哪一对标签独占改善**，是多个标签各涨一点——这正是「模型原本不知道标签是什么意思」该有的样子。
`Legal / Compliance` 从几乎认不出（召回 0.077）到能认出三成，是最直接的证据：这个标签光看名字确实猜不准。
闸门（`No Material Harm`）召回不降反升，没有 Task 1 的副作用。

### 标签个数也小幅改善

| 真实 → 预测 | v1（train_evolve） | v3 | v1（dev） | v3 |
| --- | --- | --- | --- | --- |
| 1 → 1 | 349 | 353 | 107 | 110 |
| 1 → 2（多答） | 21 | **17** | 7 | **4** |
| 2 → 1（少答） | 49 | **45** | 14 | **12** |
| 2 → 2 | 42 | 46 | 15 | 17 |

两个方向同时收窄，说明不是整体偏移，而是真的判准了一些。
但 cardinality 仍是最大的一块（train_evolve 上 17 + 45 = 62 条），**补定义没解决它**，符合 §1 的预期。

### 下一步

1. **v3 作为 2a 的新基础层**，在它上面重新蒸馏得到 v4。
2. v4 的蒸馏要盯住 cardinality：它现在是 2a 最大的一块，而且定义帮不上。
   注意方向——facts 线上以「少答」为主（45 条 vs 多答 17 条），
   [agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §2 草拟的「默认单标签」那句话方向是反的，不要用。
3. 可以考虑把 cardinality 改成「每个标签独立判 + 置信度阈值」，阈值在 train_evolve 上标定。

## 6. 三条线对照与选型（2026-11-10）

补跑 `answer-v4` 和 `reason-v4` 之后，**2a 是唯一一个「定义版同时也是最好的线」的任务**，选 `facts`。

| 线 | dev v1 → 定义版 | train_evolve v1 → 定义版 | run_id（定义版 dev / train_evolve） |
| --- | --- | --- | --- |
| `answer` | 0.837 → 0.840 | 0.823 → **0.844（显著变好）** | `20261110-060957` / `20261110-061307` |
| `reason` | 0.832 → 0.803 | 0.817 → 0.819 | `20261110-061106` / `20261110-061637` |
| **`facts`** | 0.824 → **0.854** | 0.843 → **0.856** | `20261110-040840` / `20261110-041236` |

**纵向**：`answer-v4` 对 `answer-v1` 在 train_evolve 上 −0.021 [−0.037, −0.006]，**本轮仅有的两个显著格之一**。
`answer` 线不写推理，只能靠标签名猜，定义的边际价值最大。
`facts-v3` 对 `facts-v1` 是 P=0.96 / 0.89 的噪声，`reason` 两格都是噪声且 dev 方向变差。

**横向**：`facts-v3` 在两个数据集上都显著优于 `reason-v4`（dev +0.051 [+0.002,+0.104]、
train_evolve +0.038 [+0.013,+0.063]）；对 `answer-v4` 是噪声（+0.014 / +0.013），但两边方向一致。

### 决定

**蒸馏起点 `facts-v3`**（蒸馏版命名 `facts-v4`）。`answer-v4` 是并列第二且差异在噪声内，
但 `facts` 格式的 `quote` 可机械审查，蒸馏工具链现成，所以选 `facts`。

下一轮盯 cardinality（§5 已说明：占错例一半以上，定义帮不上，且 facts 线上以「少答」为主，
[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §2 草拟的「默认单标签」方向是反的）。
