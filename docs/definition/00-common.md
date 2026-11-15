# 补全官方标签定义：共用设计

创建日期：2026-11-10 · 状态：prompt 已建，zero-shot 运行中

这一轮的三份方案分别是 [01-task1.md](01-task1.md)、[02-task2a.md](02-task2a.md)、[03-task2b.md](03-task2b.md)。
本文是共用部分。命名、目录、`run_id` 规则沿用 [单任务共用设计](../single-task/00-common.md) §3。

## 1. 这一轮为什么存在

2026-11-10 核对官方任务页时发现：**官方给每个标签写的 Description（描述栏），从来没有进过任何一版 prompt。**

| 任务 | 官方给了什么 | prompt 里实际有什么 |
| --- | --- | --- |
| Task 1（risk_severity） | 5 个等级，每级 1–2 句完整描述 | 一版自行压缩的短描述，**丢了关键判据**（见 §2） |
| Task 2a（risk_domains） | 11 个 domain，每个一句描述 + 例子 | **只有 11 个标签名** |
| Task 2b（risk_drivers） | 7 个 driver，每个一句描述 + 例子 | **只有 7 个标签名** |

覆盖范围：多任务线 `prompts/zero_shot_v1/v2/v2a/v2b/v2c/v3/v4/v5.txt` 全部 8 版，
单任务线 `prompts/single/<task>/zero_shot_{answer,reason,facts}_v*.txt` 全部版本。
用官方描述的特征短语（`would itself produce`、`originate from a source`、
`exceeds the established task scope`、`execution characteristics or side effects`）在全部 8 个多任务版本里匹配，命中数都是 0。

也就是说，**到目前为止所有实验，模型都是在「只知道标签叫什么、不知道标签是什么意思」的条件下作答的。**

## 2. Task 1 的压缩丢了什么

`prompts/single/task1/zero_shot_facts_v1.txt:13-17` 与官方描述逐条对照：

| 判据维度 | 官方 3 级 | 官方 4 级 | prompt 3 级 | prompt 4 级 |
| --- | --- | --- | --- | --- |
| 可能性 | reasonably plausible | severe outcomes are plausible | — | — |
| 后果 | substantial | severe | substantial | severe |
| **目标敏感度** | **affect sensitive targets** | **highly sensitive targets or critical systems** | **（丢失）** | **sensitive targets** |
| **可逆性** | difficult to fully recover from | **difficult or impossible to reverse** | difficult recovery | **（丢失）** |
| 防护 | — | safeguards may be limited | — | weak safeguards |

两处系统性偏移：

1. **「涉及敏感目标」在官方是 3 级的判据**，4 级要求的是「**高度**敏感目标或**关键系统**」。
   压缩版把 3 级的这一条删掉，同时把 4 级的那一条降格成「sensitive targets」。
   结果：模型只要看到「涉及敏感目标」，按它手上的文字就只能判 4。
   这对应 train_evolve 上最大的一块误差——真实 3 判成 4，34 条
   （`results/_smoke/task1/zero-shot-reason-v1/20261104-082558/triage/summary.md` §2）。
2. **4 级的「difficult or impossible to reverse」整条被删**，3 级却保留了「difficult recovery」。
   模型手上没有任何「不可逆 → 升到 4」的判据。这对应 4 判成 3 的 21 条。

5 级同样丢了 `irreversible` 和 `safety-critical` 两个判据。

## 3. 这改变了哪些已有结论

| 已有结论 | 出处 | 现在怎么看 |
| --- | --- | --- |
| 「3/4 的线从定义里推不出来」（盲选命中率约 50%） | [agentic-distill/01-blind-probe.md](../agentic-distill/01-blind-probe.md) §10、§12 | 当时的推断是「分析器看到的是压缩版，56% 不是官方定义的上限」。**2026-11-10 已证伪**：补全官方定义后 3→4 混淆纹丝不动（train_evolve 52 → 53 条），原结论成立，这条线确实不在定义里 |
| facts-v2 的规则有效，改善集中在 3 级（+19.6 / +18.8 个百分点） | [agentic-distill/02-task1.md](../agentic-distill/02-task1.md) §8 | 当时怀疑「这 9 条规则是在用判例重新发明那句官方定义」。**2026-11-10 已证伪**：补上定义后 3 级反而略降（0.392 → 0.373），规则做的是定义做不到的事，有独立价值 |
| 2a/2b 蒸馏在 train_evolve 上涨、迁移不出去 | [03-task2a.md](../agentic-distill/03-task2a.md) §7、[04-task2b.md](../agentic-distill/04-task2b.md) §7 | 在标签无定义的前提下学出来的规则，泛化差是预期之中 |
| 2b 修复循环里 061、417 写 patch 的模型主动放弃 | [04-task2b.md](../agentic-distill/04-task2b.md) §7 | 每次写出的规则都是「不要加 Scope / Safeguard Failure」。**没有定义，规则只能从否定面写，必然误伤**；有定义才写得出「什么时候该加」 |

