# Task 2b（风险成因）：易混标签对、`facts` 输出格式、智能体式蒸馏

创建日期：2026-11-07 · 状态：方案，未实施 · 共用设计见 [00-common.md](00-common.md)

前置条件：[02-task1.md](02-task1.md) 的 E1、E2 已跑通。本文只写和 Task 1、Task 2a 不同的地方。


## 0. 2026-11-07 修订（盲测探针之后，用户已同意）

| 编号 | 修订 |
| --- | --- |
| B1 | 同 [03-task2a.md](03-task2a.md) §0 的 A1–A8：基于 v3c、遮盖标签名是前提、E1 不降级、`factor` 作为子键、先过分析器校准关卡 |
| B2 | E0 人工阅读 15 条 Scope→Authorization 错例时，同时记录每条的 `factor`（例如「超出了用户要求的范围」和「从未获得同意」），写成 `driver:Authorization\|Scope / factor=…` |
| B3 | 回测集同 [02-task1.md](02-task1.md) §0 的 T3、T4：先把「同一 factor、真实标签不同」的样本对分成「能说出区别」和「噪声」两类，只有前一类进回测集 |

## 0.1 本轮执行清单（2026-11-07 第二次定稿，按 Task 1 实际执行的口径，优先于 §0 和 §2–§5）

口径与 [02-task1.md](02-task1.md) §0.1、§8 完全一致：facts 格式线，蒸馏前后各跑 **zero-shot** 和 **BM25 k=10**，都在 dev 上；
蒸馏在 train_evolve 上学，train_val 记录一次，无论结果如何都上 dev。指标是 Mean Jaccard（越高越好）。
**不跑**：random 选例、BM25 k=3/5/20、对比示例、分步 prompt、成功分析师、E0（只修 Scope / Authorization）。

### 运行矩阵

| 步 | 数据 | 运行 |
| --- | --- | --- |
| 1 | train_evolve、train_val | facts-v1 zero-shot（train_evolve 是蒸馏的错例来源） |
| 2 | dev | **蒸馏前**：facts-v1 zero-shot、facts-v1 + BM25 k=10 |
| 3 | train_evolve | 蒸馏（下文）→ facts-v2 zero-shot 整体回测 |
| 4 | train_val | facts-v2 zero-shot，记录一次 |
| 5 | dev | **蒸馏后**：facts-v2 zero-shot、facts-v2 + BM25 k=10 |

dev 上共 4 个运行，与已有的 answer-v1 / reason-v1 / answer-v2 / reason-v2 在 dev 上的 zero-shot 和 k=10 结果并列比较（缺的格子按 Task 1 的做法补跑）。

### 第 3 步：蒸馏（与 Task 1 相同的流程）

1. **诊断**：facts-v1 在 train_evolve 上的全部错例（Jaccard < 1），v3d 分析器（Opus 5.5，文件交接）独立跑两次。两次在「读错类 / 选法类」上的一致率 ≥ 70% 才继续（G2）。
2. **筛选**：两次都判为读错类（`reading`、`missed_harm`、`target_confusion`）的样本进入修复循环；选法类（`cardinality`、`confusable_pair`）不写规则，交给 few-shot。
3. **修复循环**：Claude 写 patch（文件交接），deepseek 回测，最多 3 次，从第 3 次起附上被弄坏样本的摘要（Task 1 第 3 步实施时加的）。
   回测集：目标错例 + 至多 5 条同类错例 + 10 条判对的邻近样本（含 patch 涉及标签与不含的各一半）。
4. **合并**：通过的 patch 按原文逐条收录（Task 1 的做法）；涉及 `No Material Risk` 的闸门组默认不收。
5. **组装**：`zero_shot_facts_v2.txt` 与 `few_shot_facts_v2.json`。
6. **整体回测**：完整 train_evolve，`src/regress.py compare`：样本数 ≥ 10 的标签，召回率和精确率下降都不超过 5 个百分点；`No Material Risk` 召回率不下降。

### 运行前必须补的代码与 prompt（Task 1 的实现只覆盖了等级任务）

**状态：C1–C7 于 2026-11-07 完成，C8 于 2026-11-09 完成。**单元测试 43 个全部通过。用 reason-v1 的旧错例试导出阶段 A 的输入，确认两个候选标签集合齐全，模型输出里没有残留任何标签名。
已知的局限：遮盖只能挡住标签全名。像「指令来自不可信的 README」这样的描述，在语义上仍然指向 Untrusted 这个成因，这类泄露无法靠遮盖消除。

