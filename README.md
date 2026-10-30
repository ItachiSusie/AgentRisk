# AgentRisk：任务理解与 TODO

更新日期：2026-10-30

本目录用于准备参加 [AgentRisk — SemEval 2027](https://agentrisk-semeval.lovable.app/)。已有的 [HTML slides](slides/10-20-agentrisk-slides.html) 介绍了任务形式和实例；本文记录项目计划，具体实验 instruction 放在 [LLM In-context Learning Solution](docs/llm-in-context-learning-solution.md)。

## 任务的基础理解

给定一段 agent 的交互历史，以及它接下来准备执行的 `proposed_action`，判断这个动作在当前上下文中的风险。历史包括用户请求、推理、工具调用和工具返回；待评估动作也可能是一段自然语言回复。

| 子任务 | 要回答的问题 | 输出 | 主要指标 |
| --- | --- | --- | --- |
| Task 1：Risk Level Estimation | 执行这个动作有多危险？ | 1–5 的风险等级 | MAE，越低越好 |
| Task 2a：Harm Domain Classification | 可能损害什么？ | 1–2 个 harm domain | Mean Jaccard，越高越好 |
| Task 2b：Risk Driver Classification | 什么因素使动作有风险？ | 1–2 个 risk driver | Mean Jaccard，越高越好 |
| Task 3：Policy-Guided Intervention | 按给定 policy 应该如何干预？ | intervention + actionable feedback | F1；具体评测细则待更新 |

核心是**结合历史评估最后一个动作**。例如，历史中出现窃取信息的指令，但最后的动作是拒绝发送信息，就应评估这条拒绝回复本身的风险。Task 3 还取决于 policy：同一个动作在不同 policy 下可能需要不同干预。[任务说明](https://agentrisk-semeval.lovable.app/#tasks)

当前官方数据为 **train 568 条、dev 143 条**，包含 Task 1、2a、2b 的标签。Task 3 尚未公布评测 policy，也没有公开训练用的 gold intervention labels。因此，第一轮全量 dev baseline 覆盖 Task 1、2a、2b；Task 3 等官方材料齐备后接入。[官方数据集说明](https://huggingface.co/datasets/AgentRisk/agentrisk-data-2027#subtasks)

## 三轮实验计划

总体路线：**API 大模型 baseline → traces2skill 提炼 Guardian Skill → 小模型微调与数据扩展 → 根据 dev 和正式规则选择最终系统**。完整实验设计、对照和验收标准见 [三轮实验路线](docs/experiment-roadmap.md)。

| 轮次 | 实验内容 | 核心问题 |
| --- | --- | --- |
| 第一轮 | API zero-shot、few-shot；从 train 轨迹及模型评估记录中提炼 Guardian Skill，再分别加入两种设置 | 提炼的风险判断知识能否稳定改善预测？ |
| 第二轮 | 先仅用官方 train 微调已有模型，再单独研究数据 augmentation 与扩展 | 微调能否接近或超过 API baseline？扩展数据是否带来额外收益？ |
| 第三轮 | 综合 dev 分数、成本、稳定性与正式比赛规则选择系统 | 哪个方案适合最终提交？ |

### 第一轮 A：DeepSeek API 全量 dev baseline


方案名称：**LLM In-context Learning Solution**。使用 `deepseek-flash`，先固定一版 zero-shot instruction，直接跑完整 dev set，建立后续比较的起点。这里的第一版仅通过 prompt 完成预测，不进行模型训练；few-shot 示例作为后续对照。

**分工：Shuai lead 实现、全量推理与评测；我提供 instruction，并参与结果讨论。** 执行细节见 [独立方案文档](docs/llm-in-context-learning-solution.md)，API 接入参考 [DeepSeek 中文文档](https://api-docs.deepseek.com/zh-cn/)。

- [ ] 我：提供并确认第一版任务 instruction、标签定义和输出格式。
- [ ] Shuai：下载官方 train/dev，记录数据版本，确认 dev 样本数量与 ID。
- [ ] Shuai：完成 DeepSeek API 接入，用少量 train 样本检查调用、JSON 解析和标签校验。
- [ ] Shuai：冻结 prompt 和配置，用 `deepseek-flash` 跑完整 dev set，保存预测、原始响应和运行记录。
- [ ] Shuai：计算 Task 1 MAE、Task 2a/2b Mean Jaccard，汇总成功率、token 用量与费用。
- [ ] 共同：检查代表性错误，讨论等级混淆、domain/driver 混淆，以及拒绝动作是否被误判。

完成标准：当前版本 dev 的 **143/143 条均有合法预测**，三个任务的指标可复算，prompt、配置和结果文件完整保留。若官方数据更新，以记录下来的版本和完整样本数为准。

### 第一轮 B：Few-shot 与 traces2skill

- [ ] 从 train 中选取固定 few-shot 示例，与第一版 zero-shot baseline 比较。
- [ ] 根据错误分析调整风险等级说明、上下文理解或多标签选择规则，每次只改一个主要因素。
- [ ] 基于 train 的轨迹、标签和模型评估记录，用 traces2skill 提炼 Agent Risk Guardian Skill；通过按 scenario group 划分的 train 验证折检查规则。
- [ ] 对照四组：zero-shot、few-shot、zero-shot + skill、few-shot + skill，记录 skill 来源、版本和 token 成本。
- [ ] 跟进 Task 3 的 policy、评测脚本及提交格式，补充对应方案。

### 第二轮：微调与数据扩展

- [ ] 选定一个已有的小型指令模型，先仅用官方 train 做监督微调，保留未微调模型对照。
- [ ] 在相同基础模型和评测设置下，对照微调时使用与不使用 Guardian Skill 的效果。
- [ ] 完成原始数据微调后，再研究场景改写、风险对照和新场景扩展；记录来源、审核标签、去重并按场景分组。
- [ ] 对照原始数据微调与加入扩展数据的微调，检查各任务和各风险等级的变化。

### 第三轮：最终选型与提交

- [ ] 复核正式规则：API、模型规模、外部数据、合成数据、提交形式与可复现要求。
- [ ] 综合完整 dev 指标、分组验证结果、费用、延迟和输出稳定性选择最终系统；各子任务可分别选型，前提是规则允许。
- [ ] 冻结模型、prompt、skill、数据和配置版本，按正式格式验证提交文件，并整理系统描述及消融实验。

所有实验分别记录版本与 dev 分数；dev 用于开发反馈，不作为最终泛化性能结论。Few-shot 示例、skill 提炼和扩展数据种子只来自 train；不把 dev 样本或 gold 写入 skill、训练集或生成提示。具体实施见 [三轮实验路线](docs/experiment-roadmap.md)。