### 盲选命中率的基线（补定义之前）

从已有的诊断产物 `results/analysis/<task>/*-audit-v3d-full-r{1,2}/audit.jsonl` 直接统计
（分析器 Opus 5.5 在不知道答案的情况下，于真实标签与预测标签之间二选一；随机基线 50%）：

| 任务 | 错例数 | 盲选 = 标准答案（两次运行） |
| --- | --- | --- |
| Task 1 | 128 | 88 (68.8%) / 82 (64.1%) |
| Task 2a | 107 | 64 (59.8%) / 67 (62.6%) |
| Task 2b | 153 | 94 (61.4%) / 94 (61.4%) |

这是「按当时 prompt 里的那份文字，错例中有多大比例能判对」。补全定义后要重算同一个数，
差值就是定义缺失造成的损失。统计脚本待补进 `src/`（见 §8）。

## 4. 命名

把 prompt 看成两层：**基础层**（任务说明 + 标签定义 + 输出格式）与**规则层**（从错例蒸馏的判例）。
版本号表示基础层的第几版，蒸馏规则加在某个基础层之上。

**三条输出格式线（lineage）全做**，因为「哪条线配上定义最好」本身就是要回答的问题——
蒸馏不一定非在 `facts` 线上做。

### 权威版本对照表

号在每条线内独立递增（[单任务共用设计](../single-task/00-common.md) §3.1），所以**跨线号不齐**。
这不是错误，但引用时必须写全 `<task>-<lineage>-v<N>`。

| 线 | v1 | v2 | v3 | v4 |
| --- | --- | --- | --- | --- |
| `facts` | 基础层（定义压缩/缺失） | v1 + 蒸馏规则 | **基础层 + 官方定义** ← 本轮 | 留给「定义版 + 蒸馏」 |
| `answer` | 基础层 | v1 + 蒸馏规则 | **oracle 上限实验**（task2a/2b 专有） | **基础层 + 官方定义** ← 本轮 |
| `reason` | 基础层 | v1 + 蒸馏规则 | **oracle 上限实验**（task2a/2b 专有） | **基础层 + 官方定义** ← 本轮 |

**为什么 `facts` 用 v3 而 `answer` / `reason` 用 v4**：后两条线的 v3 已经被 oracle 上限实验占用
（输入里给定另一个任务的 gold label，见 `src/make_oracle_splits.py`），且已跑过正式运行，按 [AGENTS.md](../../AGENTS.md)
不能改名。task1 本来没有 `answer-v3` / `reason-v3`，为与 2a/2b 对齐，**空出 v3 不用**，统一用 v4。

所以本轮「v1 + 官方定义」这一组是：**`facts-v3`、`answer-v4`、`reason-v4`**，三个任务共 9 个 prompt。

### 蒸馏版的号留到选定之后再定

下一轮只在**选出来的那一条线**上蒸馏，不是三条都蒸。那条线的蒸馏版用它自己的下一个空号
（`facts` 线是 v4，`answer` / `reason` 线是 v5），定下来之后补进上表。
**蒸馏必须从该线定义版在 train_evolve 上的错例重新开始**，不要搬运 v2 的规则——
v2 的规则可以当种子参考，但要重新过回测。

## 5. 单变量保证

`facts-v3` 由脚本从 `facts-v1` 生成，**只替换标签定义段，其余逐字不动**。
生成脚本在 `src/make_definition_prompts.py`，它做两件事：

1. 断言被替换的那段在原文里恰好出现 1 次；
2. 把新文本换回旧文本，断言结果与原文逐字节相同。

两条断言任一失败就退出，不写文件。词数变化：

| 任务 | facts-v1 | facts-v3 |
| --- | --- | --- |
| task1 | 565 | 622 |
| task2a | 569 | 687 |
| task2b | 535 | 666 |

