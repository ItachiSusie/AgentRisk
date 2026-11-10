# 有序标签与多标签输出的推理期优化技术（AgentRisk Task 1 / 2a / 2b）

> 调研日期：2026-11-09。各来源的发表/修订日期见对应条目。本文件中「Cited Findings」只记录来源中的原文事实；「Inferences」是本人基于这些事实对 AgentRisk 的推断，没有实验验证。
> 项目背景（来自任务说明，不是外部来源）：deepseek-flash，temperature 0，JSON 输出；Task 1 风险等级 1–5，评测指标 MAE（mean absolute error，平均绝对误差，即预测与金标差值绝对值的平均）；dev 分布 66/8/32/35/2；zero-shot MAE 0.266，BM25 k=20 + rationale MAE 0.154（报告中需要补上 run_id，按 AGENTS.md 要求用 `src/evaluate.py` 复算）。主要错误是金标为 3 的样本有 22/32 被预测成 4。

## 问题 1：有序评分——概率加权期望分、自洽采样聚合、阈值校准、成对比较、rubric/checklist 设计

### Takeaway
支持最充分的做法是概率加权期望分（probability-weighted expected score，按模型给每个分数 token 的概率求加权平均，而不是只取概率最高的 token）。没有 logprobs 时，可以用 n 次采样的经验分布近似。但现有证据报告的是相关系数或一致性，**没有找到直接报告 MAE 下降的表格**。成对比较（pairwise comparative assessment，让模型比较两个样本谁更严重，而不是直接打绝对分）和 checklist 分解在评估类任务上有正面证据，但都有位置偏差，成本也是 O(n) 到 O(n²) 次调用。

