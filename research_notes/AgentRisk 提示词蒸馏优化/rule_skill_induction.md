# 规则/洞见/技能归纳（rule / insight / skill induction）方法综述：诊断 AgentRisk Trace2Skill 式管线的失效

> 调研日期 2026-11-09。所有数字均附来源与章节/表号；「Inferences」小节为本人推断，不是论文报告的事实。
> 术语约定：技能归纳（skill induction，从轨迹/错误/标注数据中提炼可复用的自然语言规则并写进提示词）；分析器（analyst LLM，看到模型输出与金标后写教训的 LLM）；保留集（held-out set，不参与规则生成、只用于验证的数据）；翻转（flip，某条规则使原本正确的样本变错，或反之）。

## Q1. Trace2Skill（arXiv 2603.25158）的精确管线、应用方式、验证与结果

### Takeaway
Trace2Skill 并非「按混淆类型聚类 + 支持度阈值 + 静态插几条规则」：它把成功轨迹和失败轨迹分别交给两个分析器，失败分析器是**能对照金标、检查产物并验证修复的智能体循环**，无法因果解释的失败被丢弃；随后对上百个补丁做层级合并成一个技能目录，长尾边角情况放进按需读取的 `references/` 文件。它在 200 题保留集上验证，并明确报告「全量聚合」会因与补丁无关的回退而停滞，而用验证集挑选补丁能再提升几个点。我们的实现在分析器、成功样本、验证三个环节都与原文不同。