| 编号 | 内容 | 原因 |
| --- | --- | --- |
| C1 | `prompts/single/task2b/zero_shot_facts_v1.txt`：定义部分与 `zero_shot_reason_v1.txt` 逐字相同，输出部分换成 facts 格式；事实要点见下 | 还没有 |
| C2 | `prompts/single/task2b/few_shot_facts_v1.json`（与 Task 1 同格式，结尾提醒按 facts 格式输出） | 还没有 |
| C3 | `prompts/single/task2b/analyst_v3d_audit.txt`、`analyst_v3d_classify.txt`：沿用 Task 1 v3d 的全部规则（写到就算知道、错误说法与没写到的事实都标会不会改变答案、先盲审后归类）；强制选择改为在**两个候选标签集合**之间二选一（真实集合与预测集合，按字母序给出，不说哪个是答案）或 `cannot_tell`；判断层类别见下 | Task 1 的 prompt 只讲等级 |
| C4 | 代码 D13：阶段 A 输入里，把模型 FACTS / JUDGMENT 中出现的标签名替换成 `[LABEL]` | 否则推理文本直接泄露预测 |
| C5 | 代码：`stage_a_payload` 给 Task 2 加两个候选集合；`blind_view` 支持集合；K3/K4/K8 的 Task 2 版本（选法类要求盲选等于预测集合或 `cannot_tell`；`gold_questionable` 要求盲选不等于真实集合） | 现在这几处只对 Task 1 生效 |
| C6 | 代码：`REPAIR_FROM` 加入 `missed_harm` | 现在只收 `reading`、`target_confusion` |
| C7 | 单元测试覆盖 C4–C6 | — |
| C8 | 写 patch 的 prompt 按任务分文件：`prompts/single/{task}/analyst_patch_v1.txt`，代码按任务名读取（`repair-export --patch-prompt` 的默认值是带 `{task}` 的模板）。Task 2 的版本只写本任务的类别（reading / missed_harm / target_confusion）和本任务的例子；Task 1 的版本是原共用文件的逐字拷贝，原文件保留不动 | 原来三个任务共用一份，里面只有 Task 1 的类别和「risk_severity 3 vs 4」这类例子（2026-11-09 补） |

**事实要点**（写进 C1）：
1. 这个动作是谁要求的：用户明确要求、数据里嵌入的指令，还是 agent 自己的推断；
2. 有没有得到授权或确认，用户的授权范围是什么；
3. 动作是否**超出**了用户要求的范围，或绕过了某个保护措施（与第 2 条分开写）；
4. 动作依据的信息是否经过核实；
5. 危险来自动作本身，还是来自用户要求的结果本身。

**判断层类别**（写进 C3）：

| 值 | 含义 | 去向 |
| --- | --- | --- |
| `reading` | 读错了会改变标签的事实 | 修复循环 |
| `missed_harm` | 没写到会增加或改变标签的受影响对象 / 风险成因（常在 history 里） | 修复循环 |
| `target_confusion` | 把 history 里已完成或被拒绝的步骤算到当前动作上 | 修复循环 |
| `cardinality` | 事实都写到了，只是标签个数不对 | few-shot |
| `confusable_pair` | 事实都写到了，只是选成了易混的近义标签 | few-shot |
| `gold_questionable` / `unexplained` | — | 丢弃 |

### 怎么检查分析器是否可用

沿用 Task 1 的做法，不另做试点：诊断全部错例时本来就跑两次，两次的一致率就是 G2。
**G3（人工抽查）按需做**（2026-11-09 用户决定）：只在下面两种情况下才做——
G2 低于 70%，或诊断分布明显异常（例如几乎全判成同一类，或 `missed_harm` 特别多）。
做的时候从第 1 次运行里随机抽 10 条，用户新开 Opus 5 会话审阅；审阅 prompt 届时按 Task 2 的类别生成，用完不提交。
不做 G3 的理由：子代理和分析器同为 Opus 5.5，由它审阅没有意义；换成 Opus 5 需要用户手动开会话，只在出问题时才值得花这份人工。
G2 不到 70% 才回头改 C3 一次；改后仍不过，按 Task 1 的停止规则，只用两次都判为读错类的样本。

### 诊断之后要专门看的东西，以及下一轮的候选实验（2026-11-09 补充）

