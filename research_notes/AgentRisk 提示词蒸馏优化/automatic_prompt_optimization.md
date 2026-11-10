# 自动提示词优化（Automatic Prompt Optimization / APO，用算法而非人工迭代改写 prompt 以最大化任务指标）方法调研：面向小样本分类 / LLM 评判任务

调研日期：2026-11-09。背景：AgentRisk（SemEval 2027），deepseek-flash、温度 0；Task 1 为有序（ordinal，类别有大小顺序）1–5 分级、指标为平均绝对误差（Mean Absolute Error / MAE）；Task 2a/2b 为多标签（multi-label，每条样本可有多个标签）分类、指标为平均 Jaccard（交集/并集）。train_evolve 461 / train_val 107 / dev 143。

说明：「Cited Findings」只放来源中能找到的内容；「Inferences」是我基于这些内容对本项目的推断，不是论文结论。本次会话中只核对过部分论文的正文；只看过摘要或凭记忆的条目会特别标出。

---

## Q1. 各方法如何生成候选、如何选择/接受候选、数据规模与预算、分类任务上的提升

### Takeaway
主流方法都可拆成「提议器（proposer，由 LLM 生成新 prompt）+ 选择器（selector，决定保留哪个）」两部分。提议器分为三类：无方向重采样（APE/OPRO）、基于错误的「文本梯度」（textual gradient，用自然语言写出的对当前 prompt 的批评，ProTeGi/TextGrad/GEPA/PromptWizard），以及进化式变异/交叉（EvoPrompt/PromptBreeder）。选择器则有小批量（minibatch）门控、bandit/UCB、贝叶斯代理模型和帕累托（Pareto）前沿几种。论文里优化用的训练集一般只有 25–500 条，比我们的 461 条小或相当。

### Cited Findings

