# 读稿：Trace2Skill — Distill Trajectory-Local Lessons into Transferable Agent Skills

- arXiv:2603.25158v5（2026-06-04，Work in Progress）
- 作者：Jingwei Ni（ETH/UZH）、Yihao Liu / Xinpeng Liu（PKU）、Yutao Sun（ZJU）+ Qwen Large Model Application Team（Alibaba），通讯 Mengyu Zhou
- 代码：<https://github.com/Qwen-Applications/Trace2Skill>（Apache-2.0，含 4 个 released skill）
- 阅读时间建议：正文 §1–§4 约 40 分钟；§4.1 三个 apples-to-apples 对比是全文最该细读的部分；附录 C.2/C.3 和第 7/8 节（表 14、表 15）是判断可信度的关键。

## 0. 一句话

把「一堆 agent 跑任务的执行轨迹」一次性并行归纳成**一份静态 skill 目录**（SKILL.md + references/ + scripts/），而不是逐条反思存进记忆库、也不是按到达顺序一条条改 skill。

关键词：**many-to-one consolidation**、**portable skill**、**trajectory-grounded SoP**。

### 术语速查（中英对照）

| 术语 | 英文 | 在本论文里的具体所指 |
| --- | --- | --- |
| 轨迹 | trajectory（τ） | 一次完整执行记录：query + 推理/工具调用历史 + 最终产物 + 二元对错 |
| 补丁 | patch | **轨迹级（trajectory-level）**的 skill 修改提案，不是全局编辑；每个 patch 只来自一条轨迹的分析 |
| +Error / +Success / +Combined | error-only / success-only / combined patch pool | 只用失败轨迹 / 只用成功轨迹 / 两者都用的三类 patch 池，对应三种消融变体 |
| 深化 / 创建 | skill deepening / skill creation | 初始 skill 是人写的（Anthropic 官方 xlsx skill）/ 是 LLM 靠参数知识空想的草稿 |
| 同分布 / 分布外 | in-distribution (ID) / out-of-distribution (OOD) | ID = 测试集与进化集同 benchmark；OOD = 换数据集（WikiTQ、HiTab、AIME、VAREX、OfficeBench） |
| agentic 分析师 | agentic error analyst (𝒜⁻) | ReAct 循环：能打开产物、对 ground truth、重跑校验、否掉自己的错误假设 |
| 单趟基线 | single-pass / single non-interactive LLM call（论文记作 `+Error LLM`） | **一次非交互 LLM 调用**读失败轨迹就写 patch：不开产物、不对答案、不验证修法 |
| 推理-行动循环 | ReAct（Reasoning + Acting，Yao et al. 2023） | 边推理边调工具、能读取每次工具返回再决定下一步的 agent 循环 |
| 标准作业流程 | standard operating procedure (SoP) | 从多条轨迹反复出现的行为里归纳出的标准流程，是本框架的最终产物形态 |
| 归纳式压缩 | inductive compression | 把 N 条局部证据压成一条带冲突消解的通用规则（vs 最近邻式检索复用） |
| 合并算子 | merge operator (ℳ) | Stage 3 里负责去重、解冲突、保留高频模式的角色，由同一个底层模型担任 |

## 1. 它要解决什么

背景事实（§1，都有引用支撑）：

1. 人写的 skill 不总是有用。表 1 里 Anthropic 官方 xlsx skill 让 122B 的 Vrf 从 27.67 涨到 48.33，但让 35B 从 19.00 **掉到 9.67**。skill 不是白送的。
2. 纯参数知识生成的 skill 基本没用。Parametric 24 条：122B 26.17、35B 20.17，贴着 No Skill。
3. 现有「经验进化」路线有两个毛病：把轨迹级教训存进检索记忆（知识碎片化、依赖检索质量）；或者轨迹按批到达就顺序改 skill（**结果依赖更新顺序**，后一步建立在前一步的编辑上）。

Trace2Skill 的赌注：人写 skill 的方式是「先看很多轨迹 → 抽象出反复出现的模式 → 写一份紧凑流程」，那就把这个归纳过程工程化。

## 2. 形式化（§2.1）