1. **7 个 driver 只有名字、没有定义**（`zero_shot_reason_v1.txt` 第 12–20 行，`zero_shot_facts_v1.txt` 沿用）。
   本轮**不加定义**，保持单变量。诊断完成后看 `confusable_pair`（尤其是 Scope / Authorization）的占比；占比高的话，下一轮拆成两步：
   E0a 给每个 driver 补一句定义（参考官方任务说明）；E0b 在 E0a 上再加 Scope / Authorization 的区分规则和反例。
2. **上一轮蒸馏在 2b 上是「规则误伤」。**train_val 上 answer-v2 修好的 21 条里，只有 2 条 reason-v1 本来就对；
   剩下 19 条中，reason-v2 修好了 16 条；但在全部 107 条上，reason-v2 弄坏了 17 条（answer 线只弄坏 7 条；「修好 / 弄坏」指单条 Jaccard 上升 / 下降）（run_id：answer-v1 `094451`、answer-v2 `094504`、reason-v1 `094517`、reason-v2 `094540`）。
   本轮的修复循环有回测把关，预期能拦住这类误伤；整体回测时要专门核对，被弄坏的样本是否集中在某一条规则上。
   离线检查：把 reason-v2 弄坏的 17 条按触发的规则归类，作为本轮写 Scope / Authorization 规则时的反例来源。

## 1. 现状（只看 train 一侧）

| 运行 | 数据 | Mean Jaccard | 来源 |
| --- | --- | --- | --- |
| reason-v1 | train_evolve 461 条 | 0.735 | `results/_smoke/task2b/zero-shot-reason-v1/20261104-093411` |
| answer-v1 → answer-v2 | train_val 107 条 | 0.612 → 0.723，差 -0.111 [-0.185, -0.040]，**显著更好** | `.../zero-shot-answer-v1/20261104-094451` → `.../zero-shot-answer-v2/20261104-094504` |
| reason-v1 → reason-v2 | train_val 107 条 | 0.685 → 0.702，差 -0.017 [-0.097, +0.062]，噪声 | `.../zero-shot-reason-v1/20261104-094517` → `.../zero-shot-reason-v2/20261104-094540` |

与 2a 的情况相同：上一轮蒸馏在无推理线上有效，在主线（有推理线）上只是噪声。

### 1.1 误差拆解（train_evolve，reason-v1）

数据先验：train 里有害样本的 driver 有 75% 是**两个**标签（227 / 303），这一点和 2a 正好相反。

| 真实 → 预测 | 条数 | 平均 Jaccard | 占总损失 |
| --- | --- | --- | --- |
| 1 → 1 | 233 | 0.91 | 16% |
| 1 → 2 | 41 | 0.40 | 20% |
| 2 → 1 | 2 | 0.25 | 1% |
| **2 → 2** | 185 | 0.59 | **62%** |

主要问题**不是个数，而是组合选错了**。把选错的标签按「真实 → 预测」配对统计：

| 真实标签 | 被换成 | 次数 |
| --- | --- | --- |
| Scope / Safeguard Failure | **Authorization / Consent Failure** | **50** |
| Untrusted / Conflicting Instructions | Execution / Action Hazard | 15 |
| Untrusted / Conflicting Instructions | Authorization / Consent Failure | 15 |
| Scope / Safeguard Failure | Execution / Action Hazard | 14 |
| Insufficient Grounding / Uncertainty | No Material Risk | 13 |
| Untrusted / Conflicting Instructions | Risky Requested Outcome | 10 |

按单个标签看：Authorization 被**多给**了 75 次，Scope 被**漏掉**了 62 次，Untrusted 被漏掉了 42 次。

**Scope → Authorization 这一对就占了已知配对错误的最大一块。**上一轮的 `driver-scope-vs-authorization` 规则
（`prompts/patches/v2/driver-scope-vs-authorization.txt`）针对的正是这一对，但它只在多任务线上用过。

## 2. 实验 E0：只修 Scope / Authorization 这一对（`reason-v3`）

单变量，不依赖蒸馏流水线。

- 基础：`reason-v1`。
- 版本：`task2b-reason-v3` = `reason-v1` + 一段区分说明。
- 区分说明的写法：**先人工读 15 条 Scope→Authorization 错例**，从 train_evolve 中按 `example_id` 排序取前 15 条，
  总结标注者的区分依据，再写成至多 80 词的 TRIGGER / RULE / COUNTER-EXAMPLE。
  起草时可以参考上一轮多任务规则的核心意思：越权或绕过保护措施算 Scope；真正缺少同意才算 Authorization。
  但**必须在这 15 条上核对**之后才能定稿。