**只加 Description，不加 Examples。** 官方每个标签还给了例子，加上去大约再翻一倍。
放到下一个单变量去测，否则涨跌都分不清是哪一半在起作用。

## 6. 数据口径

沿用 [agentic-distill/00-common.md](../agentic-distill/00-common.md) §0.1：

| 数据 | 条数 | 本轮用途 |
| --- | --- | --- |
| train_evolve | 461 | 主要判断依据；同时为 v4 的蒸馏准备错例 |
| train_val | 107 | 本轮不跑（没有要选的东西） |
| dev | 143 | 与已有的 facts-v1 / facts-v2 对照 |

### 关于 dev 能不能跑

判断准则：**我会不会因为这个 dev 结果而改 prompt？会 → 是选择，污染 dev；不会 → 是测量，干净。**

- `facts-v3`：**不会**。无论 dev 涨跌都会保留官方定义——漏掉它本来就是失误，不是一个待调的参数。
  所以这一格是测量，可以直接跑。
- `facts-v4`（下一轮）：**会**。规则是从数据学出来的，必须守纪律：
  train_evolve 学 → train_val 记一次 → dev 最后一次，结果不好也不回头改规则。

仍然先跑 train_evolve，理由与纪律无关：v4 的蒸馏需要 v3 在 train_evolve 上的错例，顺手就有了。

## 7. 运行矩阵

3 任务 × 3 线 × 2 数据集 = **18 个 zero-shot 运行**，每格都有对应的 v1 作单变量对照。

| 批次 | 数据 | 运行 | 对照基线 | 状态 |
| --- | --- | --- | --- | --- |
| 1 | dev / train_evolve | `facts-v3` × 3 任务 | `facts-v1` | 已完成（§7.1） |
| 2 | dev / train_evolve | `answer-v4` × 3 任务 | `answer-v1` | 本批 |
| 3 | dev / train_evolve | `reason-v4` × 3 任务 | `reason-v1` | 本批 |

对照基线齐全，不需要补跑。`answer-v1` / `reason-v1` 在三个 split 上都有现成运行：

| 任务 | 线 | dev(143) | train_evolve(461) | train_val(107) |
| --- | --- | --- | --- | --- |
| task1 | answer | `20261104-081736` 0.266 | `20261104-082515` 0.330 | `20261104-083500` 0.364 |
| task1 | reason | `20261104-081746` 0.238 | `20261104-082558` 0.247 | `20261104-083523` 0.290 |
| task2a | answer | `20261104-085334` 0.837 | `20261104-090209` 0.823 | `20261104-091202` 0.799 |
| task2a | reason | `20261104-085349` 0.832 | `20261104-090302` 0.817 | `20261104-091230` 0.851 |
| task2b | answer | `20261104-092353` 0.711 | `20261104-093312` 0.671 | `20261104-094451` 0.612 |
| task2b | reason | `20261104-092410` 0.753 | `20261104-093411` 0.735 | `20261104-094517` 0.685 |

显著性一律用 `python src/paired_bootstrap.py <基准 run_dir> <对比 run_dir> --metric <mae|domain|driver>`。
143 条下指标差小于约 0.03 基本是噪声。

**本轮不跑**：few-shot、train_val、Examples 版、多任务线。
few-shot 另有一个前置障碍：`data/fewshot/` 里没有 train_evolve 的选例文件，
而且 train_evolve 的样本本身在 train 里，BM25 检索会检索到自己，必须先加排除自身的逻辑。

### 选型规则

这一轮要回答的是**「哪条线配上官方定义最好」**，选出来的那一条才是下一轮蒸馏的起点。
比较按任务分别做（三个任务可以选不同的线），判据依次是：

1. 该线的**定义版对自己 v1** 的改善方向，train_evolve 与 dev 是否一致；
2. 定义版之间的**绝对分数**（三条线横向比，用配对自助法，不看点估计）；
3. 分项结构是否健康（闸门不降、没有某个标签被压垮）。

**不以 dev 的点估计排名定胜负**——143 条下 0.03 以内都是噪声，横向比必须看置信区间。

## 7.1 `facts` 线结果（2026-11-10）

六个运行全部完成，143/143 与 461/461 合法预测，无格式失败。
显著性用 `src/paired_bootstrap.py`（10000 次重抽样）。**六格全部落在噪声区间内**，
但三个任务的方向和内部结构完全不同：