- skill 是一个人类可读目录 𝒮 = (M, ℛ)：M 是根 SKILL.md，ℛ 是 references / scripts / assets。
- 目标：𝒮* = ℰ(𝒮₀, 𝒟_evolve, π_θ)，使得 𝒫(𝒮*, π_θ, 𝒟_test) > 𝒫(𝒮₀, π_θ, 𝒟_test)。
- 两种初始化 𝒮₀：**Deepening**（人写的专家 skill）/ **Creation**（纯参数知识生成的弱草稿）。
- 全程不更新参数、不做 test-time retrieval。产物就是一个能直接 load 的目录。

## 3. 三段流水线（§2.2–2.4）

| 阶段 | 做什么 | 关键设计 |
| --- | --- | --- |
| Stage 1 轨迹生成 | ReAct harness，固定 agent + 𝒮₀ 跑全部 evolve 题，记录 query / 推理与工具调用 / 最终产物 / 二值判对 | 轨迹生成彼此独立、可并行；先收完整个语料再进入分析 |
| Stage 2 并行 patch 提案 | 一条轨迹一个 analyst，产出**轨迹级 patch**（不是全局编辑）→ patch pool 𝒫 = 𝒫⁻ ∪ 𝒫⁺ | **分析师角色不对称**：错误分析师 𝒜⁻ 是 ReAct 循环，能打开产物、对 ground truth、**重跑校验**候选修法；成功分析师 𝒜⁺ 单趟读轨迹找可复用行为。无法给出因果解释的失败**直接丢弃**，不进 𝒫⁻ |
| Stage 3 层次合并 | 每层最多 B_merge（=32）个 patch 合成一个，共 L = ⌈log_{B_merge}|𝒫|⌉ 层；最终 p* 翻成 diff 打上去 | 合并算子 ℳ 就是同一个 π_θ，不需要外部 teacher；合并时去重、解冲突、**优先保留高频模式、丢掉一次性怪招**；落盘有确定性 guardrail（改不存在的文件→拒、行号冲突→挂起、改完校验格式） |

合并那一步同时完成了**归纳泛化**：因为每个 patch 只来自一条轨迹，多个独立 patch 反复改同一处，就是「这是任务的系统性属性」而不是个例的证据。

延迟账（§B.1）：70 条错误教训、W=128 workers → 分析一轮跑完；B_merge=32 → ⌈log₃₂70⌉≈2 轮合并。所以总串行 LLM 轮数 ≈3，对照顺序基线要 N 轮 / ⌈N/B⌉ 轮。

## 4. 主结果怎么读（表 1）

设定：SpreadsheetBench-Verified 400 条切成 evolve 200 / test 200；OOD 用 WikiTableQuestions、HiTab **转成表格形式**；三个种子（41/42/43），报告的 Avg = (ID_avg + OOD_avg)/2。

### 指标口径（Vrf / Soft / Hard，三者跑在不同数据集上）

SpreadsheetBench 每道题配多个测试用例（同结构、不同数值，平均 3 个），模拟 online judge。判分是**逐格精确比对**：只比 `answer_position` 指向的区间，`data_only=True` 读缓存值，数值四舍五入 2 位、datetime 转 Excel 序列号取整、空串与 None 视为相等、`type` 不同直接判错（所以「数字写成字符串」会挂）。

| 指标 | 定义 | 数据集 / 分母 |
| --- | --- | --- |
| **Vrf** | 实例级通过率：该实例**所有**测试用例都过才记 1，否则 0 | **SpreadsheetBench-Verified 留出 200 条**（人工校验过的子集） |
| **Soft** | 测试用例级部分分（IOI 规则）：通过的用例数 / 总用例数，再对实例平均 | full SpreadsheetBench **2,529 条**（已剔除演进集） |
| **Hard** | 用例级全过才给分（ICPC 规则），即实例级 all-or-nothing，再对实例平均 | 同上 2,529 条 |
| WikiTQ / HiTab | OOD：把表格 QA 数据集转成「给输入表、填 answer_position」的表格任务 | 2,810 / 1,585 条 |

三个 ID 指标**分母不同、题目不同，数值不能横向比大小**。例如 35B Human-Written 是 Vrf 9.67 / Soft 13.03 / Hard 3.37——Soft > Vrf 并不矛盾。读表优先 Vrf（最接近「这题到底做对没有」，且噪声最小），Soft 看「是不是差一点」，Hard 看稳健性（换数据就崩的解法在 Hard 上现原形）。

