# Task 2b（风险成因）：补上官方 driver 描述

创建日期：2026-11-10 · 状态：prompt 已建，zero-shot 运行中 · 共用设计见 [00-common.md](00-common.md)

指标是 Mean Jaccard（交并比均值），越高越好，由 `python src/evaluate.py <run_dir>` 复算。

## 1. 这个任务为什么最适合补定义

2b 的 prompt 里也是一句定义都没有：`zero_shot_facts_v1.txt:12-21` 只有 7 个标签名加一句通用指引。
但 2b 和 2a 不同——**它的错误形态正好是补定义能修的那一种。**

诊断把 153 条错例分成（[agentic-distill/04-task2b.md](../agentic-distill/04-task2b.md) §7）：

| | confusable_pair | cardinality | reading | missed_harm | target_confusion | gold_questionable | unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 第 1 次 | **88** | 15 | 25 | 6 | 2 | 12 | 4 |
| 第 2 次 | **85** | 17 | 17 | 16 | 2 | 11 | 4 |

**`confusable_pair` 占六成**，而 2a 只有 13 条。两次都判为选法类的有 90 条。

配对统计（train_evolve，reason-v1，同文档 §1.1）：

| 真实标签 | 被换成 | 次数 |
| --- | --- | --- |
| **Scope / Safeguard Failure** | **Authorization / Consent Failure** | **50** |
| Untrusted / Conflicting Instructions | Execution / Action Hazard | 15 |
| Untrusted / Conflicting Instructions | Authorization / Consent Failure | 15 |
| Scope / Safeguard Failure | Execution / Action Hazard | 14 |

### 官方定义恰好能分开这两个

| | 官方 Description 的要害 | 官方例子 |
| --- | --- | --- |
| Authorization / Consent Failure | 权限、所有权、许可、同意、委托访问**本身缺失或未确立** | Accessing another person's records |
| Scope / Safeguard Failure | **超出已确立的任务范围**，或绕过一个**必需的**确认 / 审查 / 批准 / 校验关卡 | **Sending an email when only a draft was requested** |

分界是：**用户授权的那件事本身存不存在。** 存在但做超了、或跳过了该走的关卡 → Scope；
那份授权根本不存在 → Authorization。

模型只看到两个标签名时，「没经过用户确认就发出去了」这个事实在两个名字下都讲得通，
而「没有确认 = missing consent」在字面上更贴近 Authorization。官方那个例子
（只要求起草却发了邮件）字面上就是这 50 条的原型。

### Execution 的排他条件

官方 `Execution / Action Hazard` 的描述里有一句排他条件，是整张表里最关键的一句：

> ...**even when the requested outcome, authorization, and available information do not themselves create the risk.**

即：**只有当其他成因都不成立时，风险才归到执行方式头上。** 模型看不到这句话，
就会在已有 Untrusted 或 Scope 问题时再顺手加一个 Execution——对应上表的 15 条和 14 条。
这也可能解释 Execution 这个标签为什么极不稳定：整体回测里它召回 −16.7、精确率 −32.9，
而 facts-v1 自己重跑也是同样幅度（同文档 §7 第 3 点）。**一个没有定义的标签，模型只能靠猜。**

### 没有定义时，规则只能从否定面写

修复循环里 AGENTRISK-061 和 417 两条，写 patch 的模型**主动放弃**，理由是每次写出来的规则都是
「不要加 Scope / Safeguard Failure」，都会弄坏同一批 gold 含该标签的样本（同文档 §7）。
这是没有定义的必然后果：模型不知道什么时候**该**加 X，就只能写「不要加 X」。

## 2. 改了什么

`prompts/single/task2b/zero_shot_facts_v3.txt` = `zero_shot_facts_v1.txt`，在 7 个标签名各自后面补上官方
Description，其余逐字不动。535 → 666 词。**不加 Examples**（见 [00-common.md](00-common.md) §5）。

事实要点那一段（第 2 条「授权范围是什么」与第 3 条「是否超出范围或绕过保护措施」分开列）保留不动。
它和补上的定义指向同一个区分，v3 的结果可以看出两者是叠加还是冗余。

## 3. 运行矩阵

| 步 | 数据 | 运行 | run_id |
| --- | --- | --- | --- |
| 1 | dev（143） | `facts-v3` zero-shot | 待回填 |
| 2 | train_evolve（461） | `facts-v3` zero-shot | 待回填 |

```bash
.venv/bin/python src/run.py --task task2b --version facts-v3 --strategy zero-shot --split dev --concurrency 8
```

## 4. 对照基线与决策规则

已有的 zero-shot 结果（[agentic-distill/04-task2b.md](../agentic-distill/04-task2b.md) §7）：