**ProTeGi（Prompt Optimization with Textual Gradients，Pryzant et al., EMNLP 2023, arXiv 2305.03495）**
- 机制：在训练集上取一个小批量，收集当前 prompt 答错的样本，让 LLM 写出自然语言「梯度」（指出 prompt 的问题），再朝「梯度的反方向」改写 prompt，然后用蒙特卡洛改写（Monte Carlo paraphrase，同义重写）扩充候选；外层是束搜索（beam search，每轮只保留得分最高的 b 个候选）。— [ProTeGi PDF §2.1–2.2, Alg. 1–4](https://arxiv.org/pdf/2305.03495)
- 默认超参（§3.2 Setup）：小批量 |D_mini|=64，束宽 b=4，6 个优化步；每步每次取 4 个错误样本组成一组，每组生成 m=4 个梯度，每个梯度改写一次，再额外生成 p=2 个蒙特卡洛改写；每个父 prompt 随机保留 8 个后继，然后交给 bandit 选择。生成用温度 1.0，分类推理用温度 0.0；模型为 gpt-3.5-turbo（2023 年 1 月版）。— [ProTeGi PDF §3.2](https://arxiv.org/pdf/2305.03495)
- 数据规模：每个任务随机取 50 条做开发集（development set）、150 条做测试集；结果为 3 次试验的平均。任务是 Jailbreak、Ethos（仇恨言论）、Liar（假新闻）、Sarcasm（阿拉伯语讽刺），均为二分类，指标为 F1。— [ProTeGi PDF §3.1–3.2](https://arxiv.org/pdf/2305.03495)
- 选择器：把束搜索的候选选择看作最佳臂识别（best-arm identification，在多个候选中用尽量少的评估找出最好的一个）问题，比较了 UCB（Upper Confidence Bound，置信上界）、UCB-E、逐次淘汰（Successive Rejects）和逐次减半（Successive Halving）。在每个 prompt 25 次查询的预算下，UCB 的 F1 为 Jailbreak 0.83 / Liar 0.66，SH 为 0.82 / 0.64；在 50 次查询的预算下，UCB 为 0.85 / 0.66，SH 为 0.80 / 0.62。文中结论是 UCB 类方法稳定地好于逐次淘汰类。— [ProTeGi PDF Table 2](https://arxiv.org/pdf/2305.03495)
- 束搜索消融（ablation，去掉某个组件看效果变化）：不迭代时 Jailbreak / Liar / Sarcasm 为 0.80 / 0.63 / 0.87，加上束搜索后为 0.85 / 0.67 / 0.88。— [ProTeGi PDF Table 1](https://arxiv.org/pdf/2305.03495)
- 评估预算从每个候选 12 次增加到 50 次时，ProTeGi 的表现「相对稳定」（Figure 3）。摘要称它最多把初始 prompt 的表现提升 31%。— [ProTeGi PDF §3.4 / Fig. 3](https://arxiv.org/pdf/2305.03495)；[arXiv 摘要](https://arxiv.org/abs/2305.03495)

**OPRO（Optimization by PROmpting，Yang et al., ICLR 2024, arXiv 2309.03409）**
- 机制：元提示（meta-prompt，喂给优化器 LLM 的 prompt）里放入历史上得分最高的 20 条指令，按分数升序排列，另附 3 条训练样例；每步生成 8 条新指令，优化器温度 1.0，打分模型温度 0，默认 200 步。— [OPRO §4.2, §5.1, §5.2.1](https://arxiv.org/html/2309.03409)
- 数据：GSM8K 只用训练集的 3.5% 来优化；BBH 取 20% 的样本优化，其余 80% 用于测试。— [OPRO §4.1](https://arxiv.org/html/2309.03409)
- 摘要报告：相对人工 prompt，GSM8K 最多提升 8%，BBH 最多提升 50%。— [OPRO 摘要](https://arxiv.org/abs/2309.03409)
- 消融（§5.3）：元提示中的样例很关键，但样例数从 3 增加到 10 并不一定更好；文中还比较了每步生成 1/2/4/8/16 条指令的情况。— [OPRO §5.3](https://arxiv.org/html/2309.03409)

**APE（Automatic Prompt Engineer，Zhou et al., 2022, arXiv 2211.01910）** — *本次会话没有核对正文，只凭摘要记忆*
- 机制：让 LLM 根据输入/输出示例反推指令，生成大量候选，按打分筛选后再做蒙特卡洛重采样（没有方向的局部搜索）。ProTeGi 把它当作 "Monte-Carlo (MC)" 基线，并称其为「无方向的蒙特卡洛搜索」（directionless monte carlo search）。— [ProTeGi PDF §3.3](https://arxiv.org/pdf/2305.03495)
- 摘要称在 24/24 个 Instruction Induction 任务和 17/21 个 BIG-Bench 任务上达到或超过人工指令。— [APE arXiv 摘要](https://arxiv.org/abs/2211.01910)（数字凭记忆，需复核）

**MIPRO / MIPROv2（Multi-prompt Instruction PRoposal Optimizer，Opsahl-Ong et al., EMNLP 2024, arXiv 2406.11695；DSPy 实现）**
- 提议：由一个独立的提议器 LLM 写指令，提供给它的「grounding」（背景信息）包括数据集摘要、程序摘要、自举示例（bootstrapped demos，用当前程序跑训练集、只保留得分达到阈值的输出作为示例，即拒绝采样 rejection sampling）、历史指令及其分数，另外随机附加一条「tip」（6 选 1，例如 creative、persona、high_stakes）。— [MIPRO §3.1, §4.3, App. C](https://arxiv.org/html/2406.11695)
- 选择：用 Optuna 的多变量 TPE（Tree-structured Parzen Estimator，一种贝叶斯优化代理模型）对「指令 × 示例集」的组合建模；每个试验（trial）在随机小批量上打分，每隔 S 步把当前最好的候选放到完整集合上评估。— [MIPRO §3.2](https://arxiv.org/html/2406.11695)
- 预算：HotPotQA 和 ScoNe 各 50 次全量评估试验（约 300 次小批量试验）；Iris、Heart Disease、HotPotQA Conditional 各 30 次；HoVer 20 次；每种方法跑 5 次。— [MIPRO §5.2 / App. B](https://arxiv.org/html/2406.11695)
- 数据划分（train/dev/test）：Iris 75/–/75，Heart Disease 120/–/183，ScoNe 500/500/1200，HotPotQA 500/500/2000。— [MIPRO Table 3](https://arxiv.org/html/2406.11695)
- DSPy 实现的默认值：`minibatch_size=35`，`minibatch_full_eval_steps=5`，`max_bootstrapped_demos=4`，`max_labeled_demos=4`，`auto` 默认 `'light'`；把两个 demo 上限都设为 0 就是只优化指令的零样本（zero-shot）模式；小批量大小不能超过验证集大小。— [DSPy MIPROv2 文档](https://dspy.ai/current/api/optimizers/MIPROv2/)
- GEPA 论文实验中，MIPROv2 基线每次提出 18 条指令候选和 18 组自举示例。— [GEPA arXiv 2507.19457 实验设置](https://arxiv.org/html/2507.19457)

**GEPA（Genetic-Pareto，反思式提示进化，Agrawal et al., arXiv 2507.19457，2025-07；后被 ICLR 2026 接收——会议信息未在本次核实）**
- 提议（反思式变异，reflective mutation）：在一个小批量上运行当前候选，收集执行轨迹（trace）、分数和文本反馈（feedback）；按轮询（round-robin）选一个模块，把当前 prompt、轨迹、分数和反馈交给反思 LLM，由它写出新 prompt。元提示要求它推断任务、记下细分领域的事实，并总结可以推广的策略。另有 Merge 操作，在不同谱系（lineage，候选的祖先链）之间做模块级交叉（crossover，把两个候选的部分组合起来）。— [GEPA §3, Alg. 1, App. C, App. D.1](https://arxiv.org/html/2507.19457)
- 接受（两级门控）：新候选先在 D_feedback 的小批量上评估，只有平均分提升，才会在完整的 D_pareto 上评估并加入候选池。最终返回在 D_pareto 上平均分最高的候选。— [GEPA Alg. 1 第 15–21 行](https://arxiv.org/html/2507.19457)
- 帕累托选择（Alg. 2）：对每个训练/验证实例记录所有候选中的最高分；只要在至少一个实例上最好，就保留在前沿上；被严格支配（strictly dominated，在所有实例上都不如另一个候选）的候选被剪掉；按候选「领先的实例数」成比例抽样作为下一个父代。— [GEPA §3.1, Alg. 2](https://arxiv.org/html/2507.19457)
- 小批量大小：所有 GEPA 实验都用 3。Merge 每次运行最多调用 5 次。rollout 预算与 MIPROv2 对齐，差距不超过 10.15%。— [GEPA 实验设置 / 附录](https://arxiv.org/html/2507.19457)
- 数据划分（train/val/test）：HotpotQA 150/300/300，IFBench 150/300/294，HoVer 150/300/300，PUPA 111/111/221，AIME 45/45/30×5。训练集作为 D_feedback，验证集作为 D_pareto。— [GEPA §4 / 附录](https://arxiv.org/html/2507.19457)
- 预算（Table 1，Qwen3-8B）：GEPA(+Merge) 的总 rollout 数为 HotpotQA 6871、IFBench 3593、HoVer 7051、PUPA 2426，平均 3936；GRPO 每个基准都是 24,000。IFBench 上只用 678 次 rollout 就找到了 38.61% 的 prompt。— [GEPA Table 1](https://arxiv.org/html/2507.19457)
- 结果：Qwen3-8B 上的平均分为 GEPA 54.85（+9.62）、GRPO 48.91（+3.68）、MIPROv2 47.84（+2.61）（Table 1）；GPT-4.1-mini 上为 GEPA+Merge 66.36（+13.33）、GEPA 65.22（+12.19）、MIPROv2 58.67（+5.64）（Table 2）。注意：这些基准是多跳问答、指令遵循、隐私改写和数学，**不是分类任务**。— [GEPA Table 1–2](https://arxiv.org/html/2507.19457)
- 选择策略消融（Table 3，Qwen3-8B，4 个任务平均）：Pareto 61.28（+12.44），只取当前最优（SelectBestCandidate）54.89（+6.05），BeamSearch 53.95（+5.11）。— [GEPA Table 3](https://arxiv.org/html/2507.19457)
- DSPy 接口：metric 返回 `dspy.Prediction(score=..., feedback=...)`；如果不给 feedback，就退化为只含分数的文本。`valset` 可选；小批量从 trainset 抽取，通过小批量门控的候选再在 valset（Pareto 集）上评估。— [DSPy GEPA 文档](https://dspy.ai/current/api/optimizers/GEPA/overview/)

**PromptWizard（Agarwal et al., Microsoft, arXiv 2405.18369）**
- 机制：先按「思考风格」（thinking styles）变异出多个指令，在小批量上打分，对最好的一个做批判（critique），再综合（synthesize）出改进版；示例与指令交替执行「批判—综合」，最多 5 轮；还会为示例生成推理链（CoT）并检查其连贯性，并在 prompt 中加入任务意图和专家角色。— [PromptWizard §3.1–3.4](https://arxiv.org/html/2405.18369)
- 超参（Table 11）：mutate-refine 3 轮，mutate 3 轮，风格变体 3 个，打分小批量大小 5，最多 6 个示例，最多 5 次顺序迭代，打分阈值 0.5。— [PromptWizard Table 11](https://arxiv.org/html/2405.18369)
- 成本（Table 4，作者自估）：每个任务约 69 次调用、约 $0.05；对比 Instinct/InstructZero 约 1,730 次、EvoPrompt 约 5,000 次、PromptBreeder 约 18,600 次。— [PromptWizard Table 4 / §5.2](https://arxiv.org/html/2405.18369)
- 结果：BBII 零样本（GPT-3.5）19 个任务中 13 个最优（Table 1）；GSM8k 90 vs Instinct 74.5（Table 2）；BBH 23 个任务平均 88.1 vs EvoPrompt 75.03 vs APE 71.85（Table 3）。— [PromptWizard Tables 1–3](https://arxiv.org/html/2405.18369)
- 消融（Table 8，GSM8k / Ethos 分类）：完整方法 95.4 / 89.4；去掉批判—综合 90.9 / 86.9；去掉变异与打分 95.2 / 87.1；去掉推理链 45.9 / 87.6。也就是说，在分类任务 Ethos 上，各组件的贡献只有 1–2.5 个点。— [PromptWizard Table 8](https://arxiv.org/html/2405.18369)

**EvoPrompt（Guo et al., ICLR 2024, arXiv 2309.08532）/ PromptBreeder（Fernando et al., DeepMind, arXiv 2309.16797）** — *本次没有核对正文*
- EvoPrompt 用遗传算法（GA）或差分进化（Differential Evolution / DE）的算子，让 LLM 对 prompt 种群做交叉和变异；摘要称覆盖 31 个数据集，BBH 上最多提升 25%。— [EvoPrompt arXiv 摘要](https://arxiv.org/abs/2309.08532)（数字凭记忆，需复核）
- PromptBreeder 是自指（self-referential）进化：不仅进化任务 prompt，也进化「变异 prompt」本身；摘要提到它在仇恨言论分类（ETHOS）上进化出复杂的 prompt。— [PromptBreeder arXiv 摘要](https://arxiv.org/abs/2309.16797)
- 调用成本：据 PromptWizard 的估计，EvoPrompt 约 5,000 次、PromptBreeder 约 18,600 次。— [PromptWizard Table 4](https://arxiv.org/html/2405.18369)

**TextGrad（Yuksekgonul et al., arXiv 2406.07496；后发表于 Nature 2025——未在本次核实）** — *本次没有核对正文*
- 把「文本梯度」推广到任意计算图：可以通过 LLM 反馈对变量（包括 prompt）做反向传播；prompt 优化实验在 BBH 类推理任务和 GSM8k 上。具体数字未核实，见 Gaps。— [TextGrad arXiv](https://arxiv.org/abs/2406.07496)

**SAMMO（Symbolic Prompt Program Search，Schnabel & Neville, Microsoft, arXiv 2404.02319）** — *只看了摘要*
- 把 prompt 表示成符号化的「prompt 程序」（由多个结构化部分组成，例如指令段、示例段、格式段），在这个结构上做一组变换并搜索；评估任务为指令调优、RAG 流水线调优和 prompt 压缩。摘要没有给出具体数字。— [SAMMO arXiv 摘要](https://arxiv.org/abs/2404.02319)；代码 [github.com/microsoft/sammo](https://github.com/microsoft/sammo)

**2025–2026 的后续工作**
- Contrastive Reflection for Iterative Prompt Optimization（Koh et al., arXiv 2606.30840，2026-06-29，Agent4IR @ KDD 2026）：从轨迹或评分理由中找出「以错误为锚的行为切片」（error-anchored behavioral slice，一组同类型的错误样本），并加入同一区域内附近的**正确**样本作对照，由 Teacher LLM 提出有针对性的修改；只有验证集表现提升才接受，并可选做回归检查。HotpotQA 留出集 EM 从 51.4% 提升到 60.4%；轻量的只优化指令对比中，MIPROv2 为 59.4%，GEPA 为 57.0%。只用失败样本或随机证据的变体提升更少，并且「打坏更多原本正确的样本」。— [arXiv 2606.30840 摘要](https://arxiv.org/abs/2606.30840)
- Learning from Contrastive Prompts（LCP，Li et al., arXiv 2409.15199 → ACL Findings 2026）：让 LLM 对比好的和差的 prompt 候选来总结改进方向；在 BBH 上报告对现有方法的胜率超过 76%。— [ACL Findings 2026.findings-acl.9](https://aclanthology.org/2026.findings-acl.9/)；[arXiv 2409.15199](https://arxiv.org/html/2409.15199v1)
- Hyperband-based Bayesian Optimization for Black-box Prompt Selection（arXiv 2412.07820）：在固定候选池里选 prompt 时，用多保真（multi-fidelity，先用少量样本粗筛、再对剩下的候选加大评估量）的 Hyperband 来节省评估。— [arXiv 2412.07820](https://arxiv.org/pdf/2412.07820)
- 面向 LLM 评判（LLM-as-judge，用 LLM 给输出打分或分类）的 prompt 优化：Zhen et al., ACL 2025 Industry 用主动采样（active sampling，在不确定性和多样性之间做凸优化来挑选样本）做评判 prompt 的 APO。— [ACL 2025 industry.67](https://aclanthology.org/2025.acl-industry.67)

### Inferences
- 在我们的预算下（deepseek-flash 很便宜，461 条训练），评估成本主要来自对 train_val 的反复全量打分，而不是提议。GEPA 论文本身也说「大部分 rollout 预算花在验证上」（见 Q3）。
- 我们之前的 TRIGGER→RULE 蒸馏，相当于「ProTeGi 式错误梯度 + 无门控的直接插入」：既没有束搜索和多候选比较，也没有小批量或验证集接受检查。这正是各论文都会加上的那一环。

### Gaps
- APE、EvoPrompt、PromptBreeder、TextGrad、SAMMO 的表格级数字本次没有核对正文，只到摘要层面；正式写报告前，应补读这些论文的实验章节。
- GEPA 被 ICLR 2026 接收、TextGrad 发表于 Nature，这两条发表信息本次未核实。

---

## Q2. 哪些方法同时使用正确和错误样本（或对比对）？哪些联合优化指令与示例？消融结果如何？

### Takeaway
ProTeGi 和 TextGrad 默认只看错误样本；PromptWizard 和 Contrastive Reflection 明确把正确样本也放进提议过程，其中 Contrastive Reflection 报告「只看失败」会打坏更多原本正确的样本，这与我们的过度校正现象吻合。MIPRO 的消融显示：在大多数任务上，只优化示例 > 只优化指令；联合优化通常最好；指令优化主要在「示例里推断不出来的条件规则」上起作用。

### Cited Findings
- ProTeGi 的梯度只基于错误样本：每步取 4 个错误组成一组来生成梯度。— [ProTeGi PDF §3.2](https://arxiv.org/pdf/2305.03495)
- PromptWizard 随机取 25 个训练样本，按当前 prompt 是否答对分组：用失败样本指导改进，失败太少时用随机正确样本补齐；示例与指令交替优化，并生成推理链。— [PromptWizard §3.2–3.3](https://arxiv.org/html/2405.18369)
- GEPA 的反思输入是小批量（大小 3）上的输入、输出、分数和反馈，不区分对错；样本由小批量随机抽取。— [GEPA App. C / 设置](https://arxiv.org/html/2507.19457)
- Contrastive Reflection：错误切片加上同一区域附近的成功样本；只用失败或随机证据的变体增益更小，并且「breaks more previously correct examples」。— [arXiv 2606.30840](https://arxiv.org/abs/2606.30840)
- LCP：对比好的和差的 prompt（而不是样本）。— [arXiv 2409.15199](https://arxiv.org/html/2409.15199v1)
- MIPRO 联合优化的消融（Table 2，测试集，5 次平均）：

  | 方法 | ScoNe | HotPotQA | HoVer | HotPotQA Cond. | Iris | Iris-Typo | Heart Disease |
  |---|---|---|---|---|---|---|---|
  | 0-Shot MIPRO（只优化指令） | 71.5 | 36.8 | 33.1 | 14.6 | 36.4 | 56.7 | 25.8 |
  | Bootstrap RS（只优化示例） | 75.4 | 45.8 | 37.2 | 10.4 | 94.1 | 58.7 | 79.2 |
  | MIPRO（联合） | 79.4 | 46.4 | 39.0 | 23.3 | 88.6 | 68.7 | 74.2 |

  — [MIPRO Table 2](https://arxiv.org/html/2406.11695)
- MIPRO §6 的教训：Lesson 1「把自举示例作为 few-shot 来优化，是取得最佳表现的关键」；Lesson 2 联合优化通常最好（例外为 HotPotQA、Heart Disease、无拼写错误的 Iris）；Lesson 3 指令优化对「LM 无法从少量示例推断出的条件规则」最重要（依据是 Iris-Typo 和 HotPotQA Conditional）；Lesson 4 grounding 在 HotPotQA/HoVer 上有帮助，在 ScoNe 上反而有害。— [MIPRO §6](https://arxiv.org/html/2406.11695)
- 在 Heart Disease 分类上只优化指令效果差，论文将其归因于初始指令没有写明分类标准。— [MIPRO §5–6](https://arxiv.org/html/2406.11695)
- 相反的证据：GEPA 声称反思式进化的指令「泛化差距更小」，好于 few-shot 方法，并把这与 Wan et al. (2024)「示例泛化更好」的结论对立，作者猜测原因是新模型的指令遵循能力更强。— [GEPA Observation 2 / App. H Fig. 16](https://arxiv.org/html/2507.19457)

### Inferences
- 对 Task 1（有序 1–5），刻度的边界本身就是一种「条件规则」（例如什么情况算 3、什么情况算 4），属于 MIPRO Lesson 3 所说的、指令优化能起作用的场景。但具体刻度位置靠少量带标签的示例往往更容易传达，所以值得做一个「指令 + 每个分数段 1 个示例」的对比实验。
- 我们的规则蒸馏只把错误样本喂给 LLM，与 Contrastive Reflection 中「failure-only」变体的设定一致；它报告的副作用（打坏原本正确的样本）可以直接解释 Task 1 的过度校正。建议每个 TRIGGER 都配上「看起来相似但标签正确、不应触发」的反例。
- deepseek-flash 的 few-shot 示例很占上下文（每条轨迹较长），这是 MIPRO 结论迁移到我们任务时的一个约束。

### Gaps
- Wan et al. (2024)（示例 vs 指令泛化）的原文本次没有读到，具体数字未知。
- 没有找到在多标签或有序目标上专门做「指令 vs 示例」消融的论文。

---

## Q3. 过拟合与迁移到留出测试集的证据、推荐验证集规模、已知失败模式

### Takeaway
过拟合有明确记录：OPRO 的训练准确率常比测试高 5–20%；ProTeGi 在约 3 步时测试分就达到峰值；MIPRO 的 Iris 训练 98.4、测试 88.6；一篇独立博客发现 GEPA 的 Pareto 集分数与测试分几乎不相关。主要对策是：独立的验证集（不参与提议和选择）、早停、限制 prompt 长度，以及做回归检查。

### Cited Findings
- OPRO §5.4：训练准确率常比测试准确率高 5%–20%（Tables 7、10）；默认不使用验证集；建议「留出更大的训练集，并用更少的步数优化（早停）」。— [OPRO §5.4](https://arxiv.org/html/2309.03409)
- ProTeGi：「过程可能在仅仅几步之后就开始过拟合训练数据，或陷入局部最优；所有数据集都在大约 3 步时达到峰值」；Jailbreak 和 Liar 提升快并能保持，Ethos 和 Sarcasm 则相对平稳。— [ProTeGi PDF §3.4, Fig. 4](https://arxiv.org/pdf/2305.03495)
- MIPRO 的 Iris：训练 98.4 vs 测试 88.6（测试集只有 75 条）。— [MIPRO Table 2](https://arxiv.org/html/2406.11695)（差距是从表中读出的，论文没有专门讨论过拟合）
- GEPA：「大部分 rollout 预算花在验证上」，作者把更小或动态选择的验证子集列为未来工作；反思式指令的泛化差距（测试分减去最佳验证分）比 few-shot 小，但正文没有给出 Fig. 16 的具体数值。— [GEPA Observation 1–2, App. H](https://arxiv.org/html/2507.19457)
- 「GEPA is Better Than You Think」（Uğur Ali Kaplan，博客，2026-03-23；非同行评审）：AIME 实验中 feedback 集 45 / Pareto 集 45 / 独立验证集 30，模型 GPT-5-mini，300 次迭代，小批量 5。各集合分数之间的相关性：验证↔测试 Pearson 0.811 / Spearman 0.870；Pareto↔测试 0.155 / 0.272。按 Pareto 集选出的候选 49 测试分为 0.767，按验证集选出的候选 1 为 0.867。把验证样本并入 Pareto 集并不能替代独立验证集。作者在更早的实验中（Qwen3-4B，GPQA）把 Pareto 集分数从约 48% 提到近 80%，测试分却基本不变。— [博客](https://personal-blog-73f.pages.dev/blog/gepa-is-better-than-you-think/)
- 同一博客称，GEPA/DSPy 作者曾建议把所有数据都放进 Pareto 集，理由是选择集越多样越能起正则化作用；博主不同意。— [博客](https://personal-blog-73f.pages.dev/blog/gepa-is-better-than-you-think/)
- Hyperband prompt 选择论文：验证集样本太少时，验证集上最优的 prompt 未必在测试集上最优，验证误差持续下降不代表测试表现也在提升。— [arXiv 2412.07820](https://arxiv.org/pdf/2412.07820)（来自检索摘要，未读正文）
- arXiv 2608.00243（2026）：24 条的开发集无法区分两个 prompt 流水线，120 条的留出集可以。— [arXiv 2608.00243](https://arxiv.org/pdf/2608.00243)（来自检索摘要，未读正文）
- Dropbox Dash 相关性评判器（1–5 分制，2026，经 ZenML 二手转述）：优化器曾把样本特有的关键词、用户名、文档原句抄进 prompt，导致过拟合；也曾把评分刻度从 1–5 改成 1–3。团队因此加了约束：禁止复制样本特有内容，并固定任务定义。对 o3 生产版则避免整体重写，因为小的措辞变化会影响边缘案例。— [ZenML 转述 Dropbox 博客](https://www.zenml.io/llmops-database/systematic-prompt-optimization-for-production-relevance-judges-using-dspy)
- prompt 长度：GEPA 的 prompt 比 MIPROv2 的最多短 9.2 倍，Fig. 17 显示较短的 prompt 与更高的表现相关。— [GEPA Observation 4, Fig. 17–18](https://arxiv.org/html/2507.19457)
- 回归：Contrastive Reflection 把「回归检查」作为可选的接受条件，并指出只用失败样本会打坏更多原本正确的样本。— [arXiv 2606.30840](https://arxiv.org/abs/2606.30840)

### Inferences
- 我们的 Task 2b「train_val 有提升、dev 没有」与 OPRO 和 GEPA 博客描述的情况相同：train_val（107 条）一旦被反复用来选 prompt，就从「验证集」变成了「训练集的一部分」。建议把 train_val 只用于少量最终比较，或者在 train_evolve 内部再按场景组切出一个选择集。
- 107 条验证集上，MAE 或 Jaccard 的标准误不小。按经验，一个 1–5 分制、MAE≈0.8 的任务，在 n=107 时 MAE 的标准误大约是 0.06–0.08（这是推断，需要用我们自己的预测做 bootstrap 复算）。所以小于约 0.1 的差异不应作为接受依据；应该用配对 bootstrap（paired bootstrap，在同一批样本上重采样两个 prompt 的差值）来判断。
- 对有序任务，「规则插入」最容易造成单向漂移（整体偏高或偏低）。接受检查时，除了总 MAE，还应同时检查各分数段的平均偏差（mean signed error，带符号的平均误差，用来看整体是偏高还是偏低）和混淆矩阵。

### Gaps
- 没有找到在 ~500 条规模上给出「推荐验证集大小」的系统研究；现有证据是零散的（24 vs 120、GEPA 用 111–300 条）。
- GEPA Fig. 16 的泛化差距数值没有拿到。

---

## Q4. 实用配方：小批量大小、迭代次数、接受准则、控制 prompt 长度

### Takeaway
论文里的默认值：小批量 3（GEPA）/ 5（PromptWizard）/ 35（MIPROv2）/ 64（ProTeGi）；迭代次数 ProTeGi 6 步（约 3 步达到峰值）、OPRO 200 步；接受机制是「小批量提升 → 全验证集确认」的两级门控，或 UCB bandit；控制长度靠限制编辑幅度、做结构化或压缩类变换（SAMMO），或干脆让短 prompt 自然胜出（GEPA）。

### Cited Findings
- 小批量与迭代：ProTeGi 小批量 64、束宽 4、6 步、每组 4 个错误、4 个梯度、8 个后继（§3.2）；GEPA 小批量 3，预算与 MIPROv2 对齐（每个基准约 1.8k–7k 次 rollout，Table 1）；MIPROv2 默认 `minibatch_size=35`，每 5 步做一次全量评估；PromptWizard 打分小批量 5，最多 5 次迭代，约 69 次调用（Tables 4、11）。— [ProTeGi](https://arxiv.org/pdf/2305.03495)；[GEPA](https://arxiv.org/html/2507.19457)；[DSPy MIPROv2](https://dspy.ai/current/api/optimizers/MIPROv2/)；[PromptWizard](https://arxiv.org/html/2405.18369)
- 接受准则：GEPA 要求在小批量上严格提升，才进入 Pareto 集评估（Alg. 1）；Contrastive Reflection 要求验证集提升，并可选附加回归检查；ProTeGi 用 UCB 在每个候选 25–50 次查询的预算下选择。— 同上，及 [arXiv 2606.30840](https://arxiv.org/abs/2606.30840)
- 最终选择：独立验证集比 Pareto 集更能预测测试表现，分数持平时优先选更早的迭代（博客建议）。— [Kaplan 博客](https://personal-blog-73f.pages.dev/blog/gepa-is-better-than-you-think/)
- 早停：OPRO 建议用更少的步数；ProTeGi 约 3 步达到峰值。— [OPRO §5.4](https://arxiv.org/html/2309.03409)；[ProTeGi Fig. 4](https://arxiv.org/pdf/2305.03495)
- 长度与漂移控制：Dropbox 用局部的指令条目（instruction bullet）选择代替整体重写，并禁止复制样本特有内容。— [ZenML/Dropbox](https://www.zenml.io/llmops-database/systematic-prompt-optimization-for-production-relevance-judges-using-dspy)；SAMMO 的变换集合包含 prompt 压缩。— [SAMMO 摘要](https://arxiv.org/abs/2404.02319)

### Inferences（针对本项目的建议配方，均为推断）
1. 数据切分：train_evolve（461）内部再按场景组切成 feedback 集（约 300 条，用来挑错误和正确样本、生成编辑）和选择集（约 160 条，用于候选间比较 / Pareto）；train_val（107）只在最终少数几个候选间比较一次；dev（143）只报告结果，不参与选择。
2. 提议：每轮从 feedback 集抽 4–8 个同类错误，并配上 4–8 个相似但正确的样本（对比切片），要求 LLM 输出**对现有指令的最小修改**（diff，增删不超过 N 行），而不是追加 TRIGGER→RULE 块。每轮生成 4–8 个候选（参考 ProTeGi 的 m=4 和 OPRO 的每步 8 条）。
3. 接受：两级门控。先在 30–60 条选择集小批量上，用配对比较判断是否提升；再在完整选择集上要求：(a) 主指标提升，并超过 bootstrap 噪声；(b) 原本正确样本的「打坏率」低于阈值（例如 ≤3%）；(c) Task 1 的各分数段带符号偏差不恶化；(d) prompt 长度增量不超过上限。
4. 迭代：3–6 轮，选择集连续 2 轮没有提升就停（依据是 ProTeGi 约 3 步达到峰值和 OPRO 的早停建议）。
5. 预算估算：每次全量评估选择集约 160 次调用，每轮 8 个候选，小批量过滤后约 2–3 个进入全量评估，加上提议调用；6 轮合计约 2–4k 次调用，与 GEPA 单个基准的预算（约 1.8k–7k）同一量级。
6. 输出约束：固定 1–5 刻度定义和标签集合，禁止在指令里出现具体样本的实体名（参考 Dropbox 的约束）。

### Gaps
- 没有论文给出「小批量大小 vs 最终泛化」的系统消融；上述数值是各论文默认值的拼合。

---

## Q5. 有序（ordinal）或多标签目标的专门证据

### Takeaway
几乎找不到 APO 论文在有序回归或多标签 Jaccard 上做过系统实验；主流基准是二分类、多跳问答和数学。最相关的是工业案例（Dropbox 1–5 评判器，用归一化均方误差 NMSE 和带方向的误差反馈），以及一份质疑「直接打 1–5 分」这种测量设计的白皮书。

### Cited Findings
- Dropbox Dash 相关性评判器：1–5 分制，指标为 NMSE（归一化均方误差，0–100，0 表示与人工完全一致），格式错误按完全错误计。对每个分歧样本，反馈中写明分差的大小和方向、人工理由和模型推理。GEPA 把 gpt-oss-120b 的 NMSE 从 8.83 降到 4.86（-45%）；MIPROv2 把 gemma-3-12b 的 NMSE 从 46.88 降到 17.26，格式错误从 358/856 降到 9/856。— [ZenML/Dropbox 2026](https://www.zenml.io/llmops-database/systematic-prompt-optimization-for-production-relevance-judges-using-dspy)（二手转述，原文为 Dropbox 技术博客）
- Microsoft 白皮书（2026-06）：直接让 LLM 给出单个 1–5 分是一种脆弱的测量设计；有序类别可以排序，但相邻类别之间的距离不一定相等。— [Microsoft LLM 1–5 Scoring White Paper](https://microsoft.github.io/mcscatblog/assets/posts/better-llm-scoring/20260626_LLM1-5Scoring_WhitePaper.pdf)（来自检索摘要，未读正文）
- 一份厂商博客（LayerLens）推荐用 Cohen's kappa（一种扣除随机一致后的标注一致性系数）评估有序评分，并声称有 8–20 点提升。这是厂商宣传，没有同行评审。— [LayerLens](https://layerlens.ai/blog/judge-optimization-gepa-llm-evaluation)
- ProTeGi、PromptWizard（Ethos）、MIPRO（Iris、Heart Disease）的分类实验都是单标签任务，指标为 F1 或准确率。— [ProTeGi §3.1](https://arxiv.org/pdf/2305.03495)；[PromptWizard Table 8](https://arxiv.org/html/2405.18369)；[MIPRO Table 3](https://arxiv.org/html/2406.11695)

### Inferences
- 对 Task 1，GEPA 式的文本反馈应该写明「预测 4、真实 2，偏高 2 档，原因……」，即带方向和幅度的反馈（与 Dropbox 做法相同），而不是简单的对/错；metric 直接用 -|y-ŷ|，让部分接近也能得到部分分。
- 对 Task 2a/2b，可以把每条样本的 Jaccard 作为分数，反馈中列出漏报（FN）和误报（FP）的标签。在 Pareto 选择中，多标签任务的每个实例只有一个 Jaccard 值，与 GEPA 的「逐实例最优」机制兼容。
- 在 Task 2b 上，train_val 有提升而 dev 没有，可能也与标签基数（每条 1–2 个标签）有关：规则容易让模型多报标签，从而在某些切分上虚高 Jaccard。验收时应同时看平均预测标签数是否漂移。

### Gaps
- 没有找到在 MAE 或多标签 Jaccard 上评估 APO 的同行评审论文。Dropbox 案例的数据集规模（除 gemma 的 856 条外）和 o3 实验的具体数字均未公开。