基线（绝对分，Vrf）：

| Skill | 122B Vrf | 35B Vrf | 备注 |
| --- | --- | --- | --- |
| No Skill | 27.67 | 19.00 | — |
| Human-Written（官方 xlsx） | 48.33 | **9.67** | 小模型上比不用还差 |
| Parametric（LLM 空想 skill） | 26.17 | 20.17 | 等于没用 |

Deepening（从人写 skill 出发，报相对 Human-Written 的增量）：

- 122B 作作者：+Combined Vrf **+21.50**（→69.83），Soft +10.87，Hard +12.50，OOD 也正。
- 35B 作作者：+Combined Vrf **+20.00**（→29.67），Avg +14.04 —— 全文**最大绝对 Avg**，即「小模型产的 skill 反而最可移植」。
- 作者和用户不同模型时也基本正迁移，这一条是跨规模可移植性的主证据。

Creation（从 Parametric 草稿出发）：

- 122B 作作者 +Error：Vrf +22.83（→49.00），**WikiTQ +57.65**（→81.38）——摘要里那个 "up to 57.65 pp" 就是这一格。
- 35B 作作者 +Combined：Avg +13.31，OOD 涨得比 ID 多。

其他域（都是从零 Creation，delta 相对 No Skill）：

| 域 | 结果 |
| --- | --- |
| 数学（DAPO 400 训 / 100 ID + AIME'26 OOD） | +Error 最稳：122B 用户 D-Test +4.0、AIME +2.9；35B 用户 +5.0 / +5.0。+Success 在弱模型上会掉（35B 作者→35B 用户 AIME −1.2） |
| DocVQA（仅 50 条用于进化，5299 条测试） | +Combined 最强：122B 用户 Acc +22.25（70.27→92.52）、ANLS +0.2534；跨模型 +17.22 |
| PDF 抽取（VRDU→VAREX） | 76.9% → **85.3%** |
| PPTX（TSBench 训练→留出 deck） | 72.5% → **88.8%**（+16.3pp，最大增益） |
| DOCX（生成任务→OfficeBench 留出） | 79.7% → **87.5%** |

跨家族（§3.3 / §B.4）：Gemma-4-31B-it 和 GPT-5.5-high 用**自己的**轨迹深化官方 skill 都能自涨，也能吃 Qwen 产出的 skill；其中 GPT-5.5-authored Deepening +Combined 让 Qwen3.5-122B 到 68.00 Vrf（No Skill 27.67 / Human-Written 48.33）。

## 5. §4 Analysis 精读：这一章在干什么

§3 只回答「有没有用」，§4 要回答四个不同的问题，四个小节各管一个：

| 小节 | 问题 | 性质 |
| --- | --- | --- |
| 4.1 | 是**哪个设计**在起作用？ | 消融 / 归因（全文唯一的因果主张） |
| 4.2 | 蒸馏出来的东西**长什么样**？ | 定性产物分析 |
| 4.3 | 能不能**只挑好 patch**，比全量合并更强？ | 选择问题 + 反例 |
| 4.4 | 换个模态、换个分布**还成立吗**？ | 外部效度 |

读的时候注意一件事：4.1 的三个对比是**同轨迹池、同 harness、同模型，只换一个变量**；4.4 和附录 G 不是。作者自己在 §4.1 末尾写死了这句：「我们的因果主张只在 §4.1」。

### 5.1 三刀隔离：并行、静态化、agentic

**第一刀：并行合并 vs 顺序编辑**（表 4；全部 error-analyst，全部从 Human-Written 出发）

| 条件 | 122B Vrf / Soft / Hard | 35B Vrf / Soft / Hard | 墙钟 |
| --- | --- | --- | --- |
| Seq, B=4（每 4 条轨迹改一次） | 59.00 / 40.63 / 20.63 | 26.17 / 22.37 / 7.47 | ~15 min |
| Seq, B=1（每条改一次） | 61.83 / 44.40 / 25.40 | 26.00 / 23.83 / 10.57 | ~60 min |
| **Parallel（本文）** | **65.83 / 46.60 / 27.43** | 27.00 / **22.20 / 8.20** | **~3 min** |