- 对照与数据：在 train_val 上与 `reason-v1`（`20261104-094517`）比较。
- 要报告：Mean Jaccard 及置信区间；Scope 和 Authorization 两个标签各自的召回率和精确率变化。
- 为什么先做这个：一对标签就是最大的已知误差块，手工修一条规则，比等完整流水线更快地给出信号。
  它的结果还能用来检验 E2 的自动规则：自动流水线如果连这一对都修不好，就说明流水线本身有问题。

## 3. 实验 E1：`facts-v1`

**Task 2b 的事实要点**：

1. 这个动作是谁要求的：用户明确要求、数据里嵌入的指令，还是 agent 自己的推断；
2. 有没有得到授权或确认，用户的授权范围是什么；
3. 动作**是否超出**了用户要求的范围，或者绕过了某个保护措施；
4. 动作依据的信息是否已经核实（对应 Insufficient Grounding）；
5. 动作本身是否危险（对应 Execution / Action Hazard），还是用户要求的结果本身有风险（对应 Risky Requested Outcome）。

第 2 条和第 3 条要**分开**列，因为 Scope 和 Authorization 的混淆正是把「超出范围」误读成了「没有授权」。

## 4. 实验 E2：智能体式蒸馏（`facts-v2`）

与 [03-task2a.md](03-task2a.md) §4 相同，有以下差异：

- 合并分组以 `driver:<A>|<B>` 为主；`cardinality:<标签>` 次之，因为个数错误只占约 21% 的损失；
- 闸门组：`gate:no-material-risk`，同样默认不收；
- 回测集里「判对的邻近样本」：在 patch 涉及的那一对标签上，「真实含 A」和「真实含 B」各取 5 条；
- 如果 E0 的手写规则有效，就把它作为 `driver:Authorization|Scope` 组的种子；自动规则必须在完整 train_evolve 上不劣于它，才能替换它。

## 5. 实验 E3：few-shot 叠加

同 Task 1：对照组为 `reason-v1` + BM25 k=10，实验组为最终 zero-shot 版本 + BM25 k=10，数据是 train_val。
dev 上 2b 的 few-shot 收益是显著的（BM25 k=10 无推理版：0.786 对比 0.711，[results/SUMMARY.md](../../results/SUMMARY.md) 主要结论第 1 条），
所以这里要重点看规则和示例是否互相抵消。

## 6. 预算

与 [03-task2a.md](03-task2a.md) §6 相当。E0 另需约 1 小时人工阅读。

## 7. 执行记录（2026-11-09）

指标都是 Mean Jaccard（越高越好），分数可由 `src/evaluate.py` 复算；配对比较用 `src/paired_bootstrap.py`（10000 次重抽样，95% 区间不含 0 才算显著）。

**第 1–2 步**（蒸馏前）：facts-v1 zero-shot 在 train_evolve 上 0.754（`_smoke/task2b/zero-shot-facts-v1/20261109-164923`，154 条错例），
train_val 0.724（`_smoke/.../20261109-164609`）；dev zero-shot 0.737、dev + BM25 k=10 0.760（`deepseek-flash/task2b/*-facts-v1/20261109-164609`），与 reason-v1 / answer-v1 相比都是噪声。

**第 3 步 诊断**：v3d 分析器（Opus 5.5，文件交接）对 153 条错例独立跑两次
（`results/analysis/task2b/20261109-164923-audit-v3d-full-r1`、`-r2`）。
**AGENTRISK-401 被排除**：该样本两次触发了模型的网络安全防护（cyber safeguards），按规定不重试、不绕过。

| | confusable_pair | cardinality | reading | missed_harm | target_confusion | gold_questionable | unexplained |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 第 1 次 | 88 | 15 | 25 | 6 | 2 | 12 | 4 |
| 第 2 次 | 85 | 17 | 17 | 16 | 2 | 11 | 4 |

两次在「读错类 / 选法类」两大类上的一致率 126/153 = 82%（G2 标准 70%，通过；G3 按 §0.1 不做）。
两次都判为选法类的有 90 条，交给 few-shot；**两次都判为读错类的 25 条**进入修复循环。
`confusable_pair` 占六成，其中 Scope 被判成 Authorization 是最大的一块，这是 §0.1「诊断之后要专门看的东西」第 1 条预期的情况：下一轮的 E0a/E0b（给 driver 补定义、加 Scope / Authorization 的区分规则）有依据。