| 任务 | 数据 | facts-v1 | facts-v3 | 差值 | P(v3 更好) | run_id |
| --- | --- | --- | --- | --- | --- | --- |
| Task 1（MAE ↓） | dev | 0.238 | 0.245 | +0.007 | 0.37 | `20261110-040755` |
| Task 1（MAE ↓） | train_evolve | 0.299 | 0.321 | +0.022 | 0.10 | `20261110-041014` |
| Task 2a（Jaccard ↑） | dev | 0.824 | **0.854** | +0.030 | **0.96** | `20261110-040840` |
| Task 2a（Jaccard ↑） | train_evolve | 0.843 | 0.856 | +0.013 | 0.89 | `20261110-041236` |
| Task 2b（Jaccard ↑） | dev | 0.737 | 0.753 | +0.016 | 0.78 | `20261110-040926` |
| Task 2b（Jaccard ↑） | train_evolve | 0.754 | 0.755 | +0.001 | 0.52 | `20261110-041455` |

**三个任务的结论各不相同，预期几乎全错：**

| 任务 | 事前预期（各方案 §1） | 实际 |
| --- | --- | --- |
| Task 1 | 收益大：两个判据被删，正对最大的 3/4 混淆 | **轻微变差**。3→4 纹丝不动（52 → 53），变差来自闸门：1 级正确率 0.953 → 0.926 |
| Task 2a | 收益最小：confusable_pair 只有 13 条 | **三个里最好**，dev P=0.96。改善分散在多个标签，Legal 召回 0.077 → 0.308 最明显 |
| Task 2b | 收益最大：confusable_pair 占六成，定义恰好可分 | **机制完全如预期但总分不动**：Scope 召回 +35/+37 个百分点，被 Authorization 召回 −32/−34 抵消 |

三条可以带走的结论：

1. **定义能让模型「认得出一个标签」，但改不动「两个相邻档位之间的线」。**
   2a 的 Legal、2b 的 Scope 都是「模型原本根本认不出来」，补上定义立竿见影；
   Task 1 的 3/4 是同一个量上的切点，补再多文字也不动。这与
   [agentic-distill/01-blind-probe.md](../agentic-distill/01-blind-probe.md) 的盲测结论一致。
2. **总分不变不等于没有变化。** 2b 的结构变了一大截，只是得失相抵。
   只看 Mean Jaccard 会把这件事完全漏掉，分项必须看。
3. **更完整的定义有副作用。** Task 1 的官方描述每一级都用 `or` 串了多个条件，
   等于给了模型更多升级的理由，闸门（1 级）因此被弄坏。补定义不是无损操作。

## 7.2 三条线横向对照与选型（2026-11-10）

18 格全部跑完，每格 143/143 或 461/461 合法预测。下表是 zero-shot 的分数
（Task 1 是 MAE 越低越好，2a/2b 是 Mean Jaccard 越高越好），**粗体是该任务该数据集上最好的定义版**。

| 任务 | 数据 | answer-v1 → **v4** | reason-v1 → **v4** | facts-v1 → **v3** |
| --- | --- | --- | --- | --- |
| Task 1 | dev | 0.266 → 0.280 | 0.238 → **0.224** | 0.238 → 0.245 |
| Task 1 | train_evolve | 0.330 → 0.341 | 0.247 → **0.260** | 0.299 → 0.321 |
| Task 2a | dev | 0.837 → 0.840 | 0.832 → 0.803 | 0.824 → **0.854** |
| Task 2a | train_evolve | 0.823 → 0.844 | 0.817 → 0.819 | 0.843 → **0.856** |
| Task 2b | dev | 0.711 → 0.733 | 0.753 → 0.751 | 0.737 → **0.753** |
| Task 2b | train_evolve | 0.671 → 0.699 | 0.735 → **0.756** | 0.754 → 0.755 |

run_id 见各任务方案的 §6。

### 定义本身有没有用（纵向：定义版 vs 自己的 v1）

12 个新比较里**只有两格显著**，都在 `answer` 线上：