读法有三层，别只读第一层：

1. 效率：3 min vs 15 / 60 min，约 5–20×。而且差距随轨迹数 N **线性**放大（顺序法要 N 轮或 ⌈N/B⌉ 轮，并行法只要 1 + ⌈log₃₂N⌉ 轮）。这是全文最不可辩驳的结论。
2. 质量：122B 三项全赢，且**顺序法的质量随批量变大而下降**（B=1 61.83 > B=4 59.00）——即"改得越勤越好，但越勤越慢"，这是个两难，并行直接绕掉了。
3. 让步在哪：35B 的 Soft/Hard 上 Seq-B=1 更高（23.83/10.57 vs 22.20/8.20）。也就是说"并行在质量上不吃亏"**只在大模型上无条件成立**；小模型上要拿 Vrf 换 Soft/Hard。作者写了这一句，但结论段没重复它。
4. 一个隐藏观察：这张表里所有条件都比 Human-Written 的 35B 基线（Vrf 9.67）高得多，说明**这张表本身就在证明"skill 能救小模型"**，而不只是证明并行更好。

**第二刀：一份静态 skill vs 检索式经验记忆**（表 5）

- 实现：按 ReasoningBank 原设定，成功和失败轨迹都存教训，用 Qwen3-Embedding-8B 检索 top-1 记忆注入；对照组 +Combined 用**同一批轨迹**。
- 结果：ReasoningBank 122B 56.00 / 40.10 / 21.30，35B 20.50 / 17.30 / 4.97；+Combined 69.83 / 47.17 / 29.53 与 29.67 / 18.80 / 5.73。**Vrf 差 13.8 和 9.2 个点**。
- 边界：**OOD 没比**。理由是同 query 语义距离太远、检索无从谈起。理由成立，但结论就只能限定在「同分布、检索有得检」的场景。这一条对 AgentRisk 反而是最相关的，因为你的 few-shot 检索就是在同分布上做的。
- 深层含义：检索式记忆的问题不是"记忆不对"，是**记忆是碎的、按相似度拼装的**；蒸馏的价值在于把 N 条证据压成一条带冲突消解的规则。

**第三刀：agentic 错误分析 vs 单趟 LLM**（表 12，配套 §C.1）

| 作者/模式 | agentic +Error Avg | 单趟 +Error LLM Avg | 谁赢 |
| --- | --- | --- | --- |
| 122B Deepening | **36.21** | 28.00 | agentic |
| 122B Creation | 26.02 | **26.60** | 单趟（唯一反例） |
| 35B Deepening | **32.58** | 28.80 | agentic |
| 35B Creation | **34.45** | 26.49 | agentic |

- 机理不是猜的，§C.1 做了 **33 例共同错例的人工审计**：两条流水线只有 **12.1%（4 例）** 强一致，**54.5%（18 例）** 在根因或该打的 patch 上明确分歧。
- 最硬的一条证据：在日志里出现 parse error 的样本中，单趟 LLM 把 parse error 当**主根因**的比例 **57%**，agentic 只有 **14%**。因为单趟只能看日志，看不到"产物其实是对的"。
- 还有一个直接的反例故事：单趟 LLM 编造了三个不同的失败原因，而打开产物一看输出是对的——只有能重跑校验的循环才能否掉这种解释。
- 为什么这重要：它把"patch 该锚定在哪"讲清楚了——agentic 锚在**已验证的失败机制**（错的目标区间、stale 公式值、工作簿结构损坏、类型转换、缺读回校验），单趟锚在**日志表面症状**。前者才会变成跨模型、跨 OOD 都成立的 guardrail。
- 反例怎么读：122B Creation 那格输，是因为单趟在 OOD 表格题上强得多（47.26/30.26 vs 31.62/15.66），而 ID 上 agentic 仍赢。也就是说**单趟偶尔能产出"更野但更能迁移"的 patch**，代价是 ID 掉。这不是噪声，是真实的 trade-off。

三刀合起来的结论边界：

| 结论 | 成立范围 |
| --- | --- |
| 并行 > 顺序 | 效率无条件；质量在 122B 无条件，35B 上 Soft/Hard 让位 |
| 静态 skill > 检索记忆 | 仅 ID；OOD 未测 |
| agentic > 单趟 | Avg 4 格里赢 3 格；OOD 上单趟可能更野 |