| 数据 | answer-v1 | reason-v1 | facts-v1 | facts-v2 | reason-v2 | answer-v2 |
| --- | --- | --- | --- | --- | --- | --- |
| dev | 0.711 | 0.753 | 0.737 | 0.741（`20261109-204041`） | 0.703 | 0.716 |
| train_evolve | — | 0.735 | 0.754（`20261109-164923`） | 0.793（`20261109-202959`） | — | — |

**三个任务里，2b 是预期收益最大的一个**（confusable_pair 六成，且官方定义恰好可分）。
如果补定义在哪里有效，最应该在这里看到。

| 结果 | 读法与下一步 |
| --- | --- |
| v3 显著优于 v1，且 Scope 召回上升、Authorization 过度使用下降 | 诊断链条完整闭合。在 v3 上重新蒸馏得到 v4，剩下的 reading 类才是规则该管的 |
| v3 优于 v1 但不显著 | 看分项方向是否一致；一致就接受 v3 作基础层 |
| v3 ≈ v1 | 说明模型本来就「知道」定义（从标签名推出来了），confusable_pair 的根因另在别处，要回去看诊断样本 |

**要专门看的分项**：

1. **Scope / Safeguard Failure 的召回率**（train_evolve 上它被漏了 62 次）；
2. **Authorization / Consent Failure 的精确率**（被多给了 75 次）；
3. **Execution / Action Hazard 的召回与精确率**——排他条件是否起作用。
   注意这个标签的重跑波动极大（±17 到 ±33 个百分点），只看方向，不要看绝对值；
4. `No Material Risk` 的召回率不得下降。

**数据先验提醒**：train 里有害样本的 driver **75% 是两个标签**（227/303），和 2a 正好相反。
现有 prompt 里「只在必要时加第二个」那句话对 2b 是反先验的。本轮不动它，记在这里供下一轮参考。

**排除的样本**：AGENTRISK-401 在诊断阶段两次触发模型的网络安全防护，没有进入诊断，按规定不重试、不绕过。

## 5. 结果（2026-11-10）

**结论：§1 预测的机制完全发生了，幅度很大——但总分几乎没动，因为收益被另一侧的下跌抵消。**

| 数据 | facts-v1 | facts-v2 | **facts-v3** | v3 − v1（Jaccard） | P(v3 更好) |
| --- | --- | --- | --- | --- | --- |
| dev（143） | 0.737 | 0.741 | **0.753** | +0.016 [-0.022, +0.056] | 0.78，噪声 |
| train_evolve（461） | 0.754 | **0.793** | 0.755 | +0.001 [-0.027, +0.029] | 0.52，噪声 |

run_id：dev `20261110-040926`、train_evolve `20261110-041455`，143/143 与 461/461 全部合法。

### Scope / Authorization：机制完全如预期

按标签的召回率和精确率（v1 → v3）：

| 标签 | n（train_evolve） | 召回（train_evolve） | 召回（dev） | 精确（train_evolve） |
| --- | --- | --- | --- | --- |
| **Scope / Safeguard Failure** | 82 | 0.183 → **0.537** | 0.185 → **0.556** | 0.455 → 0.489 |
| **Authorization / Consent Failure** | 111 | 0.919 → **0.604** | 0.938 → **0.594** | 0.560 → **0.638** |
| Insufficient Grounding / Uncertainty | 52 | 0.442 → 0.538 | 0.438 → 0.500 | 0.676 → 0.757 |
| Untrusted / Conflicting Instructions | 161 | 0.919 → 0.925 | 0.898 → 0.918 | 0.955 → 0.961 |
| Execution / Action Hazard | 18 | 0.389 → 0.278 | 0.143 → 0.429 | 0.636 → 0.357 |
| Risky Requested Outcome | 11 | 0.545 → 0.636 | 0.667 → 0.667 | 0.231 → 0.146 |
| No Material Risk（闸门） | 213 | 0.977 → 0.981 | 1.000 → 1.000 | 0.893 → 0.905 |

**Scope 的召回率在两个数据集上分别涨了 35.4 和 37.1 个百分点**，同时 Authorization 的精确率从 0.560 升到 0.638。
官方定义确实把这两个标签分开了，§1 的诊断链条是对的。

### 为什么总分不动

这是一次**此消彼长**：模型从「什么都标 Authorization」换成了「该标 Scope 的标 Scope」，
但同时把一批真该标 Authorization 的样本也不标了（召回 0.919 → 0.604）。
Jaccard 两边各得各失，净值归零。

也就是说，**v1 和 v3 不是「差」与「好」的关系，是两个不同的偏差点**：

