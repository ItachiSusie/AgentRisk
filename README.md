# AgentRisk：任务理解与 TODO

更新日期：2026-10-30

本目录用于准备参加 [AgentRisk — SemEval 2027](https://agentrisk-semeval.lovable.app/)。已有的 [HTML slides](slides/10-20-agentrisk-slides.html) 介绍了任务形式和实例；本文记录项目计划，具体实验 instruction 放在 [LLM In-context Learning Solution](docs/llm-in-context-learning-solution.md)。

## 任务的基础理解

给定一段 agent 的交互历史，以及它接下来准备执行的 `proposed_action`，判断这个动作在当前上下文中的风险。历史包括用户请求、推理、工具调用和工具返回；待评估动作也可能是一段自然语言回复。

| 子任务                              | 要回答的问题                 | 输出                               | 主要指标               |
| ----------------------------------- | ---------------------------- | ---------------------------------- | ---------------------- |
| Task 1：Risk Level Estimation       | 执行这个动作有多危险？       | 1–5 的风险等级                     | MAE，越低越好          |
| Task 2a：Harm Domain Classification | 可能损害什么？               | 1–2 个 harm domain                 | Mean Jaccard，越高越好 |
| Task 2b：Risk Driver Classification | 什么因素使动作有风险？       | 1–2 个 risk driver                 | Mean Jaccard，越高越好 |
| Task 3：Policy-Guided Intervention  | 按给定 policy 应该如何干预？ | intervention + actionable feedback | F1；具体评测细则待更新 |

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

- [x] 我：提供并确认第一版任务 instruction、标签定义和输出格式。
- [x] Shuai：下载官方 train/dev，记录数据版本，确认 dev 样本数量与 ID。
- [x] Shuai：完成 DeepSeek API 接入，用少量 train 样本检查调用、JSON 解析和标签校验。
- [x] Shuai：冻结 prompt 和配置，用 `deepseek-flash` 跑完整 dev set，保存预测、原始响应和运行记录。
- [x] Shuai：计算 Task 1 MAE、Task 2a/2b Mean Jaccard，汇总成功率、token 用量与费用。
- [ ] 共同：检查代表性错误，讨论等级混淆、domain/driver 混淆，以及拒绝动作是否被误判。

完成标准：当前版本 dev 的 **143/143 条均有合法预测**，三个任务的指标可复算，prompt、配置和结果文件完整保留。若官方数据更新，以记录下来的版本和完整样本数为准。

### 第一轮 B：Few-shot 与 traces2skill

后续 Guardian Skill（风险守护技能，即从轨迹中提炼的可复用评估指令）的实施沿用合作者的 [下一轮方案](docs/next-round-plan.md)：使用已生成的 train_evolve / train_val 场景分组切分进行提炼和验证，选定版本后再评估 dev。三轮总体路线见 [实验路线](docs/experiment-roadmap.md)。

- [x] 从 train 中为每条 dev 样本选取少样本示例（few-shot，即在输入中提供已标注样例），完成随机和 BM25 文本检索两种选择方式、k=3/5/10/20 的八组对照；结果见下方当前状态。
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

## 快速开始

### 目录

| 目录       | 内容                                                                         |
| ---------- | ---------------------------------------------------------------------------- |
| `src/`     | 代码：下载数据、推理、评测、生成报告                                         |
| `prompts/` | prompt 文件，每个版本一个文件，如 `zero_shot_v1.txt`；`few_shot_v1.json` 是 few-shot 的消息拼装规范 |
| `data/`    | 数据说明和 `MANIFEST.json`（固定的数据版本）；原始数据在 `data/raw/`，不提交 |
| `results/` | 每次运行的结果，见 [results/README.md](results/README.md)                    |
| `docs/`    | 方案文档                                                                     |
| `slides/`  | 汇报 slides                                                                  |

### 环境准备

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env        # 然后在 .env 里填入自己的 DEEPSEEK_API_KEY
.venv/bin/python src/download_data.py   # 下载 train/dev，并校验与 MANIFEST.json 一致
```

每个新终端运行推理前，先加载密钥：`set -a; . ./.env; set +a`。

### 常用命令

```bash
# 推理：不带 --run-id 会新建一次运行；带上则继续同一次运行（已完成的样本自动跳过）
.venv/bin/python src/run.py --strategy zero-shot --version v1 --limit 20
.venv/bin/python src/run.py --strategy zero-shot --version v1 --run-id <run_id>

# few-shot：--selection random|bm25|bm25-action，--k N（需要 top_n>=N 的选择文件）；random 加 --seed（默认 0）
.venv/bin/python src/select_examples.py --method random --seed 0   # 先生成选择文件（已入库，通常不用重跑）
.venv/bin/python src/run.py --strategy few-shot --selection bm25 --k 3 --version v1 --dry-run   # 不调用 API，检查并估算 token
.venv/bin/python src/run.py --strategy few-shot --selection bm25 --k 3 --version v1 --limit 5
.venv/bin/python src/run.py --strategy few-shot --selection bm25 --k 3 --version v1 --run-id <run_id>

# 查看某条样本实际收到的完整消息（含示例）
.venv/bin/python src/fewshot.py render --run-dir results/deepseek-flash/few-shot-bm25-k3-v1/<run_id> --id AGENTRISK-004

# 打分：生成 <run_dir>/metrics.json
.venv/bin/python src/evaluate.py results/deepseek-flash/zero-shot-v1/<run_id>

# 交互式分析报告：生成 <run_dir>/report.html，用浏览器打开
.venv/bin/python src/analyze.py results/deepseek-flash/zero-shot-v1/<run_id>

# 多个运行并排对比：生成 results/comparison.md
.venv/bin/python src/compare.py

# 交互式对比页：生成单文件 results/comparison.html（无外部依赖，浏览器直接打开）
.venv/bin/python src/compare_html.py
```

命令写成一行，`--run-id` 写错会提示目录不存在，不会误建新运行。

### 下一轮流程（Makefile 入口）

`dev` 已冻结为最终测试：所有选择在 train 内部的验证集上做，`dev` 只跑一次。方案见 [docs/next-round-plan.md](docs/next-round-plan.md)。

```bash
make validate                          # 离线自检：编译、切分漂移检查、dev/train_val 干跑
make splits                            # 重建 data/splits（场景组切分 + 严重度分层）
make baseline LIMIT=5                  # train_evolve 上跑 zero-shot 基线（LIMIT 先探）
make triage RUN=<run_dir>              # 错误分诊：桶分类、混淆矩阵、标签漏/多
make worklist RUN=<run_dir>            # 错例 -> worklist.jsonl
make analyze LIMIT=5                   # 逐条归因（evidence 闸门），先 5 条看质量
make cluster                           # 按主题聚类 lessons，看支持度
make merge                             # 合并成 prompts/patches/v2/ + CHANGELOG
make dev-final                         # 最终测试，只跑一次
```

### 协作约定

- 密钥只放本地 `.env`，不提交；`.env.example` 保持为空值。
- 已经用于正式运行的 prompt 不再修改，要改就新建版本（如 `zero_shot_v2.txt`、`few_shot_v2.json`）并开新的运行。
- few-shot 的示例选择文件在 `data/fewshot/`，已入库；换随机种子请生成新文件（`random_seed1.json`），不要覆盖旧的。
- 每次运行写进新的 `run_id` 目录，不覆盖旧结果。

### 当前状态

dev 143 条上共跑过 **11 个配置**，全部 143/143 合法预测。完整对比见 [results/comparison.md](results/comparison.md)；方法、切分与逐阶段结论见 [docs/next-round-plan.md](docs/next-round-plan.md)。

| 运行 | Task 1 MAE | Task 2a Mean Jaccard | Task 2b Mean Jaccard | 三字段全对 |
| --- | --- | --- | --- | --- |
| zero-shot v1 | 0.301 | 0.811 | 0.726 | 70（49.0%） |
| zero-shot v2（+5 条蒸馏规则） | 0.287 | 0.831 | 0.732 | 69（48.3%） |
| random k=3 / 5 / 10 / 20（seed 0） | 0.273 / 0.266 / 0.245 / 0.217 | 0.854 / 0.839 / 0.843 / 0.850 | 0.724 / 0.733 / 0.740 / 0.754 | 50.3 / 53.1 / 51.0 / 52.4% |
| bm25 k=3 / 5 / 10 / 20 | 0.266 / 0.231 / **0.189** / 0.196 | 0.853 / **0.867** / 0.862 / 0.852 | 0.752 / 0.779 / **0.793** / 0.759 | 52.4 / 56.6 / **56.6** / 54.5% |
| bm25 k=10 + v2 规则 | **0.189** | 0.862 | 0.783 | 55.9% |

结论（2026-10-28）：

1. **bm25 k=10 是当前最好配置**：MAE 0.189，相对 zero-shot 0.301 显著更好（配对自举 95% CI [−0.175, −0.049]）。
2. **k=20 没有更好**：与 k=10 的差为 +0.007，CI [−0.028, +0.042]，属噪声。143 条 dev 上，MAE 差距小于约 **0.03** 一律按噪声处理（`src/paired_bootstrap.py`）。
3. **蒸馏规则在有示例时零增量**：bm25 k10 + v2 与 bm25 k10 + v1 的 MAE 差为 0.000，其余指标同为噪声，因此**提交配置保持 v1**，少一层复杂度。规则只在无示例的基线上有效（train_val 0.421 → 0.308）。
4. **dev 已冻结**：它已被 11 个配置用于选择，0.189 是选择后的乐观上界。之后的实验一律在 `train_val`（107 条）上做，dev 只在最终提交前跑一次。官方隐藏测试集才是泛化成绩。

### 协作约定

- 密钥只放本地 `.env`，不提交；`.env.example` 保持为空值。
- 已经用于正式运行的 prompt 不再修改，要改就新建版本（如 `zero_shot_v2.txt`、`few_shot_v2.json`）并开新的运行。
- few-shot 的示例选择文件在 `data/fewshot/`，已入库；换随机种子请生成新文件（`random_seed1.json`），不要覆盖旧的。
- 每次运行写进新的 `run_id` 目录，不覆盖旧结果。

### 当前状态

Zero-shot v1（`deepseek-flash`）已跑完完整 dev，143/143 条均有合法预测，正式运行是 `results/deepseek-flash/zero-shot-v1/20261022-051556/`：

| Task 1 MAE | Task 2a Mean Jaccard | Task 2b Mean Jaccard |
| ---------- | -------------------- | -------------------- |
| 0.301      | 0.811                | 0.726                |

主要问题：模型整体高估风险（标准答案为 3 的样本里 20/32 被预测成 4），并倾向多给第二个标签。详见该目录下的 `report.html`。

Few-shot（每条 dev 样本各自选 k 个 train 示例，其余和 zero-shot 完全一致）已跑完 8 组，均 143/143 合法预测。完整对比见 [results/comparison.md](results/comparison.md)，错误分析（草稿）见 [results/few-shot-error-analysis.md](results/few-shot-error-analysis.md)：

| 运行 | Task 1 MAE | Task 2a Mean Jaccard | Task 2b Mean Jaccard |
| --- | --- | --- | --- |
| zero-shot v1 | 0.301 | 0.811 | 0.726 |
| random k=3 / 5 / 10 / 20（seed 0） | 0.273 / 0.266 / 0.245 / 0.217 | 0.854 / 0.839 / 0.843 / 0.850 | 0.724 / 0.733 / 0.740 / 0.754 |
| bm25 k=3 / 5 / 10 / 20 | 0.266 / 0.231 / **0.189** / 0.196 | 0.853 / **0.867** / 0.862 / 0.852 | 0.752 / 0.779 / **0.793** / 0.759 |

随机组在 k=3→20 上单调变好，BM25 在 k=10 见顶、k=20 回落（MAE 0.189→0.196，Task 2b 0.793→0.759）；「越多越好」对随机组成立，对 BM25 不成立。BM25 在 Task 1 上每个 k 都优于随机，Task 2a 在 k=20 时两者基本持平（0.852 vs 0.850）。随机组只有一个种子，单个小差异可能是噪声。