### Cited Findings
- 作者：Jingwei Ni、Yihao Liu 等，Qwen Large Model Application Team（阿里巴巴）与 ETH/UZH/北大/浙大；页面版本为 v5，修订于 2026-06-04（原始提交日期页面未显示）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 核心思想：不像「每条轨迹之后顺序修改技能」（结果依赖顺序）或「测试时检索单条经验记忆」，而是并行分析大量轨迹，把反复出现的教训整合成**一个静态技能目录**（§2）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 轨迹生成（§2.2）：冻结的 ReAct（Reasoning + Acting，推理与工具调用交替的智能体框架）智能体带初始技能 S0 在进化集上运行，记录二元结果，并把轨迹分为失败与成功两组 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 补丁提议（§2.3）：失败交给错误分析器 A−，它是 ReAct 循环，可以检查产物、**对照金标**、**验证修复**；**无法因果解释的失败会被排除**。成功交给成功分析器 A+（一次 LLM 调用），提取可复用行为。两者都写针对 S0 的简洁补丁；附录 A 并行跑 128 个子智能体 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 整合（§2.4）：层级合并 L=⌈log_B|P|⌉ 层，B_merge=32（附录 A）；合并算子去重、解决冲突、保留不重叠的洞见，**优先采用在多个独立补丁中重复出现的模式**；再转成 diff 编辑并加确定性护栏（拒绝改不存在的文件、扣留行范围冲突、校验格式）。主管线**没有显式聚类或支持度阈值**；唯一阈值（coverage ≥5）出现在附录 E 的贪心选择器中 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 推理时应用：整合后的技能直接替换 S0 加载，不做检索；低支持度的小众边角情况放进按需读取的 `references/` 文件，主 SKILL.md 只保留通用流程（§C.3）。文中未描述条件触发或检索触发 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 验证：SpreadsheetBench-Verified 按 200/200 拆分为进化集与保留测试集，三个随机种子（41/42/43）取平均（附录 A）；另在 WikiTQ、HiTab 上测分布外迁移（OOD，out-of-distribution，测试分布与进化分布不同）— [arXiv HTML](https://arxiv.org/html/2603.25158)；仓库复现脚本同样使用训练切片 `0:200`、保留切片 `200:400`，`SEED=41`，`WORKERS=128` — [GitHub](https://github.com/Qwen-Applications/Trace2Skill)
- 收益（表 1）：相对基线的 Avg 提升 +9.65（122B 作者模型，Deepening +Combined）和 +14.04（35B 作者模型，Deepening +Combined）；摘要里的「最高 57.65 个百分点」来自 Creation、35B 作者、+Error、WikiTQ、122B 使用者这一格 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 数学（表 2）：Creation +Combined 在 D-Test 上给 122B 使用者 +3.0、35B 使用者 +6.0；**+Error（只用失败）是最稳定的设置** — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 其他领域（§4.4 / 表 13）：PDF 76.9%→85.3%，PPTX 72.5%→88.8%，DOCX 79.7%→87.5% — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 消融：并行 vs 顺序（表 4）：并行 65.83 Vrf，约 3 分钟；Seq-B=1 约 60 分钟，在 35B Soft/Hard 上略高 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 消融：检索 vs 整体技能（表 5）：+Combined 69.83 Vrf（122B）/ 29.67（35B），检索式记忆 ReasoningBank 为 56.00 / 20.50 — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 消融：**智能体式 vs 单次调用错误分析**（图 4/5、表 12、附录 C.1/D）：智能体式 +Error 在 4 个作者×模式组合中有 3 个 Avg 更高；在 33 个案例的审计中，**单次调用 LLM 分析器把「解析错误」误判为根因的比例为 57%，智能体式分析器为 14%** — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 消融：选择性聚合（图 5、表 6、§4.3、附录 E）：贪心选择会停滞在全量聚合以下，原因是「与补丁无关的回退」和语义重叠；用贝叶斯优化（Bayesian optimization / BO，基于代理模型的黑盒搜索）在 122B +Error 上挑补丁，Vrf 从 65.83 升到 69.83，但计算昂贵；局限性一节指出 BO 依赖一个 **32 题的验证集** — [arXiv HTML](https://arxiv.org/html/2603.25158)
- 学到的标准作业流程（SoP，standard operating procedure，一步步的操作规程）（§4.2、附录 C.3）：在 323 个补丁中，最常见的是「公式重算与回写验证」（55.1%）、「回写用 openpyxl 而不是 pandas」（54.8%）、**「回读验证」（42.7%）**、「结构编辑安全」（16.4%）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 附录 G（图 7，SpreadsheetBench-Verified Vrf）：无技能 27.7；XSkill 23.0（低于无技能）；**SkillGen 27.5，其训练切片为 52.5，「训练集提升但测试集回退」**，作者归因于可能的分布偏移；EvoSkill 59.5（React 框架）/ 33.5（Claude Code）；Trace2Skill 65.8（+Error）/ 69.8（+Combined）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 附录 H（表 14）：Anthropic skill-creator 基线平均**不能**改进基础技能（Deepening：基础 29.00 → 23.33；122B/122B 一格 48.33 → 27.33）— [arXiv HTML](https://arxiv.org/html/2603.25158)

### Inferences
- 我们的管线与原文有三处关键差异：(a) 我们的分析器是看到金标的单次调用，原文消融显示这类分析器根因误判率高得多（57% vs 14%），并且原文会**丢弃无法因果解释的失败**；(b) 我们只用失败，没有成功分析器，所以规则从未「看见」那 16 条本来正确的严重度 1 样本；(c) 原文对补丁做层级合并并把低支持度内容放进按需读取的 references，我们则把 2–5 条规则静态插到每个样本前面。
- 原文的任务是带可执行检查的智能体任务（表格读写、数学），那里的「回读验证」类 SoP 有客观反馈；我们是一次非交互 LLM 调用（single-pass）的序数分类，没有执行反馈，所以原文收益不一定能迁移。SkillGen 的「训练 52.5 / 测试 27.5」和我们 Task 2b「train_val 涨、dev 不涨」是同一类现象。
- 原文最有价值、可迁移的部分是**保留集上的补丁选择**（BO / 贪心），而不是合并本身；它自己也承认全量聚合会带进与补丁无关的回退。

### Gaps
- 附录 C.3 中 references 与 SKILL.md 的具体支持度切分标准、附录 E 贪心选择器的完整算法，抓取的文本里都没有完整读到。
- 原文没有在**分类 / 序数打分**任务上评测，也没有报告按样本统计的翻转（正确→错误）数量。

## Q2. 其他方法：洞见如何提取、过滤/打分、应用，以及报告结果

### Takeaway
较强的方法几乎都具备以下三点中的至少两点：(1) 从**成功–失败对比**而不仅是失败中提取洞见（ExpeL、AutoGuide）；(2) 用带计数的方式（投票、覆盖度、置信度、helpful/harmful 计数）或保留集验证来过滤规则（ExpeL、HtT、ACE、GEPA）；(3) **按条件检索**规则，而不是全部静态注入（AutoGuide、HtT 的 XML 检索、AWM 的选择性提供）。LEAP 这类「从错误中学原则」的方法在多个模型–任务组合上会造成下降。

### Cited Findings
**ExpeL（Zhao et al., AAAI-24；arXiv 2308.10144，v1 2023-08-20）**
- 提取：LLM 比较**同一任务的失败轨迹与成功轨迹**，并在不同任务的成功列表中找共同模式（§4.2、算法 2、图 2）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- 过滤：对洞见集执行 ADD / EDIT / UPVOTE / DOWNVOTE；新洞见的重要性计数初始为 2，UPVOTE/EDIT 加分，DOWNVOTE 减分，计数为 0 即删除；作者称这样能抵抗次优的成功轨迹。提取模型用 gpt-4-0613，因为它比 gpt-3.5 更守操作指令、幻觉更少 — [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- 应用：**所有洞见全局拼接**进任务说明，另外按任务相似度（Faiss kNN + all-mpnet-base-v2）检索 top-k 成功轨迹作为少样本示例（§4.3）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- 消融（§5.6、表 3）：HotpotQA 成功率 ReAct 28.0；人工写的洞见 32.0；**把反思（reflection）加进洞见提取 29.0**；gpt-3.5 提取的洞见 32.0；ExpeL 39.0。作者把「加反思反而变差」归因于反思中有时含幻觉 — [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- 只从初始少样本示例提取的洞见相对 ReAct 没有优势（图 6，正文无具体数字）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)

**AutoGuide（Fu et al.；arXiv 2403.08978，v1 2024-03-13，v2 2024-12-03）**
- 提取：用**同一训练任务的对比轨迹对**（τ+, τ−），满足 R(τ+) > R(τ−)；找到两条轨迹分叉的时间步，把共同前缀总结成「上下文」，再让 LLM 对照这一上下文比较两条轨迹，写出指南（§3.2）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 格式：条件式指南，例如「When on the Reddit main page, if you want to navigate to a specific forum, you should click…」；以上下文为字典键、指南列表为值，近重复的上下文由 LLM 合并 — [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 应用：每步先把当前轨迹映射到一个上下文；如果字典里有这个上下文，由 LLM 从中选 top-k 条指南（附录配置里 k=2）加入动作提示（§3.3、算法 2）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 结果（表 1）：ALFWorld 成功率 ReAct 54.5% / ExpeL 59.0% / AutoGuide 79.1%；WebShop 成功率 30% / 35% / 46%；WebArena 8.0% / 21.8% / 47.1% — [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 作者认为 ExpeL「不生成上下文相关的指南」，每一步都给出所有指南，**不相关的指南会干扰智能体**，在 WebArena 上最明显 — [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 消融（表 6，WebShop 成功率）：ReAct 30%；+上下文识别 36%；+指南提取与选择（无上下文）37%；完整 AutoGuide 46%。top-k（表 4）：k=0 30%，k=1 42%，k=2 46%，k=3 47%，**k=5 43%（指南过多反而下降）**。论文清单中注明没有报告误差条 — [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)

**HtT / 「Large Language Models can Learn Rules」（Zhu et al.；arXiv 2310.07064，v1 2023-10-10，v3 2024-12-19）**
- 归纳：对每个训练样本让 LLM 生成规则，用正则提取；**每条规则记录出现次数与答对次数**，覆盖度（coverage）= 被复用的次数，置信度（confidence）= 答对次数 / 出现次数 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 过滤：只保留覆盖度 ≥ k 且置信度 ≥ p 的规则；网格 k∈{1,2,3}、p∈{0.1,…,0.9}；选定值（表 7），例如 CLUTRR 上 k=2，GPT-4 用 p=0.7；CLUTRR 与 Arithmetic 归纳用了 2,000 个训练样本 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 演绎：规则库前置于 CoT（chain-of-thought，思维链）提示，规则组织成层级并用 XML 标签引用，示例教模型检索；作者称每步选项不超过约 10 个时检索效果最好 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 结果：CLUTRR 上 GPT-4 5-shot CoT 50.6→64.3（+13.7）；Arithmetic 上 GPT-4 CoT 57.4→78.4（+21.0）；GPT-3.5 在 Arithmetic 上只 +3.3 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 误差分析：在 100 个样本的人工分析中，**错误规则占 CoT 错误的 65%（CLUTRR）和 81%（base-16）**，作者把大部分收益归于错误规则减少；把规则结论换成随机答案，GPT-4 CoT 在 CLUTRR 上从 50.6 跌到 9.9 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 样本量：性能随训练样本数呈对数线性；CLUTRR 和 base-11 大约要 500 个样本才有显著提升，base-16 和 base-9 大约 100 个 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 局限：要求基础模型在训练样本上有一定正确率（论文用 ≥20%）；规则库必须放得进上下文窗口；GPT-3.5 难以检索到正确规则 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)

**LEAP（In-Context Principle Learning from Mistakes，Zhang et al.；arXiv 2402.05403，ICML 2024）**
- 诱导错误：对每个少样本示例以非零温度采样 15 条零样本 CoT，**此时不给金标**；保留答错的输出，**之后才给出金标**，让模型为每个错误写低层原则（low-level principle，针对单个错误的解释）；高层原则（high-level principle）把它们浓缩成约 5 条要点 — [arXiv HTML](https://arxiv.org/html/2402.05403)
- 低层 vs 高层没有一致的胜者，作者建议在验证集上两种都试 — [arXiv HTML](https://arxiv.org/html/2402.05403)
- 有害情形：HotpotQA 上 Gemini Pro 28.25 → 23.70 / 25.50（两种都下降）；GSM8K 上 Claude-2 84.3 → 82.7 / 83.8；DROP 上 GPT-4-turbo 高层原则 83.40 → 80.00；BBH 42 个任务–模型组合中，有 3 个组合基线同时胜过两种变体（如 Gemini Pro 的 snarks 82.58 → 79.21 / 80.90）；附录表 8 显示部分任务（如 ruin_names）**由对变错的数量多于由错变对** — [arXiv HTML](https://arxiv.org/html/2402.05403)
- 头条收益：GPT-4 在 DROP 上 72.05 → 79.55（低层）— [arXiv HTML](https://arxiv.org/html/2402.05403)

**ACE（Agentic Context Engineering，Zhang et al.；arXiv 2510.04618，v3 2026-03-29）**
- 角色（§3、图 4）：生成器（Generator）产出轨迹，并**标记哪些条目帮了忙、哪些误导了它**；反思器（Reflector）从轨迹中提炼教训，可多轮细化；整理器（Curator）把教训变成增量条目（delta），由非 LLM 逻辑合并 — [arXiv HTML](https://arxiv.org/html/2510.04618)
- 存储（§3.1）：上下文是逐条的要点（bullet），每条带 ID 与 helpful/harmful 计数；更新是局部的，只改相关条目 — [arXiv HTML](https://arxiv.org/html/2510.04618)
- 增长–精炼（grow-and-refine，§3.2）：新条目追加，旧条目原地更新（如加计数），再用语义嵌入去重 — [arXiv HTML](https://arxiv.org/html/2510.04618)
- 结果（表 1，DeepSeek-V3.1，AppWorld）：ReAct 基线平均 42.4；离线 ACE 有标签 59.4（+17.0），无标签 57.2。金融（表 2）：基线平均 69.1；离线 ACE 有标签 81.9，无标签 77.1；**在线、无标签的 ACE 在 FiNER 上 67.3，低于基线 70.7**；作者称 ACE 与 DC 在没有可靠反馈时都可能退化 — [arXiv HTML](https://arxiv.org/html/2510.04618)
- 消融（表 3）：去掉反思器与多轮（epoch）适应 55.1；去掉多轮适应 56.8；完整 59.4 — [arXiv HTML](https://arxiv.org/html/2510.04618)

**Dynamic Cheatsheet（DC，Suzgun et al.；arXiv 2504.07952，2025-04-10）**
- 给黑盒 LM 一个持久、演化的记忆，**不需要金标或人工反馈**；GPT-4o 在 Game of 24 上 10%→99%（复用了一段 Python 解法）；Claude 在 GPQA-Diamond 上 +9%、MMLU-Pro 上 +8% — [arXiv abs](https://arxiv.org/abs/2504.07952)

**Hypothesis Search（Wang et al.；arXiv 2309.05660，ICLR 2024）**
- 让 LLM 提出多个自然语言假设，实现为 Python 程序，在已观测样例上校验后再用于新输入；用 LLM 总结或人工挑选来缩减假设集；ARC 100 题子集：自动管线 30%，直接提示 17%，人工挑选 33% — [arXiv abs](https://arxiv.org/abs/2309.05660)

**Phenomenal Yet Puzzling（Qiu et al.；arXiv 2310.08559，ICLR 2024）**
- 迭代假设精炼（iterative hypothesis refinement，提出–选择–精炼文本规则）配合任务专用的符号解释器过滤规则效果很好；但 LM 在**规则归纳与规则应用之间存在明显落差**，常常提出自己并不能正确应用的规则 — [arXiv abs](https://arxiv.org/abs/2310.08559)

**Agent Workflow Memory（AWM，Wang, Mao, Fried, Neubig；arXiv 2409.07429，ICML 2025）**
- 归纳常用例程（workflow，可复用的多步操作模板），并**选择性地**提供给智能体；在 Mind2Web 和 WebArena 上相对成功率分别提升 24.6% 和 51.1%；随训练–测试分布差距增大，比基线高 8.9–14.0 个绝对点 — [PMLR](https://proceedings.mlr.press/v267/wang25bx.html)、[arXiv](https://arxiv.org/abs/2409.07429v1)

**CLIN（Majumder et al.；arXiv 2310.10134，2023-10-16）**
- 持久文本记忆基于「因果抽象」（causal abstractions），而不是笼统的「有用提示」，每次试验后更新；在 ScienceWorld 同任务重复试验中比 Reflexion 高 23 个绝对点；在新环境、新任务上零样本分别 +4、+13 — [arXiv abs](https://arxiv.org/abs/2310.10134)

**GEPA（Agrawal et al.；arXiv 2507.19457，ICLR 2026 oral）**
- 对轨迹做反思式诊断并提出提示词更新，从自身尝试的帕累托前沿（Pareto frontier，在不同样本子集上各自最优、互不支配的候选集合）中组合互补的教训；比 GRPO 平均高约 6%、rollout 最多少 35 倍；比 MIPROv2 高 10% 以上 — [arXiv abs](https://arxiv.org/abs/2507.19457)

### Inferences
- 规则「应用位置」的证据倾向条件化：AutoGuide 的条件指南明显优于 ExpeL 的全局洞见（表 1），而且 k=5 比 k=2/3 差（表 4），说明注入的指南越多、越不相关就越干扰。不过 AutoGuide 中两者还有其他差异，**并不是**一个纯粹的「静态 vs 条件」受控对照。
- 过滤机制的共性：ExpeL 的投票计数、HtT 的覆盖度+置信度、ACE 的 helpful/harmful 计数，本质上都是「这条规则在多少样本上被用到、用到时对了多少」。我们的「support ≥10」只统计**错误**中有多少条支持该规则，没有统计规则在本来正确的样本上触发时的代价。
- 关于 Self-Discover 和 Instruction Induction，本轮没有抓取原文，下面不引用它们的数字。

### Gaps
- Reflexion、Self-Discover、Instruction Induction（Honovich et al.）的具体数字本轮没有核对原文，故不引用。
- DC 的两个变体（DC-Cu 累积式、DC-RS 检索合成式）的区别与退化情形，摘要页没有给出；ACE 论文 §2.2 把「上下文坍缩」的例子归到 DC。
- AWM 中「NL 描述 vs 带 HTML 状态」的对比只在二手摘要中出现，未经核实。

## Q3. 专题证据：成功+失败 vs 只用失败、对比对、规则冲突与过度泛化、上下文坍缩/简短偏置、条件检索 vs 静态插入、看金标的事后合理化

### Takeaway
(1) 「只用失败」并非总是更差：Trace2Skill 在数学上 +Error 最稳；但所有表现好的方法都**用成功样本来检验或约束规则**（ExpeL 对比对、AutoGuide 对比对、HtT 置信度）。(2) 每条规则都可能把正确样本变错（LEAP 表 8、AutoGuide 中 k=5 下降、SkillGen 训练涨测试跌）。(3) 让 LLM 整体重写或合并上下文会坍缩、丢细节（ACE §2.2）。(4) 给分析器看金标、让它一次调用写解释，有较强证据会产生不忠实的根因（Trace2Skill 的 57% vs 14% 审计；Turpin 2023；ExpeL 中加反思反而变差）。

### Cited Findings
- **成功+失败 vs 只用失败**：Trace2Skill 表 2 中数学任务 +Error 是最稳定的设置，而电子表格任务的最高绝对分来自 +Combined（表 1、表 5 中 69.83 vs +Error 65.83）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- ExpeL 同时用失败–成功对比和成功列表；只从初始少样本示例提取的洞见没有优势（图 6）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- **对比对**：AutoGuide 用分叉点之前的共同前缀定义「上下文」，分叉之后的差异给出指南；单加指南提取（无上下文）只有 37%，加上上下文为 46%（表 6，WebShop）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- **规则冲突 / 过度泛化 / 翻转**：LEAP 附录表 8 显示部分任务由对变错多于由错变对；42 个 BBH 组合中有 3 个两种变体都输给基线 — [arXiv HTML](https://arxiv.org/html/2402.05403)
- 注入的指南更多反而更差：AutoGuide 表 4 中 k=5（43%）< k=3（47%）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 训练集涨、测试集跌：SkillGen 训练切片 52.5，测试 27.5（Trace2Skill 附录 G 图 7）；skill-creator 在 122B/122B Deepening 上 48.33→27.33（表 14）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 全量聚合带进与补丁无关的回退，贪心选择停滞；用 32 题验证集做 BO 选择后 65.83→69.83（§4.3、表 6）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- **简短偏置**（brevity bias，优化过程倾向于收敛到短而泛的指令、丢掉领域细节）和**上下文坍缩**（context collapse，LLM 整体重写累积上下文时把它压缩成信息量更少的摘要）：AppWorld 上第 60 步上下文 18,282 tokens、准确率 66.7；下一步被重写成 122 tokens，准确率跌到 57.1，低于不做适应的基线 63.7（ACE §2.2、图 2）— [arXiv HTML](https://arxiv.org/html/2510.04618)
- ACE 的对策：用条目级增量更新代替整体重写，用 helpful/harmful 计数打分，用嵌入去重（§3.1–3.2）— [arXiv HTML](https://arxiv.org/html/2510.04618)
- **反馈不可靠时会退化**：在线、无标签的 ACE 在 FiNER 上 67.3 < 基线 70.7（表 2）— [arXiv HTML](https://arxiv.org/html/2510.04618)
- **条件检索 vs 静态插入**：AutoGuide 优于 ExpeL，作者归因于 ExpeL 每步都给全部指南、不相关指南造成干扰（表 1）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)。反方证据：Trace2Skill 表 5 中整体技能（69.83）优于检索式记忆 ReasoningBank（56.00）— [arXiv HTML](https://arxiv.org/html/2603.25158)。注意后者比较的是「整合后的技能 vs 检索原始单条经验」，不是「条件触发的规则 vs 无条件规则」。
- HtT 通过 XML 层级让模型**在演绎时自己检索**相关规则，作者称每步选项不超过约 10 个时效果最好 — [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- **事后合理化 / 不忠实**：Trace2Skill 33 例审计中，单次调用分析器误判根因 57%，智能体式 14%；原管线丢弃无法因果解释的失败（§2.3、附录 C.1/D）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- Turpin et al.（NeurIPS 2023，arXiv 2305.04388）：CoT 解释会「系统性地歪曲模型预测的真实原因」；被诱导到错误答案时，模型常常为这个答案编造合理化解释；在 13 个 BBH 任务上准确率最多下降 36%（GPT-3.5、Claude 1.0）— [arXiv abs](https://arxiv.org/abs/2305.04388)
- ExpeL：把反思加进洞见提取，HotpotQA 从 39.0 降到 29.0，作者归因于反思中含幻觉（表 3）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)
- LEAP 的设计是**先在不看金标的情况下采样出错误，之后才给金标**写原则 — [arXiv HTML](https://arxiv.org/html/2402.05403)
- **归纳–应用落差**：Qiu et al. 发现 LM 常提出自己无法正确应用的规则 — [arXiv abs](https://arxiv.org/abs/2310.08559)

### Inferences（对应我们的失效）
- **「拒绝但有残余风险 → 2」翻转 16 条正确的严重度 1 样本**：这是规则触发条件过宽、且从未在成功样本上检验的典型表现。按 HtT 的置信度定义计算，这条规则在 train_evolve 上被触发的样本中有多少答对，就能在上线前发现它的净收益为负。ExpeL / AutoGuide 的对比对（同类场景中 gold=1 判对 vs gold=2 判错）会迫使分析器写出区分两者的条件，而不是只写朝一个方向推的规则。
- **3-vs-4 规则与「敏感数据 → 4」规则冲突、什么都没改变**：这与 Trace2Skill 合并算子里「解决冲突」那一步相对应，而我们的 LLM 合并是在每个混淆簇内部完成的，簇与簇之间没有冲突检查。序数任务中，「推高」和「拉低」两类规则在同一边界上天然对立。
- **Task 1 错误 84/102 是证据阅读错误、只有 15/102 是规则错误**：HtT 的收益主要来自「错误规则」占 65–81% 的任务；而在我们的任务里，规则错误只占约 15%，所以加决策规则的上限本来就很低。Qiu 的「归纳–应用落差」和 Trace2Skill 学到的「回读验证」类 SoP 都提示：**流程型指令**（先逐项抽取证据，再打分）比**结论型规则**（遇到 X 就打 N 分）更适合处理阅读错误。这是推断，没有在分类任务上直接验证过的文献。
- **Task 2b 在 train_val 上提升、在 dev 上不提升（规则把 Authorization 与 Scope 的错误互换）**：符合 SkillGen 式的训练–测试回退；train_val 只有 107 条，按场景组拆分后，「提升」可能来自少数场景组。一对互斥标签之间的规则往往只是把边界整体平移，而不是让边界变得更准。
- **看金标的单次分析器**：Turpin 和 Trace2Skill 审计都支持这样的担忧：分析器会为金标编造一个说得通的理由，而不是找出模型真实的出错原因。按 LEAP 的做法，可以先让分析器在**不看金标**的情况下复查证据，再揭示金标；或者要求分析器给出可验证的证据片段（引用原文中的 span），无法给出时就丢弃这条失败（同 Trace2Skill §2.3）。
- **合并簇时的坍缩**：把一个支持度 ≥10 的簇合并成一条规则，就是 ACE 所说的简短偏置——反例和边界条件在合并中最先被丢掉。

### Gaps
- 没有找到在**序数分类 / 多标签分类**上直接比较「静态插入 vs 条件检索规则」的受控实验。
- 没有找到量化「分析器看金标 vs 不看金标」对规则质量影响的直接消融（Trace2Skill 比较的是智能体式 vs 单次调用，不是看不看金标）。
- 没有找到专门研究「规则在序数边界上互相冲突」的文献；上面的讨论是推断。

## Q4. 可迁移到约 460 条训练样本分类任务的具体建议

### Takeaway
最可迁移的做法不是更好的合并，而是**按单条规则在保留数据上做「净翻转」验收**、**带条件的触发 + 对比对产生的反例**，以及针对 84% 阅读错误把规则改成**证据抽取流程**；同时承认在 107/143 条的规模上，几个点的差异可能是噪声。

### Cited Findings（建议所依据的证据）
- 以覆盖度 k 与置信度 p 过滤规则（HtT 表 7）；在约 100–500 个样本时出现显著提升（HtT 样本量分析）— [arXiv HTML v3](https://arxiv.org/html/2310.07064v3)
- 用小验证集（32 题）挑选补丁优于全量聚合（Trace2Skill §4.3、表 6、局限性一节）— [arXiv HTML](https://arxiv.org/html/2603.25158)
- 条件化指南 + 少量（k≈2）选择（AutoGuide 表 4、表 6）— [arXiv HTML v2](https://arxiv.org/html/2403.08978v2)
- 投票 / 计数式的洞见维护（ExpeL §4.2；ACE §3.1）— [arXiv HTML v3](https://arxiv.org/html/2308.10144v3)、[arXiv HTML](https://arxiv.org/html/2510.04618)
- 低层 vs 高层原则无一致胜者，需在验证集上选（LEAP）— [arXiv HTML](https://arxiv.org/html/2402.05403)
- 增量编辑而非整体重写（ACE §3.1–3.2，图 2）— [arXiv HTML](https://arxiv.org/html/2510.04618)
- 可复现性：Trace2Skill 用 3 个种子取平均（附录 A）；AutoGuide 未报误差条 — [arXiv HTML](https://arxiv.org/html/2603.25158)、[arXiv HTML v2](https://arxiv.org/html/2403.08978v2)

### Inferences（建议，均为推断，需要实验验证）
1. **单规则消融 + 净翻转验收**：对每条候选规则单独插入，在 train_evolve **全部** 461 条（包括本来正确的样本）上运行，记录 wrong→right 与 right→wrong 两个数；只保留「净翻转 > 0 且 right→wrong 小于某个阈值」的规则，再在 train_val 上确认。这相当于 HtT 的置信度过滤加上 Trace2Skill 的选择性聚合。temp 0 下单次运行的随机性较小，但 deepseek-flash 的 API 不一定完全确定，最好用重复运行估计噪声底线。
2. **对比对提取**：对每个混淆边界（如 gold=1 vs gold=2），把同一场景组里「判对的 gold=1」与「判错的 gold=1→2」配成对交给分析器，要求它写出**能区分这两者**的 TRIGGER 和取自真实正确样本的 COUNTER-EXAMPLE（ExpeL / AutoGuide 的思路）。可以直接避免「拒绝→2」这类单向规则。
3. **条件触发而非静态插入**：规则写成「仅当证据中出现 X 且未出现 Y 时适用」，或者先用一次 LLM 调用（或关键词）判断适用哪些规则，再只注入 ≤2 条（AutoGuide k=2）。在单次调用的设定下，也可以把规则写成「先判断条件是否成立、再应用」的显式两步。
4. **针对 84/102 阅读错误，用流程而非结论规则**：在提示词中加入证据抽取步骤（例如先列出 agent 下一步实际调用的工具与参数、是否已执行、受影响的对象、是否存在拒绝），再基于抽取结果打分；这对应 Trace2Skill 学到的「回读验证」类 SoP，也对应 Qiu 发现的「规则应用」短板。
5. **分析器去合理化**：先让分析器在**不看金标**的情况下重读证据、判断可能出错的位置，再揭示金标（LEAP 的顺序）；要求引用原文 span 作为证据，给不出则丢弃（Trace2Skill §2.3）。可以抽查 20–30 条，人工核对分析器给出的根因，作为 Trace2Skill 那种 33 例审计的小规模复现。
6. **跨簇冲突检查**：合并之后把所有规则放在一起，在序数边界上检查是否存在方向相反的规则（如「→4」与「→3」）；有冲突时给出明确的优先级，或只保留净翻转更好的那一条。
7. **避免合并坍缩**：用条目级增量 + 计数（ACE），保留每条规则的反例；不要让 LLM 把一个簇重写成一句话。
8. **统计上的谨慎**：train_val 107 条、dev 143 条，Task 2b 在 train_val 上的提升可能来自少数场景组；建议报告按场景组的分解结果和自助法（bootstrap，有放回重采样估计置信区间）区间，并按 AGENTS.md 的要求写明 run_id，由 `src/evaluate.py` 复算。
9. **Task 2b 的互斥标签对（Authorization vs Scope）**：与其加方向性规则，不如在提示词中把两者的定义写成对照表并给出取自训练集的对比例子，然后用净翻转验收。

### Gaps
- 以上建议都没有在 AgentRisk 或类似的序数风险打分任务上被文献直接验证过。
- 不清楚 deepseek-flash 在 temp 0 下的运行间方差；需要自行测量。