- v1：Authorization 过度扩张，Scope 几乎认不出来（召回 0.183）；
- v3：两个标签都认得出，但平衡点偏到了另一侧。

v3 的失衡比 v1 的轻得多（v1 的 Scope 召回只有 0.183，等于这个标签根本不存在），
所以 v3 是更好的起点，哪怕总分一样。

其余标签：`Execution / Action Hazard` 在 train_evolve 上变差、dev 上变好，n 只有 18 和 7，
且这个标签的重跑波动本来就有 ±17 到 ±33 个百分点
（[agentic-distill/04-task2b.md](../agentic-distill/04-task2b.md) §7），不作结论。
`Risky Requested Outcome` 精确率 0.231 → 0.146，被过度使用，n=11，留待下一轮看。

标签个数基本不变（train_evolve 1→2 从 30 到 35，2→1 从 4 到 3），符合 §1——2b 的问题本来就不是个数。

### 下一步

1. **v3 作为 2b 的新基础层**，在它上面重新蒸馏得到 v4。
2. **v4 的蒸馏目标非常明确**：把 Authorization 的召回从 0.604 拉回来，同时不要把 Scope 推回去。
   这正是规则该干的事——现在两个标签都有定义，规则写得出「在什么情况下该加 Authorization」，
   而不再是 v2 时代那种只能写「不要加 Scope」、必然误伤的局面
   （[agentic-distill/04-task2b.md](../agentic-distill/04-task2b.md) §7 里 061、417 两条模型主动放弃的原因）。
3. v2 的 9 条规则作废，只当种子参考：它们是在 Scope 召回 0.183 的世界里学出来的，前提已经不存在。

## 6. 三条线对照与选型（2026-11-10）

补跑 `answer-v4` 和 `reason-v4` 之后，**2b 改选 `reason` 线**——总分和 `facts` 打平，但分项结构健康得多。

| 线 | dev v1 → 定义版 | train_evolve v1 → 定义版 | run_id（定义版 dev / train_evolve） |
| --- | --- | --- | --- |
| `answer` | 0.711 → 0.733 | 0.671 → **0.699（显著变好）** | `20261110-061017` / `20261110-061406` |
| **`reason`** | 0.753 → 0.751 | 0.735 → **0.756** | `20261110-061138` / `20261110-061815` |
| `facts` | 0.737 → **0.753** | 0.754 → 0.755 | `20261110-040926` / `20261110-041455` |

**纵向**：`answer-v4` 对 `answer-v1` 在 train_evolve 上 −0.028 [−0.047, −0.008]，**显著**；
`reason-v4` 对 `reason-v1` 是 −0.021 [−0.044, +0.004]，P=0.95，差一点。

**横向**：`reason-v4` 与 `facts-v3` 完全打平（dev +0.002、train_evolve −0.001，都是噪声）。
`answer-v4` 在 train_evolve 上显著垫底（+0.056 [+0.029, +0.083]）。

### 打平时按分项结构判

train_evolve 召回率：

| 标签 | n | reason-v1 → **v4** | facts-v1 → **v3** |
| --- | --- | --- | --- |
| Scope / Safeguard Failure | 82 | 0.244 → **0.524** | 0.183 → **0.537** |
| **Authorization / Consent Failure** | 111 | 0.964 → **0.847** | 0.919 → **0.604** |
| Untrusted / Conflicting Instructions | 161 | 0.739 → 0.752 | 0.919 → **0.925** |
| Insufficient Grounding / Uncertainty | 52 | 0.519 → 0.538 | 0.442 → 0.538 |
| Scope 被判成 Authorization | — | 52 → **30** | 63 → **26** |

**两条线都把 Scope 修好了**（§5 发现的机制在 `reason` 线上同样成立，而且幅度相当），
但代价差很多：`facts-v3` 的 Authorization 从 0.919 崩到 0.604，`reason-v4` 只从 0.964 掉到 0.847。
`reason-v4` 没有任何标签崩掉。

`facts` 线在 Untrusted 上明显更强（0.925 对 0.752），这是它的长处，但一个标签掉 32 个百分点更难修。

### 决定

**蒸馏起点 `reason-v4`**（蒸馏版命名 `reason-v5`）。目标明确：
把 Authorization 召回从 0.847 拉回 0.96 附近，同时不把 Scope 推回去。
两个标签现在都有官方定义，规则写得出「什么时候**该**加 Authorization」，
不再是 §1 里 061、417 那种只能写「不要加 Scope」、必然误伤的局面。

同 Task 1：`reason` 线上蒸馏要先解决 `agentic.py audit` 的事实层机械审查问题
（它依赖 `facts` 的 `quote` 是原文子串）。
