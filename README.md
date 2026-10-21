# AgentRisk：任务理解与 TODO

更新日期：2026-10-21

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

## TODO 计划

### 计划 1：DeepSeek API 全量 dev baseline

方案名称：**LLM In-context Learning Solution**。使用 `deepseek-flash`，先固定一版 zero-shot instruction，直接跑完整 dev set，建立后续比较的起点。这里的第一版仅通过 prompt 完成预测，不进行模型训练；few-shot 示例作为后续对照。

**分工：Shuai lead 实现、全量推理与评测；我提供 instruction，并参与结果讨论。** 执行细节见 [独立方案文档](docs/llm-in-context-learning-solution.md)，API 接入参考 [DeepSeek 中文文档](https://api-docs.deepseek.com/zh-cn/)。

- [ ] 我：提供并确认第一版任务 instruction、标签定义和输出格式。
- [ ] Shuai：下载官方 train/dev，记录数据版本，确认 dev 样本数量与 ID。
- [ ] Shuai：完成 DeepSeek API 接入，用少量 train 样本检查调用、JSON 解析和标签校验。
- [ ] Shuai：冻结 prompt 和配置，用 `deepseek-flash` 跑完整 dev set，保存预测、原始响应和运行记录。
- [ ] Shuai：计算 Task 1 MAE、Task 2a/2b Mean Jaccard，汇总成功率、token 用量与费用。
- [ ] 共同：检查代表性错误，讨论等级混淆、domain/driver 混淆，以及拒绝动作是否被误判。

完成标准：当前版本 dev 的 **143/143 条均有合法预测**，三个任务的指标可复算，prompt、配置和结果文件完整保留。若官方数据更新，以记录下来的版本和完整样本数为准。

### 计划 2：根据 baseline 结果确定改进方向

- [ ] 从 train 中选取固定 few-shot 示例，与第一版 zero-shot baseline 比较。
- [ ] 根据错误分析调整风险等级说明、上下文理解或多标签选择规则，每次只改一个主要因素。
- [ ] 跟进 Task 3 的 policy、评测脚本及提交格式，补充对应方案。

后续实验分别记录版本与 dev 分数；dev 用于开发反馈，不作为最终泛化性能结论。Few-shot 示例只从 train 选择。
