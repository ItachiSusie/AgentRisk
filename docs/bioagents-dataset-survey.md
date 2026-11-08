# BioAgents 相关数据集调研与 AgentRisk 扩展建议

调研日期：2026-10-30。范围：官方 workshop 页面、作者项目页、官方代码仓库和数据卡。本文为资源筛选与实验建议，未下载完整数据、执行环境或完成逐样本审核；公开数量以以下链接的当前说明为准。

## 1. 结论与 workshop 定位

有可用资源。建议优先考察 MedAgentBench、MedCTA 和 BixBench，分别覆盖医疗动作、临床工具轨迹、生物科研分析。它们适合作为 AgentRisk 的领域扩展来源，但本次核查的资源中，没有一个直接提供与 AgentRisk 完全一致的“历史 + 下一动作 → 五级风险 + harm domain + risk driver”标签。

[BioAgents 官网](https://bioagents-workshop.github.io/) 的主题是生物医学发现与医疗中的多智能体系统（Multi-Agent Systems，即多个专门 agent 协作完成任务）。官网 Topics of Interest 明确包括安全、可靠性、可信度、评测和患者隐私；网页未附带统一竞赛数据集。官网 Important Dates 列出的投稿截止日期为 2026-11-20，workshop 日期为 2026-12-14。

若以该 workshop 为目标，研究问题可以是：**从通用 agent 轨迹中提炼的风险守护技能（Guardian Skill，即在执行前检查动作及其证据和授权的指令），能否迁移到医疗与生物科研 agent？** 这是本文建议的切入点，不是 workshop 的官方任务要求。

## 2. 核心候选

| 资源 | 官方规模与形式 | 已有监督信息 | 对我们最合适的用途 | 接入难点 |
| --- | --- | --- | --- | --- |
| MedAgentBench | 300 个临床任务，100 个患者档案；虚拟电子健康记录环境 | 任务目标与完成检查 | 在医疗动作执行前，构建允许、确认、拦截的对照 | 需要运行环境或取得执行记录，另标风险 |
| MedCTA | 107 个临床多模态任务，含参考工具轨迹 | 图像、问题、参考轨迹、最终答案和工具定义 | 现成轨迹的离线风险标注试点 | 多模态证据不能随意删掉；参考正确性不等于无风险 |
| AgentClinic | 仓库公告的扩展版本：MedQA 215 例、NEJM 120 例 | 病例与模拟患者/医生互动环境 | 不完整信息下的判断、偏差和过早诊断 | 需要生成轨迹；病例来源和访问条件分开核查 |
| BixBench | 205 个问题，来自 60 个真实研究 notebook；仓库链接原论文 2,120 条运行轨迹 | 科研问题、参考答案、代码执行与结果 | 科研分析流程中的证据、结果报告与文件操作风险 | 原始轨迹版本与当前题集要对齐；需要另标安全性 |
| BiomniBench-DA | 总计 100 任务，公开其中 50 个；含参考轨迹和专家评分细则 | 对完整分析过程的评分依据 | 更深入的科研过程风险审计 | 需接受访问条件；底层数据按各自条款使用 |
| MedSafetyBench | 1,800 个有害医疗请求与安全回复对，train/test 各 900 | 安全回复；另有额外生成请求资源 | 医疗安全原则归纳、辅助训练 | 不是多轮工具轨迹，也没有五级风险标签 |

数量与字段出处：

- MedAgentBench：[官方项目页](https://stanfordmlgroup.github.io/projects/medagentbench/) 的 What is / Why / Dataset structure；[官方仓库](https://github.com/stanfordmlgroup/MedAgentBench) 的 Quick Start。
- MedCTA：[官方数据卡](https://huggingface.co/datasets/IVUL-KAUST/MedCTA) 的 Dataset Summary、Dataset Schema；其中 `trajectory` 是完整参考对话及工具轨迹。
- AgentClinic：[官方仓库](https://github.com/SamuelSchmidgall/AgentClinic) 的 Release（2024-08-17）；该数量是公告中的扩展病例数，不与早期版本相加。
- BixBench：[官方仓库](https://github.com/Future-House/BixBench) 的介绍和 Replicating the Paper Results / Original Paper Results；2,120 是执行轨迹数，不是独立问题数。
- BiomniBench-DA：[官方数据卡](https://huggingface.co/datasets/phylobio/BiomniBench-DA) 的介绍、Task structure。
- MedSafetyBench：[官方仓库](https://github.com/AI4LIFE-GROUP/med-safety-bench) 的 Dataset structure；正式区分训练和测试目录。

## 3. 能否训练、访问与许可

以下是资源页面的许可/访问记录，不将代码许可证自动扩展为所有底层病历、图片和论文数据的授权。

| 资源 | 已核实页面信息 | 当前使用建议 |
| --- | --- | --- |
| MedAgentBench | 仓库标为 MIT；官方提供虚拟环境；病例源于去标识化 STARR 数据 | 先核查实际分发包和患者数据条款；任务/环境可作为试点候选，训练及派生公开前确认覆盖范围 |
| MedCTA | 官方数据卡与代码仓库标为 Apache-2.0，数据卡可浏览轨迹字段 | 可优先做小规模离线标注；保存图像来源和许可记录，核对底层材料条款 |
| AgentClinic | 官方仓库标为 MIT；MIMIC-IV 子集需要访问审批 | 优先开放子集；不能把仓库许可当作 MIMIC-IV 数据的无条件授权 |
| BixBench | 代码仓库 Apache-2.0；数据经 Hugging Face 获取，官方另链接历史运行轨迹 | 先用于独立测试；训练前核实数据卡、原始 capsule 和轨迹文件条款 |
| BiomniBench-DA | 基准指令、评分细则、参考轨迹等为 CC-BY-4.0；需接受访问条件；底层数据保留原许可 | 接入前读取访问条件；先预留作独立评估，不能默认所有科研数据可再分发 |
| MedSafetyBench | 仓库 MIT，同时 README 明确要求仅用于研究 | 辅助训练仅使用官方 train；test 保留评测用途 |

许可和访问依据分别见上表链接的仓库 License / README、数据卡 License；AgentClinic 另见 [论文 Data availability](https://pmc.ncbi.nlm.nih.gov/articles/PMC13324710/)。尚未接受任何需要登录确认的条款，也未申请受控病历访问。

## 4. 通用 agent 安全资源与不优先项

**ATBench** 更接近我们评估器的输入输出结构：当前版本有 1,000 条完整工具使用轨迹，含安全二分类、风险来源、失败方式、现实损害及说明。官方数据卡标为 Apache-2.0，分发为 test；建议优先作为外部评估，若将其改作训练，必须另设互不重叠的测试集并公开说明。它不是专门的生物医学数据，也不是 AgentRisk 五级风险标签。出处：[官方数据卡 Shared Task Definition / Schema Notes / License](https://huggingface.co/datasets/AI45Research/ATBench)。

**R-Judge** 有多轮交互、安全二分类和风险描述。官方仓库当前版本报告 569 条，早期项目页的 162 条不应混用。它可作通用安全判断对照，但必须先核查与 AgentRisk 的场景和上游来源是否重叠；本文未证明两者独立，也不建议未经核查直接并入训练或称为分布外测试。出处：[官方仓库](https://github.com/Lordog/R-Judge)、[正式论文摘要](https://aclanthology.org/2024.findings-emnlp.79/)。

**LAB-Bench** 是生物研究能力问答，并非多轮风险轨迹。官方数据虽使用名为 train 的 split，但样本含“基准数据不应进入训练语料”的 canary 提示；本项目将其保留为评测候选，不因 split 名称而当作可训练数据。出处：[官方数据页的字段和 canary](https://huggingface.co/datasets/futurehouse/lab-bench)。

普通医学选择题或原始病历也不能直接替代动作风险样本：医学答案正确、任务完成与动作安全是不同的监督目标。

## 5. 推荐试点：医疗动作 + 科研分析

以下数量是我们建议的试点预算，不是现成数据集规模或已完成结果。

### 路线 A：先做医疗动作守护

优先从 MedAgentBench 的可取得执行记录或隔离环境运行中选取约 20–30 个独立病例/任务场景；若环境成本高，先用 MedCTA 现有轨迹验证标注流程，再补医疗写入动作。

为每个场景保存“截至决策点的历史 + 拟执行动作”，构建有明确证据的安全与危险对照。可考察：患者身份未核对即写入、依据不完整即修改记录、授权范围外导出信息，以及先补充证据或请求确认的替代动作。它们是待构造的场景类型，不声称原数据已含这些错误。

不能将未来发生的结果放进预测输入，也不能把整段轨迹的 unsafe 标签直接贴给每一步；应由标注者针对当前动作重新判断。医学后果和严重度由临床领域审核者复核。

### 路线 B：科研流程外部验证

优先使用 BixBench 的公开历史轨迹，先核对其对应版本、任务和可读性；BiomniBench-DA 作为参考轨迹与过程评分的补充候选。

重点标注有迹可查的证据不足、数据覆盖/误改、分析结论与工具结果不符、缺少质量检查就发布结论等风险。必须区分“分析错误”与“对人、数据、服务或信息质量构成风险”：一次可恢复的失败不自动成为高风险。不能由纯计算任务推断其已产生临床治疗后果。

### 公共标注与划分

1. 保留来源、版本、原始任务和场景组标识，以及抽取的决策步骤。
2. 按 AgentRisk 定义标五级风险、损害领域（harm domain，即可能被损害的对象）和风险成因（risk driver，即使动作危险的因素），附可定位证据和不确定项；无法对齐者明确排除或保留为原生任务。
3. 两位标注者独立标注并解决分歧；医学判断由领域审核者参与。若新增干预标签，单独给出政策及其依据，不称为官方 Task 3 标签。
4. 在生成改写前按原始患者、病例、研究 capsule 或论文分组划分；同一场景的安全/危险变体不可跨训练与测试。与 AgentRisk train/dev 检查重复及近似场景。
5. 外部测试集保持冻结，不用于 Trace2Skill 提炼；外部训练材料与测试材料分别记录。派生数据能否公开，取决于全部上游条件。

## 6. 如何接入现有三轮计划

第一轮先完成通用 Guardian Skill，在冻结的医疗/科研试点上做迁移评估。比较无示例（zero-shot，即仅给任务指令）与少样本（few-shot，即附带标注示例）设置，各自使用和不使用 skill。示例和 skill 来源保持一致，不从外部测试集取例。

第二轮若开展领域适配，再比较“仅官方 train 微调”与“官方 train + 独立外部训练子集微调”；数据增强（data augmentation，即通过受控变换增加训练样本）另设对照。不要把用于证明迁移能力的同一批病例同时用于训练。

第三轮仍按正式 SemEval 规则决定外部数据是否进入比赛系统；领域试点可以作为独立研究结果，不预设比赛允许使用。

推荐执行次序：**MedCTA 少量轨迹检查 → MedAgentBench 动作场景试点 → BixBench 科研外部验证**。若只推进一个方向，优先 MedAgentBench 的医疗动作守护；若目标是最快验证现成轨迹能否转成标注样本，优先 MedCTA。