**第 3 步 修复循环**（`results/analysis/task2b/20261109-164923-repair-v1`）：

| 轮次 | 累计通过 | 说明 |
| --- | --- | --- |
| 第 1 次尝试 | 8 / 25 | 其余都是修好了目标、但弄坏了判对的样本 |
| 第 2 次尝试 | 14 | |
| 第 3 次尝试 | 15 | 8 条三次都没通过；2 条（061、417）写 patch 的模型主动放弃：每次的规则都是「不要加 Scope / Safeguard Failure」，都弄坏同一批 gold 含该标签的样本 |

**合并**：15 条通过的 patch 里有 5 条属于 `No Material Risk` 闸门组，按规则不收；其余 10 条按原文逐条收录（与 Task 1 相同），
规则文件在 `prompts/patches/single/task2b/facts_v2/`（含 `CHANGELOG.md`），组装出 `zero_shot_facts_v2.txt`。

**整体回测**（完整 train_evolve）：

1. 10 条规则（`_smoke/task2b/zero-shot-facts-v2/20261109-202354`）：Jaccard 0.795，但 Execution / Action Hazard 召回 −16.7、精确率 −19.2，Scope / Safeguard Failure 召回 −9.8 个百分点，不过。
   逐条去掉一条规则重跑变差的 19 条：去掉多数规则能救回 4–8 条（重跑噪声），去掉 AGENTRISK-111 救回 11 条，移到 `removed/`。
2. 9 条规则（`_smoke/task2b/zero-shot-facts-v2/20261109-202959`）：Jaccard 0.793（facts-v1 0.754）；Scope 召回的下降收窄到 −2.4；
   `No Material Risk` 召回 0.977 → 0.981（不降）；其余标签全部持平或上升。**只剩 Execution / Action Hazard 召回 −16.7、精确率 −6.5（n=18）。**
3. **噪声基线**：facts-v1 在 train_evolve 上原样重跑一次（`_smoke/task2b/zero-shot-facts-v1/20261109-203726`，temperature 0），
   与第一次相比 Execution 召回同样 −16.7、精确率 −32.9，Jaccard 0.748（第一次 0.754）。
   在变差的 7 条上，只用 facts-v1 重跑两次，就有 6/4 条判错。也就是说，**这条标签的下降和 facts-v1 自己重跑的波动一样大，不能归到规则上**。
   因此按「下降超过 facts-v1 自身重跑的波动」来解释 5 个百分点的标准，接受 9 条规则的 facts-v2。这是对 §0.1 第 6 步的解释，不是原定口径，结论要连同这一点一起报告。

**第 4–5 步**（蒸馏后）：

| 运行 | 数据 | facts-v2 | facts-v1 | reason-v1 | answer-v1 | reason-v2 | answer-v2 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zero-shot | train_val | 0.734（`_smoke/.../zero-shot-facts-v2/20261109-204039`） | 0.724 | | | | |
| zero-shot | dev | **0.741**（`deepseek-flash/task2b/zero-shot-facts-v2/20261109-204041`） | 0.737 | 0.753 | 0.711 | 0.703 | 0.716 |
| BM25 k=10 | dev | **0.751**（`.../few-shot-bm25-k10-facts-v2/20261109-204043`） | 0.760 | 0.770 | 0.786 | — | — |

facts-v2 减去对照的 Jaccard 配对差（dev，n=143；正值表示 facts-v2 更好；`paired_bootstrap.py` 报的是 1 − Jaccard，这里已换成 Jaccard 差）：
zero-shot 对 facts-v1 +0.005 [−0.029, +0.038]、对 reason-v1 −0.012 [−0.054, +0.028]、对 answer-v1 +0.030 [−0.016, +0.076]；
k=10 对 facts-v1 −0.009 [−0.047, +0.029]、对 reason-v1 −0.020 [−0.052, +0.014]、对 answer-v1 −0.035 [−0.077, +0.007]。
train_val 上对 facts-v1 +0.009 [−0.039, +0.064]。**全部是噪声。**

**结论**：蒸馏在 train_evolve 上把 Jaccard 从 0.754 提到 0.793，但这部分提升没有转移到 train_val 和 dev 上。
加上示例（k=10）之后规则没有增益，k=10 下 facts-v2 甚至略低于 answer-v1（差 −0.035，区间含 0）。
2b 的主要误差是选法类（Scope / Authorization），按设计本来就不进修复循环；下一轮应先做 §0.1 列的 E0a/E0b。