### 5.2 §4.2 产物长什么样：SoP 的层级是自动长出来的

323 个轨迹 patch 合并后，四大 SoP 覆盖率 55.1% / 54.8% / 42.7% / 16.4%（一个 patch 可命中多个主题），中等支持度还有 4.6% / 4.6% / 4.0% 三条。关键是**分布形状**：

- 高频 → 写进主 SKILL.md（通用流程、必做动作）；
- 低频怪癖 → 路由进 **13 个 references/** 文件（单元格颜色提取、特殊业务逻辑下的 FIFO/LIFO 错配），主文档不背这些；
- 这个「主文档=通用流程、references=按需查表」的层级**不是人设计的**，是从证据的支持度分布里自动恢复出来的。

这条对写 skill 的人比具体条文更有用：**支持度就是分层信号**。50% 以上的进主文档，5% 以下的进 references，中间的看情况。

### 5.3 §4.3 选择问题：为什么"挑最好的 patch"会失败

设定（§E）：全量合并是默认做法，因为不用逐 patch 验证。那如果 patch 质量参差，挑子集会不会更好？两个选择器，都在 200 条 evolve 集上跑、在 **32 条验证集**上打分：

- **Greedy top-1**：每轮取覆盖率 ≥5 的 5 个候选，做 add-one / remove-one 干预（Δ⁺ = 加了它涨多少，Δ⁻ = 从全集里拿掉它掉多少），丢掉 Δ⁺<0 或 Δ⁻<0 的，按 r = Δ⁺+Δ⁻ 排序取第一。
- **BO**：固定 m ≤ 15 个高覆盖 patch 的全集，搜二进制包含向量，TPE 采集函数（γ=0.2，α=1，ρ=0.1），每轮从 500 候选池评 8 个，4 轮或 3 轮无提升即停。

结果与机制：

- 贪心（Fig. 5，只有图没有表）快速上升然后**平台化，三条曲线全部低于全量合并**；+Success 还会先掉后部分恢复。
- 平台化的两个机制（§C.2，seed 41 的十轮路径）：
  1. **patch-irrelevant regression**：某一步 fail→pass 57 条、pass→fail 21 条；另一步 46 vs 26。**每一步都在同时修和坏**。而且这些被弄坏的题跟该 patch 的源任务**零重叠**——是副作用，不是针对性回退。净准确率自然停住。
  2. **semantic overlap**：十轮里选择器反复回到三个主题——重算与校验（第 1、6 轮）、结构/表头/工作表（2、9）、格式/类型/日期（4、5、7、8）。新选中的 patch 只是在重述 skill 里已有的指导，边际收益趋零。
- BO（表 6）：Evolve 68.00→72.83、Vrf 65.83→69.83、Soft 46.60→47.27、Hard 27.43→28.90、WikiTQ 76.30→77.51、HiTab 43.45→43.38（**唯一略降**）。

我的两个判断，比论文说得狠：

1. **BO 的收益基本是白捡的**。BO 选出的 +Error 是 69.83 Vrf；而表 5 里 Human-Written +Combined 也是 **69.83** Vrf。也就是说，**再跑一遍 +Combined 就能拿到 BO 花几倍验证成本换来的那个数**。作者把 BO 定位成"未来工作"，是诚实的。
2. **32 条验证集做选择，增益里有多少是选择噪声说不清**。而且贪心那条对照**只有曲线没有表**，没法复算。这是我唯一想给这篇扣分的方法细节。

### 5.4 §4.4 推广：源分布和目标分布是分开的

三个域共用 Anthropic 官方 pdf / pptx / docx skill 作为底座，但关键在**源轨迹和目标评测不同分布**：

| 域 | 源轨迹（只用于进化） | 留出评测 | Base → 进化后 |
| --- | --- | --- | --- |
| PDF 抽取 | VRDU Registration Forms | **VAREX Flat**（另一个数据集） | 76.9% → **85.3%**（+8.4） |
| PPTX 编辑 | TSBench 训练 deck | TSBench **deck-disjoint** OOD | 72.5% → **88.8%**（+16.3） |
| DOCX 编辑 | 合成文档操作任务 | **OfficeBench** DOCX 留出（64 子任务，max_turns=100） | 79.7% → **87.5%**（+7.8） |

正确的读法：这三个数字证明的是「**从分布 A 的轨迹能蒸出对分布 B 有用的流程**」，不是「skill 通杀」。DOCX 那格尤其说明问题——源数据是**合成**的，目标是最真实的 OfficeBench，照样涨 7.8 个点。反过来 PPTX 的 +16.3 最大，是因为源和目标的差距最小（同 benchmark 不同 deck），别把它当成泛化能力的证据。

### 5.5 附录 G 与 H：两个"对照"要分开用

- **§G 跨系统对照**（同模型同 benchmark）：XSkill 20.0、EvoSkill 59.5（本地 harness）/ 33.5（Claude Code proxy）、SkillGen 27.5，Trace2Skill 65.83 / 69.83。作者自己说这是 whole-system 分，混了 base model、harness 和工程，**不能归因到设计**，只作参考。而且三个对手的复现分数低得可疑（XSkill 20.0 几乎等于 No Skill 27.67 之下），复现协议是否公平无法验证。引用时只当"我们没有输"，别当"我们赢了 3 倍"。
- **§H skill-creator 基线**：Claude Code + Opus 4.6 medium 跑官方 skill-creator，Deepening 平均 29.00 → **23.33（越改越差）**，Creation 23.17 → 22.50。这条比什么都说明问题：**会写 skill 的模型 + 官方流程，没有轨迹锚定照样把 skill 改坏**。

### 5.6 §4 该怎么引用、怎么不引用

可以引用：并行合并的效率与质量（大模型上）、agentic 分析优于单趟日志分析、SoP 的支持度分层现象、patch 价值是组合性的所以默认全量合并。

不要引用：57.65 pp（单格 OOD）、BO 是必需组件（它是可选优化）、跨域通杀（三个域的 transfer 设计各不相同，且 PPTX 的增益来自同 benchmark）。

## 6. 附录 C 补充：产物细节与中等支持度 SoP

四大 SoP 的具体条文见 5.2。这里补三个中等支持度（3.1%–4.6%）的，它们同样被写进了最终 skill——正好演示"低于 5% 但不进 references"的中间带：

| SoP | 支持度 | 内容 |
| --- | --- | --- |
| 目标区间与 answer_position 校验 | 4.6% | 写之前先确认 sheet 名、cell range、`answer_position` 字段。读错这些**不报错、直接 0 分**，是最典型的静默失败 |
| dtype 与 datetime 保真 | 4.6% | 日期和数值用原生 Python 类型写，别写字符串。pandas 解析和 openpyxl 赋值都会静默把 datetime 变成字符串——写前先看每列 dtype |
| 编辑前先探查工作簿结构 | 4.0%（成功侧为主） | 先列出所有 sheet、检查行列布局、确认表头位置，再动手。这条撑起了那次运行里 ~151 个偏成功侧的 patch |

另外两个数字值得记：323 个 patch 里有 ~151 个来自成功侧（说明成功分析师不是摆设，只是产出更偏"预防"而非"修复"）；13 个 references 文件承载全部低频怪癖。

结论一句话：**patch 的价值是组合性的，不可按单点增量相加**——所以默认全量合并，而不是贪心挑最好的几个（理由见 5.3）。

## 7. 我的批判性判断

站得住的：

- 「schema/格式类工具链上的操作型 SoP 可以从轨迹里蒸馏出来，而且跨模型可移植」——这是本文最硬的部分，四个文档域 + 数学 + VQA 都有正迁移，且作者给了单变量消融。
- 「并行 many-to-one > 顺序编辑」在**效率**上是无争议的（20×），质量上只在 122B 站得住。
- 「单份 skill > 检索记忆」在 ID 上站得住，OOD 未验证。

需要打折的：

- **+57.65 pp 是单格挑出来的**。WikiTQ 是作者自己转成表格形式的 OOD，Parametric 基线 23.73 分已经是地板，涨到 81 更多说明「读回校验类 SoP 对表格题致命」而不是「skill 泛化到任意 OOD」。看 Avg 更靠谱（Creation 35B 作者 Avg +13.31、122B 作者 +18.62）。
- **验证集只有 32 条**，BO 选择还在这 32 条上做搜索（§E），选择噪声和过拟合空间都不小；作者自己在 Limitations 里承认用全 evolve set 会更准但太贵。
- **35B 用户上 Human-Written 只有 9.67**，而 No Skill 19.00。这既是最有说服力的动机，也提醒：**任何 skill 化方案在小模型上先要证明不比空 prompt 差**。
- **100% self-evolution 只覆盖 Qwen3.5 两个规模**；Gemma/GPT 只做了深化自己 skill + 吃 Qwen skill 的一侧。
- 复现性：README 自己写了「100% 复现困难，且一次幻觉编辑就能毁掉整个 skill 的稳健性」，所以他们做了训练集验证再选 seed。这条对你直接有用——**别信一次跑出来的 skill，必须回测**。
- 20,000 A100 GPU 小时。这套方法的成本门槛不在算法，在 rollout。

## 8. 对 AgentRisk 这个 repo 的直接含义

当前状态（README 2026-10-21）：zero-shot v1 MAE 0.301 / Jaccard 0.811 / 0.726；few-shot 最好的是 BM25 k=10（0.189 / 0.862 / 0.793）。**这本质上就是论文里的 retrieval-memory 范式**——每条样本检索 k 个相似样例塞进 context。论文表 5 说明这条路的上限低于「把轨迹教训蒸馏进一份静态 instruction」。

可迁移的映射（不需要 GPU，也没有 100 步 ReAct）：

| Trace2Skill 概念 | AgentRisk 里的对应物 |
| --- | --- |
| 轨迹 τ | 一条 dev/train 样本 + 模型完整 raw_response（`raw_responses.jsonl` 已有） |
| 判对/判错 | Task1 MAE 误差 > 阈值、Task2 Jaccard < 1、标签集合错误 |
| 错误分析师 𝒜⁻（agentic） | 能读 `predictions.jsonl` + gold + 打分脚本的循环：先复现、再归因、再给 patch、**再回测** |
| 轨迹级 patch | 对 prompt/instruction 的一段结构化改动（新增判定规则、改标签边界、加反例约束） |
| 层次合并 | 把 N 条 patch 合并成 1 版 instruction（去重、解冲突、保留高频模式） |
| SoP | 「历史最后一步是拒绝动作时，风险等级按拒绝本身评，不按被拒绝的请求评」这类可复用判定规则 |
| 验证集 | train 里切 100 条做验证，**dev 143 条只做最终 test**（现在 dev 被同时用来调 prompt，属于在 test 上调参） |

具体建议的下一步（按性价比排）：

1. 先做**错误归因**，不急着改 prompt。用 train 568 条跑现版本，把错例按类型聚类（等级高估、多给第二标签、拒绝动作误判、上下文忽略），产出计数表。这是 𝒜⁻ 的输入。
2. 拿最小的一条规则先验证闭环：只改「历史最后动作是 refusal → 等级按 refusal 评」，train 上回测，正向才保留。一次只动一个因素（README 计划 2 本来就这么写的）。
3. 把 dev 冻结。要调参就在 train 内部切分，别继续在 143 条 dev 上做选择，否则最终数字没意义。

## 9. 推荐阅读顺序

1. 摘要 + §1（10 min）：抓住「human skill 在小模型上有害」和「三种范式对比」两个动机。
2. 图 1、图 2（5 min）：左/右两张图就是全文论点。
3. §2.3–2.4（10 min）：分析师不对称 + 层次合并，这是方法本体。
4. 表 1（10 min）：只读 Vrf 和 Avg 两列 + 三行基线，别被 OOD 单格带走。
5. §4.1 三个对比 + 表 4/5/12（15 min）：这是唯一能做因果归因的部分，也是审稿人会打的地方。
6. §C.1–C.3（10 min）：agentic 分析师的机理证据 + SoP 真实长相。想要模板就直接抄这里。
7. 其余表（数学/VQA/PDF/PPTX/DOCX）快速扫，看方向不看小数点。
8. 要动手就 clone 仓库，先只读 `released_skills/trace2skill-xlsx-122B-combined/SKILL.md`——那是整篇论文最浓缩的产物。