| 比较 | 差值 [95% CI] | 判定 |
| --- | --- | --- |
| task2a train_evolve：answer-v4 vs answer-v1 | −0.021 [−0.037, −0.006] | **显著更好** |
| task2b train_evolve：answer-v4 vs answer-v1 | −0.028 [−0.047, −0.008] | **显著更好** |
| task2b train_evolve：reason-v4 vs reason-v1 | −0.021 [−0.044, +0.004] | P=0.95，噪声 |
| task2b dev：answer-v4 vs answer-v1 | −0.022 [−0.056, +0.012] | P=0.90，噪声 |
| task2a dev：reason-v4 vs reason-v1 | +0.029 [−0.024, +0.084] | P=0.15，方向是变差 |
| Task 1 的全部 6 格 | — | 全噪声，4 格方向是变差 |

（2a/2b 的差值是 Jaccard 距离，负值表示更好。）

**`answer` 线受益最大，而且只有它显著。** 这很合理：`answer` 线不写推理，模型只能靠标签名猜，
定义的边际价值最大；`reason` / `facts` 线的推理过程本来就在部分补偿定义缺失。

**Task 1 上定义在三条线上都没用**，6 格全噪声，4 格方向是变差。与 §7.1 的结论一致。

### 哪条线最好（横向：三条定义版互比）

| 任务 | 数据 | 最好 | 对第二名 | 对第三名 |
| --- | --- | --- | --- | --- |
| Task 1 | dev | `reason-v4` | facts-v3 +0.021 [−0.042,+0.084] 噪声 | answer-v4 +0.056 [−0.007,+0.119] P=0.03 |
| Task 1 | train_evolve | `reason-v4` | facts-v3 **+0.061 [+0.020,+0.100] 显著** | answer-v4 **+0.080 [+0.041,+0.119] 显著** |
| Task 2a | dev | `facts-v3` | answer-v4 +0.014 噪声 | reason-v4 **+0.051 [+0.002,+0.104] 显著** |
| Task 2a | train_evolve | `facts-v3` | answer-v4 +0.013 噪声 | reason-v4 **+0.038 [+0.013,+0.063] 显著** |
| Task 2b | dev | `facts-v3` | reason-v4 +0.002 噪声 | answer-v4 +0.020 噪声 |
| Task 2b | train_evolve | `reason-v4` | facts-v3 +0.001 噪声 | answer-v4 **+0.056 [+0.029,+0.083] 显著** |

### 选型结论

| 任务 | 选定的线 | 依据 |
| --- | --- | --- |
| **Task 1** | **`reason`** | train_evolve 上显著优于另外两条；dev 方向一致。**但这是线的差异，不是定义的功劳**——定义在 Task 1 上三条线都是噪声 |
| **Task 2a** | **`facts`** | 两个数据集上都显著优于 `reason`；对 `answer` 是噪声但方向一致。唯一一个「定义版同时是最好的线」的任务 |
| **Task 2b** | **`reason`** | 与 `facts` 总分完全打平（dev +0.002、train_evolve −0.001，都是噪声），**按分项结构判**，见下 |

### Task 2b 为什么选 `reason` 而不是 `facts`

总分打平，但分项差别很大（train_evolve 召回率）：

| 标签 | n | reason-v1 → **v4** | facts-v1 → **v3** |
| --- | --- | --- | --- |
| Scope / Safeguard Failure | 82 | 0.244 → **0.524** | 0.183 → **0.537** |
| Authorization / Consent Failure | 111 | 0.964 → **0.847** | 0.919 → **0.604** |
| Untrusted / Conflicting Instructions | 161 | 0.739 → 0.752 | 0.919 → **0.925** |
| Scope 被判成 Authorization 的条数 | — | 52 → **30** | 63 → **26** |

**两条线都把 Scope 修好了**（召回 0.24→0.52、0.18→0.54），但代价不同：
`facts-v3` 的 Authorization 从 0.919 崩到 0.604，`reason-v4` 只从 0.964 掉到 0.847。
`reason-v4` 没有任何标签崩掉，是更健康的蒸馏起点。
（`facts` 线在 Untrusted 上明显更强，0.925 对 0.752，这是它的长处，但不足以抵消一个标签崩掉。）

### 一个需要记下来的发现

**`reason` 线在 Task 1 和 Task 2b 上都比 `facts` 线强，而且 Task 1 上是显著的。**

| Task 1 train_evolve | reason-v1 | facts-v1 |
| --- | --- | --- |
| 3 级正确率 | **0.520** | 0.392 |
| 真实 3 → 预测 4 | **34** | 52 |
| MAE | **0.247** | 0.299 |