### Cited Findings
- **G-Eval 概率加权**：先把分数集合 S={s1..sn} 上的概率归一化，再加权求和作为最终分。GPT-4 当时不返回 token 概率，作者就设 `n=20, temperature=1, top_p=1` 采样 20 次来估计分数分布；GPT-3.5 用 temperature 0（§2 Scoring Function、§3.1 Implementation Details）。 — [G-Eval, Liu et al. 2023, arXiv:2303.16634](https://arxiv.org/abs/2303.16634)
- G-Eval Table 1（SummEval 摘要级相关，取四个维度的平均）：G-Eval-4 的 ρ/τ 为 0.514/0.418；去掉概率（−Probs）为 0.502/0.446；去掉 CoT（chain-of-thought，思维链，先生成推理步骤再打分）为 0.500/0.407。G-Eval-3.5 为 0.401/0.320，−Probs 为 0.346/0.317。 — [G-Eval Table 1](https://arxiv.org/abs/2303.16634)
- G-Eval §4 说明：不用概率时 Kendall-τ 反而更高，原因是直接打整数分会产生大量并列（tie），τ 不计并列对，所以虚高；作者认为这个数字「不能反映真实评估能力」。也就是说，概率加权的主要收益是细化区分度、减少并列，Spearman 只提升约 0.01–0.05。 — [G-Eval §4 "The Effect of Probability Normalization"](https://arxiv.org/abs/2303.16634)
- **TrustJudge**（arXiv 2025-09-26 v2）：采用分布敏感打分（distribution-sensitive scoring）。先在扩展量表（如 100 分）上取各分值概率，softmax 归一化后求期望，再缩放回原量表。在 Llama-3.1-70B 上，分数-比较不一致率从 23.32% 降到 14.89%（Table 1），传递性违背率（NTR, k=5）从 15.22% 降到 4.40%；成对 exact match 从 80.42% 升到 81.61%。各模型规模上的提升为 1.19–6.85 点。 — [TrustJudge, arXiv:2509.21117](https://arxiv.org/html/2509.21117v2)
- 一篇缩小人类与 LLM 评分差距的论文指出：概率型打分在「直接输出分数」时最可靠。如果先写推理再出分，分数 token 的概率会被推理内容带偏（变得过度尖锐）；这种情况下可以改用重复采样来估计分数分布。 — [Bridging Human and LLM Judgments, arXiv:2508.12792](https://arxiv.org/pdf/2508.12792)（仅读到搜索摘要，未核对具体表格）
- LAGER（arXiv:2508.03550）：把各层对候选分数 token 的概率加权聚合后取期望值，认为只取 top-1 token 会丢信息。 — [LAGER, arXiv:2508.03550](https://arxiv.org/html/2508.03550v3)（仅读到摘要级内容）
- 「Quantitative LLM Judges」：在基础 judge 的文本输出和各分值概率之上，再训练一个轻量的第二阶段回归/分类头。据报告，在绝对打分任务上 MSE/MAE 低于基础 judge，低数据量时提升尤其明显。 — [Quantitative LLM Judges 文献综述页](https://www.themoonlight.io/review/quantitative-llm-judges)（二手综述，未核原文表格）
- **成对比较 vs 绝对打分**：Liusie et al.（EACL 2024，v3 2024-02-06）报告，中等规模开源模型（FlanT5、Llama2-chat）上比较式评估（comparative assessment）优于直接打分（prompt scoring），并且常常能和 SOTA 方法竞争。同时 LLM 在成对比较中有明显的位置偏差（positional bias，倾向于选排在前面或后面的那个），作者提出了去偏方法。 — [LLM Comparative Assessment, arXiv:2307.07889](https://arxiv.org/abs/2307.07889)（摘要页，未取到具体数字）
- 作文评分领域：一篇论文用 few-shot 的成对比较判断（comparative judgment, CJ），报告其优于传统 rubric 打分。 — [Is GPT-4 Alone Sufficient for AES? arXiv:2407.05733](https://arxiv.org/html/2407.05733v1)（来自搜索摘要）
- **Checklist 分解**：TICK（NeurIPS 2024）让 LLM 把指令拆成一组 YES/NO 问题，按通过的条目打分。与人类偏好的 exact-match 一致率相比直接打分从 46.4% 升到 52.2%。把生成的 checklist 提供给人类标注员后，WildBench 上标注员之间的一致性从 0.194 升到 0.256。 — [TICK, arXiv:2410.03608](https://arxiv.org/abs/2410.03608)
- 作文评分（ASAP 2.0，GPT-5.1，2026）：在 prompt 中为每个分数等级各给 2 个示例，QWK（quadratic weighted kappa，二次加权 kappa，越远的错误惩罚越重）约提升 26%。 — 来自 [arXiv:2602.04604](https://arxiv.org/pdf/2602.04604) 的搜索摘要，未核对表格
- 2026 年 FSU 作文评分研究：LLM 给分过度自信、高度一致，多数投票（majority vote）在与人类一致性上**没有超过**确定性打分。 — 来自搜索摘要（[aimecon 2026.31](https://aclanthology.org/2026.aimecon-main.31.pdf) 一组结果，未逐条核对出处）

### Inferences
- **期望分 + 取整**：如果 deepseek-flash 能返回分数 token 的 logprobs，可以算 E[s]=Σ p(s)·s 再四舍五入；也可以按 dev 集学习切点（cutpoint，把连续期望分映射到 1–5 的阈值）。MAE 的最优点估计是预测分布的**中位数**，不是均值；所以在分布上取中位数，理论上比取期望后四舍五入更贴合 MAE（这是统计常识推断，没有找到 LLM 论文的直接实证）。
- **没有 logprobs**：可以照搬 G-Eval 的做法，temperature>0 采样 n 次（G-Eval 用 n=20）。用中位数（median）聚合而不是多数票：样本分布为 {3,3,4,4,4} 时，多数票和中位数都给 4；但面对 {2,3,3,4,4} 这样分散的分布，中位数（3）比多数票更稳。成本是调用次数乘以 n。另外，FSU 研究提示：模型本身很自信时，采样分布可能高度集中，聚合收益有限。
- **CoT 与概率的冲突**：当前最佳配置是先写 rationale 再出分，而 2508.12792 提示先推理后出分会让分数概率变尖。所以「rationale + logprob 期望」很可能退化成 argmax；更合适的是「rationale 采样 n 次 → 中位数」。
- **3→4 过预测的直接修法**：用 dev 上的混淆矩阵做事后切点平移，例如期望分 <3.6 时判为 3（具体阈值需要在交叉验证中调）。这比改 prompt 更便宜，但 dev 中 3 和 4 合计只有 67 条，有过拟合风险，应该在 train 的 OOF（out-of-fold，交叉验证中每条样本由未见过它的折来预测）上调。
- **成对比较**：适合「3 和 4 难分」这一处局部决策。可以只在模型预测为 3 或 4 时，与检索到的金标 3、金标 4 锚点样本各做一次比较（交换位置跑两次以消除位置偏差），调用次数增加约 4 倍，但只作用于约一半样本。
- **Checklist**：可以把等级 3 与 4 的区分拆成若干 YES/NO 判据（如「是否已经实际执行了有害动作」「影响是否可逆」），按满足条数映射等级。TICK 的证据来自评估指令遵循，迁移到风险等级是推断。

### Gaps
- 没有找到在 1–5 有序分类上**直接对比「期望分 vs argmax vs 中位数自洽」MAE 的表格**。
- 自洽（self-consistency, Wang et al. 2022，多次采样推理路径后投票）原文针对推理题的多数投票，本次没有核对其表格。没有找到把它用于有序标签、比较中位数与多数票的论文。
- deepseek-flash 是否返回 top-k logprobs，需要查 API 文档实测（本次未调研）。
- CheckEval 以及「decomposed rubric」类论文本次没有检索到可引用的数字。

## 问题 2：分布偏移与标签先验校正（contextual / batch calibration、类别不平衡）

### Takeaway
校准方法（calibration，对模型输出的类别分数做事后修正以去除对某些标签的系统偏好）在 1-shot 分类上能带来约 +6 到 +8 点的平均准确率提升。但这类方法都依赖每个类别的分数或 logprob；只有硬标签时，只能退化为「在验证集上调阈值/混淆矩阵映射」。

### Cited Findings
- **Batch Calibration（BC）**：对一批无标签测试输入的各类分数取平均，作为上下文偏置估计，再从每条样本的分数中减去。不需要标签，也不需要额外 API 调用，但需要每类的 log-prob。 — [Batch Calibration, Zhou et al., arXiv:2309.17249 v3 2024-12-01](https://arxiv.org/html/2309.17249)
- BC Table 2（13 个 NLU 任务平均准确率，1-shot）：PaLM 2-S 的 ICL 为 66.20，用 BC 后 74.41；PC 为 67.65，CC（contextual calibration，用 "N/A" 之类无内容输入估计偏置的方法，Zhao et al. 2021）为 62.39。PaLM 2-L 的 ICL 为 75.16，BC 为 81.09，CC 为 77.83。 — [BC Table 2](https://arxiv.org/html/2309.17249)
- 该文指出 CC 在多句任务（复述、NLI）上失败案例更多。DC（domain-context calibration，用随机领域内 token 序列估计先验）需要多做 20 次前向，是「最不具竞争力」的基线。BC 只需约 10 个无标签样本就能稳定，PC 则需要 >500 个。 — [BC §5](https://arxiv.org/html/2309.17249)
- BC 论文**没有**直接做类别频率变化的实验，只是把多数标签偏置（majority-label bias）列为偏置来源之一。 — [BC](https://arxiv.org/html/2309.17249)
- 关于 demonstration 中的标签不平衡：在二分类任务上，中度不平衡对偏置和性能几乎没有影响，只有极端情况（某类只有 0–1 条示例）才有明显影响。 — [Beyond Performance: Quantifying and Mitigating Label Bias in LLMs, arXiv:2405.02743](https://arxiv.org/pdf/2405.02743)（搜索摘要）
- RCB（arXiv:2502.04037）：在平衡的验证子集上估计条件类别偏置，再据此重加权检索分数。在 100:1 不平衡的四个任务上，测试准确率从约 37.8% 升到 43.3%。 — [arXiv:2502.04037](https://arxiv.org/pdf/2502.04037)（搜索摘要）
- LLM 输出倾向于跟随检索到的 demonstration 的标签，所以检索既能帮忙也可能误导。 — [arXiv:2404.07546](https://arxiv.org/pdf/2404.07546)（搜索摘要）

### Inferences
- 有 logprobs 时，BC 实现最简单：对整个 test 批次每个等级的 log p 取均值并减去，然后再取 argmax 或中位数。它刚好能抵消「整体偏向 4」的系统偏置，而且不需要标签。
- 没有 logprobs 时，等价的做法是在 OOF 上学一个 5×5 的「预测→最终输出」映射，或者调整切点。2 级和 5 级极稀少（dev 分别只有 8 和 2 条），这些稀有类不宜单独调阈值，否则容易过拟合。
- BM25 k=20 检索出来的示例，标签分布会跟随训练先验（1 级占约 47%），可能放大「跟随邻居标签」的效应。对 3 和 4 这一对，可以考虑强制每个检索结果中至少包含若干条 3 和 4 的近邻（标签感知检索）。这是推断，需要 A/B 验证。

### Gaps
- Zhao et al. 2021「Calibrate Before Use」原文的表格数字本次没有直接核对，只通过 BC 论文间接引用了 CC 的结果。
- 没有找到有序标签场景（而非名义分类）下校准效果的专门研究。

## 问题 3：多标签——标签数决策、对比式定义、逐标签二分类 vs 联合输出

### Takeaway
逐标签二分类（dichotomic prompting，对每个标签单独问 yes/no）在**同分布**下与联合 JSON 输出持平；在**零样本 OOD**（out-of-distribution，测试分布与训练分布不同）下明显更好。代价是调用次数乘以标签数，但可以靠前缀缓存（prefix caching，复用相同 prompt 前缀的计算）摊薄。标签数量的校准主要依赖示例选择。没有找到直接报告 Jaccard 的 LLM prompt 对比研究。

### Cited Findings
- Dichotomic prompting（arXiv:2511.03830，2025-11-05）：针对 24 个情感维度、约 1 万条波兰语文本。Table IV（同分布，macro/micro F1）：PLLuM-8B 的 JSON 为 0.812/0.897，dichotomic 为 0.801/0.898；Gemma3-1B 的 JSON 为 0.712/0.846，dichotomic 为 0.722/0.866。 — [Divide, Cache, Conquer](https://arxiv.org/html/2511.03830v1)
- 同文 Table V（OOD，零样本 Gemma3-1B）：JSON 为 0.250/0.300，dichotomic 为 0.363/0.445。但微调后的 dichotomic 在 OOD 上降到 0.286/0.178，泛化反而变差。该文也说明 dichotomic 避免了 JSON 生成和解析错误；把标签放在 prompt 末尾能最大化可缓存前缀。 — [arXiv:2511.03830 Table V](https://arxiv.org/html/2511.03830v1)
- 该文**不报告 Jaccard**，只报告 macro/micro F1。 — [arXiv:2511.03830](https://arxiv.org/html/2511.03830v1)
- 关于标签数量：朴素 prompt 倾向于**少预测**标签数；按多样性选择示例能让模型对「该给几个标签」的预期更准确。 — [Prompting multi-label 论文概述页](https://galsang.github.io/hyu-nlp-publications/papers/prompting-multi-label.html)（二手摘要，未核原文表格）
- 2026 年医疗器械多标签基准指出：性能对标签语义、输出约束、阈值策略都敏感。 — [ACL 2026.acl-long.2148](https://aclanthology.org/2026.acl-long.2148.pdf)（搜索摘要）

### Inferences
- 当前设定是「选 1–2 个标签」，指标是 mean Jaccard。对单金标样本多给一个错误标签，该样本 Jaccard 从 1 降到 0.5；对双金标样本漏掉一个，也是从 1 降到 0.5。因此第二个标签只有在其正确概率 >0.5 时才值得输出（粗略推断：单金标且首选正确时，多给一个错的损失 0.5；双金标时，补上正确的第二个收益 0.5）。可以采用「先输出首选，再对第二标签单独问一次 yes/no」的流程，并用 train 上的 OOF Jaccard 定阈值，或统计「要求置信度为高才输出第二标签」时的命中率。
- 对 Authorization/Consent Failure 与 Scope/Safeguard Failure 这类混淆对，写对比式定义（contrastive boundary description，明确写出「若 X 则选 A 而非 B」的判别句），配一个最小对立例（minimal pair）。这与 TICK 的「拆成 YES/NO」思路一致，也是推断。
- 逐标签二分类在约 11 个标签上需要 11 次调用，DeepSeek API 有上下文缓存时成本可以大幅摊薄。但同分布证据显示它不比联合输出强，所以优先用于高混淆的 2–3 个候选标签（先联合输出 top-3 候选，再逐个二分类），而不是全部标签。

### Gaps
- 没有找到在 LLM prompt 层面直接比较「固定 1 个 / 阈值 / 先一后二」对 Jaccard 影响的论文。
- 层级式 prompt（先领域大类再细类）在多标签 LLM 分类上的实证本次没有检索到。

## 问题 4：检索式 few-shot vs 指令/规则——示例到底在教什么

### Takeaway
Min et al. 2022 显示，在传统规模模型上，示例的作用主要是提供**标签空间、输入分布和格式**，金标正确与否只造成 0–5% 的差异。但长上下文和多示例（many-shot）研究显示：示例数增加到数百、上千时，性能持续上升，并且能覆盖预训练偏置。检索的优势在 1-shot 时很大，到数千 shot 时缩小到约 5 点。我们观察到的「k=20 检索把 MAE 从 0.266 降到 0.154」，与「示例同时校准量表位置和决策边界」相容。

### Cited Findings
- Min et al.（EMNLP 2022）§4.1 / Figure 3：把金标换成随机标签，几乎所有模型性能下降 0–5% 绝对值，分类任务平均下降 2.6%，多选任务 1.7%。 — [Rethinking the Role of Demonstrations, arXiv:2202.12837](https://arxiv.org/abs/2202.12837)（[ACL PDF](https://aclanthology.org/2022.emnlp-main.759.pdf)）
- 同文 §5.1 / Figure 8：把示例输入换成外部语料的 OOD 文本（保留标签空间和格式），性能下降 3–16% 绝对值。§5.2 / Figure 9：direct 模型中，把标签换成随机英文词，比随机标签再差 5–16% 绝对值，说明标签空间本身贡献显著。 — [Min et al. 2022 §5.1–5.2](https://aclanthology.org/2022.emnlp-main.759.pdf)
- 同文 §7 Limitation：个别数据集与模型组合的金标/随机标签差距更大，最极端的是 GPT-J 在 financial_phrasebank 上接近 14% 绝对值。后续工作（Kim et al. 2022）发现取反标签会显著降低分类性能。 — [Min et al. 2022](https://aclanthology.org/2022.emnlp-main.759.pdf)
- Bertsch et al.（arXiv:2405.00200）：在大标签空间分类上，从 10 增加到 1000 个示例，最多提升 50.8 点，五个数据集平均提升 36.8 点（Llama2-80k）。在 Banking-77 上，检索相对随机示例的优势从 1-shot 时的 51.5 点降到 1500-shot 时的 4.9 点。**按标签排序示例**会让 Llama2-32k 在 Clinic-150 上（1169-shot）下降 25.7 点。 — [In-Context Learning with Long-Context Models](https://arxiv.org/html/2405.00200)
- Many-Shot ICL（Agarwal et al.，NeurIPS 2024 Spotlight，v3 2024-10-17）：从 few-shot 到 many-shot 在生成和判别任务上都有显著提升。many-shot 能覆盖预训练偏置，表现与微调相当。推理成本随示例数线性增长。 — [arXiv:2404.11018](https://arxiv.org/abs/2404.11018)（摘要页）
- 作文评分（ASAP，GPT-4）：zero-shot 在部分题目上接近随机，few-shot 有提升，但仍明显落后于微调方法（few-shot GPT-4 的 QWK 为 0.257–0.784，微调 GPT-3.5 为 0.613–0.859）。 — [arXiv:2401.06431](https://arxiv.org/pdf/2401.06431)（搜索摘要）
- 一个 CLEF 2026 系统在 rubric 赛道用了 few-shot 检索，但在简单赛道改用 zero-shot，因为开发期发现 few-shot 示例反而降分。 — [CEUR-WS Vol-4283](https://ceur-ws.org/Vol-4283/paper101.pdf)（搜索摘要）
- 另一项工作（arXiv:2309.10954）报告：通过去重来多样化示例池是负面结果。 — [ICL for Text Classification with Many Labels](https://arxiv.org/pdf/2309.10954)（搜索摘要）

### Inferences
- 对 Task 1，0.266→0.154 的提升很可能来自两部分：(a) 示例把模型的「严重度刻度」对齐到标注者的刻度，属于标签空间/先验校准，与 Min et al. 一致；(b) 近邻示例提供了近似样本的金标，属于「从邻居学习」，与 2404.07546 的「跟随示例标签」一致。区分两者的低成本实验：保留检索到的输入，把标签替换为同分布随机标签。如果 MAE 只轻微变差，说明主要是 (a)。
- 按 Bertsch 的结果，示例数从 20 增加到 100–300 可能还有提升，而且检索带来的优势会随示例数增加而缩小。可以测试「k=100 随机分层样本」与「k=20 BM25」的对比。同时应避免按标签分组排列示例（-25.7 点的反例）。
- 规则/指令 vs 示例：有证据显示示例能覆盖先验（many-shot），而规则主要靠模型自己的理解。对于「标注者特有的刻度」（如 3 和 4 的边界），示例可能比文字规则更有效；对于有明确语义边界的标签对（2a/2b 的混淆对），对比式定义可能更有效。这是推断，需要 A/B 测试。

### Gaps
- Liu et al. 2022（KATE，kNN 选示例）、Wei et al. 2023（大模型能学习翻转标签）的表格本次没有核对，不引用数字。
- 没有找到在有序风险评分任务上直接比较「BM25 / 稠密检索 / 标签均衡检索」的研究。

## 问题 5：低成本集成——prompt 集成、多模型投票、级联

### Takeaway
本次检索到的直接证据很少。现有零散结果显示：在模型本身已经很确定的场景中，多数投票不一定优于确定性单次输出；采样估计分布（G-Eval n=20）的代价是线性增长的调用次数。

### Cited Findings
- G-Eval 用 20 次采样（temperature=1）估计分数分布，成本是 20 倍调用。 — [G-Eval §3.1](https://arxiv.org/abs/2303.16634)
- 2026 年作文评分研究：多数投票没有超过确定性打分。 — 搜索摘要（[aimecon 2026.31](https://aclanthology.org/2026.aimecon-main.31.pdf)）
- Dichotomic prompting 靠前缀缓存降低多次调用的成本；但文本较长、批量较大时，缓存容量会限制加速效果。 — [arXiv:2511.03830](https://arxiv.org/html/2511.03830v1)

### Inferences
- **级联（cascade，先用便宜配置，只有不确定时才升级到贵配置）**：对 Task 1，模型对等级 1 已经 66/66 全对，可以只对首轮预测为 3 或 4 的样本（dev 中约 67 条中的大部分）追加采样、成对比较或换 prompt 投票。这样总成本大约只增加 0.5 倍左右。
- **Prompt 集成**：可以把「BM25 k=20 + rationale」「随机分层 k=50」「checklist 版本」三种 prompt 的输出取中位数（Task 1），或按标签计票并设阈值（Task 2）。需要注意：AGENTS.md 规定已用于正式运行的 prompt 不能修改，新增 prompt 要建新版本号、开新 run。

### Gaps
- 没有找到多模型投票或 prompt 集成在有序 MAE 或多标签 Jaccard 上的直接实证表格。
- 级联的成本-收益曲线需要在本项目数据上自行测量。