也就是说，`facts` 格式本身在 Task 1 上就是一次退步——
[agentic-distill/02-task1.md](../agentic-distill/02-task1.md) §0 当时也记了「facts-v1 在 train_evolve 上显著更差」，
但为了便于诊断和蒸馏，那一轮仍决定整条线走 `facts`。
后来 `facts-v2` 蒸馏到 0.228，看起来是大幅改善，但它只是把 `facts` 格式自己造成的损失补了回来：
对 `reason-v1` 的 0.247 只有 −0.017，仍是噪声。

**这不否定蒸馏流程**（它确实在 `facts` 线内部带来了显著改善），
但说明**选哪条输出格式线，影响可能比蒸馏更大**，而这一维之前没有系统比较过。

## 8. 决策规则

每个任务的具体阈值写在各自方案的 §4。共用的部分：

| 结果 | 下一步 |
| --- | --- |
| v3 明显优于 v1（train_evolve 与 dev 方向一致） | 新开三份蒸馏方案，在 v3 上重新蒸馏得到 v4；v2 的规则作废，只当种子参考 |
| v3 与 v1 持平（都在噪声内） | 仍然保留 v3 作为基础层（官方材料本该在里面），但说明定义不是瓶颈；蒸馏改在 v3 上做，预期收益与 v2 相当 |
| v3 明显劣于 v1 | 先查是不是格式问题（更长的定义段挤占了注意力），再考虑只保留区分度最高的几条定义 |

### 本轮实际落点（2026-11-10）

三条线跑完后的最终落点（取代本节 2026-11-10 早先只看 `facts` 线时的版本）：

| 任务 | 蒸馏起点 | 下一轮蒸馏要盯住什么 |
| --- | --- | --- |
| **Task 1** | **`reason-v4`**（dev 0.224 / train_evolve 0.260） | 3/4 边界。注意 `reason-v2` 曾把 dev 从 0.238 弄坏到 0.336，这一轮必须用带回测的新流程。定义在这个任务上帮不上忙，闸门也要保护（`reason` 线闸门 0.972，比 `facts` 的 0.926 好得多） |
| **Task 2a** | **`facts-v3`**（dev 0.854 / train_evolve 0.856） | cardinality（占错例一半以上，定义帮不上）。注意 facts 线上以「少答」为主，[agentic-distill/03-task2a.md](../agentic-distill/03-task2a.md) §2 的「默认单标签」方向是反的 |
| **Task 2b** | **`reason-v4`**（dev 0.751 / train_evolve 0.756） | 把 Authorization 召回从 0.847 拉回 0.96 附近，且不把 Scope 推回去。两个标签现在都有定义，规则写得出「什么时候该加 X」 |

三个任务的 v2 规则一律作废，只当种子参考——它们都是在定义缺失的前提下学出来的。

**蒸馏版的号**（按 §4 的规则，各线下一个空号）：Task 1 → `reason-v5`，Task 2a → `facts-v4`，Task 2b → `reason-v5`。

**一个尚未解决的问题**：Task 1 和 2b 选了 `reason` 线，但 agentic-distill 的整套诊断工具
（`agentic.py audit` 的事实层机械审查）是为 `facts` 格式建的——`facts` 的 `quote` 必须是轨迹原文子串，
代码能直接验证，`reason` 的自由文本不行。在 `reason` 线上蒸馏，要么放弃机械审查（回到纯模型判断），
要么让分析器审查 `reason` 输出时自行提取引文。这一点要在下一轮方案里先定下来。

## 9. TODO

- `src/probe_stats.py`（或 `agentic.py probe-stats`）：把 §3 的盲选命中率做成可复算的命令，现在是一次性统计。
- 补定义后重算盲选命中率，与 §3 的基线对比。
- `facts-v2 + 官方定义` 的诊断格（zero-shot，三任务约 1M token）：回答「v2 的规则里有多少是在补定义缺口」。
  不作为候选系统，命名 `facts-v2-def` 并在 `config.json` 里标明。需要先把 `src/run.py:56` 的
  `SINGLE_VERSION_RE` 放宽为 `^(answer|reason|facts)-v\d+(-def)?$`。
- Examples 版（官方例子栏）作为下一个单变量。
- Task 1 的 prompt 第 18 行写着 `Assess severity within the relevant harm domain`，
  但 task1 的 prompt 里没有 harm domain 列表，也没有定义。等于让模型在一个看不见的框架里评估严重性。
