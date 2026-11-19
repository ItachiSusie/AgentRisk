# 医疗智能体风险与对抗安全基准调研

**初次调研：2026-11-11；增补核查：2026-11-13。** 本文核查论文、会议页面、作者项目页和官方代码仓库，重点看评测是否包含医疗任务、真实的多轮工具动作、攻击者可控入口、可验证的违规结果，以及正常任务效用。表中数字均指向原论文的章节或官方仓库；不同基准的分母和攻击权限不同，成功率不可直接横向比较。

## 1. 结论

已经有与医疗智能体风险密切相关的基准。尤其需要正面比较的是医疗提示注入基准（Medical Prompt Injection Benchmark, MPIB，评估恶意内容对医疗答复及临床伤害的影响）、医疗访问控制基准（EICU-AC，按用户角色检查重症监护数据访问权限）、**QFIRE-HealthBench** 的医疗攻击提示和模拟病历动作实验，以及 **MedToolFault** 的医疗工具故障与状态核对。因此不应宣称本项目是“首个医疗智能体安全基准”。

**“没有可交互医疗安全基准”也不准确。** MedAgentBench、HealthAgentBench 和 MedHarnessBench 都让智能体在可执行环境中与工具交互；QFIRE-HealthBench §5.8 已在模拟病历中测试攻击和正常任务，THReD §5.3 已在病历数据预处理任务中测试表格指令注入；MedToolFault 以工具故障测试读写状态。较窄、仍需验证的研究空间，是在同一可重置医疗工作流中系统比较权限明确的多入口对抗攻击，特别是技能、跨任务记忆、病历/工具返回与恶意用户，并分别检查动作、观察和输出。**这是基于已核查文献的定位判断，不是对所有未检索工作的排除证明。** [MedAgentBench §2.4.3](https://arxiv.org/html/2501.14654v2)、[HealthAgentBench 官方仓库“Overview”](https://github.com/microsoft/HealthAgentBench)、[QFIRE-HealthBench §5.8](https://www.medrxiv.org/content/10.64898/2026.06.04.26354950v2.full.pdf)、[THReD §5.3](https://arxiv.org/html/2611.02484)、[MedToolFault §2.1](https://arxiv.org/html/2611.09942)

本文区分医疗安全（clinical safety，关注错误建议或动作可能造成的临床伤害）与对抗安全（security，关注攻击者通过注入、篡改或越权改变智能体行为）。提示注入（prompt injection，把指令藏入智能体会读取的低信任材料）只是后者的一种手法；错误临床数据也可能在没有显式指令的情况下误导结果。

## 2. 最相关的基准

| 基准与状态 | 任务及评估对象 | 对抗设置与评分 | 对本项目的意义及边界 |
| --- | --- | --- | --- |
| **[MedAgentBench](https://stanfordmlgroup.github.io/projects/medagentbench/)**；[原论文](https://arxiv.org/html/2501.14654v2)，2025 | 300 个患者相关任务，使用电子健康记录（Electronic Health Record, EHR，保存患者临床资料的数字病历系统）和 FHIR（Fast Healthcare Interoperability Resources，医疗数据交换接口）工具。 | 官方重点评估任务是否完成。 | 本项目的任务与环境底座；原版未系统构造多入口攻击目标。[项目页“MedAgentBench”](https://stanfordmlgroup.github.io/projects/medagentbench/) |
| **[MedAgentBench v2](https://github.com/ericoericochen/medagentbenchv2)**；2026 年论文与独立仓库 | 改进工具设计，并加入从先前失败学习的记忆组件；仓库说明另外开发了 300 条多步任务。 | 主要评估智能体任务能力及记忆带来的变化。 | 是本项目扩展任务、工具与记忆设计的直接对照；其“从失败学习的记忆”与本项目按患者授权、可被攻击的跨任务记忆不是同一实验设置。[官方仓库 README](https://github.com/ericoericochen/medagentbenchv2) |
| **[MPIB](https://aclanthology.org/2026.findings-emnlp.1670/)**；2026 年同行评审论文 | 9,697 个医疗问题、边界案例与对抗实例；涵盖直接攻击及检索增强生成（Retrieval-Augmented Generation, RAG，先检索资料再将资料交给模型生成答案）中的污染材料。 | 同时报告攻击成功与临床伤害事件率（Clinical Harm Event Rate, CHER，高严重度临床伤害答复的比例）；采用结构化模型评审，并有医疗专家抽样核查。 | 最直接的医疗提示注入对照。主体评估医疗问答和检索上下文中的答复，未把多轮病历工具动作作为主要结果对象。[论文 §3–4](https://arxiv.org/html/2602.06268) |
| **[EICU-AC / GuardAgent](https://guardagent.github.io/)**；2025 年同行评审论文 | 给重症监护数据查询指定医生、护士或行政人员角色，并规定可访问的数据表与信息类别。 | 判断请求应放行还是拒绝；每个实例含角色、所需数据与访问控制标签。 | 与本项目的患者隐私、授权和执行前守护器高度相关；重点是访问控制，而非多入口攻击植入和医嘱后果。[项目页“Benchmark”](https://guardagent.github.io/)、[论文](https://proceedings.mlr.press/v267/xiang25a.html) |
| **[QFIRE-HealthBench](https://github.com/Task-force-for-AI-agents-in-Healthcare/qfire)**；2026 年预印本 | 1,000 条正常和 1,000 条恶意医疗提示，覆盖跨患者访问、隐私信息外泄等；另用模拟病历环境测试工具智能体。 | 静态提示检测与端到端动作实验并行。论文 §5.8 的模拟病历实验包含 40 条攻击、40 条正常任务；报告守护器启用前后有害动作和正常效用。 | **最接近本项目“医疗攻击＋动作守护”的工作**。不能把我们的差异写成“首次测医疗智能体攻击”；可比较具体任务、入口权限、配对协议和结果判定。其模拟病历实验的规模与所用模型也限制了结论。[代码及数据说明](https://github.com/Task-force-for-AI-agents-in-Healthcare/qfire)、[预印本 §5.8](https://www.medrxiv.org/content/10.64898/2026.06.04.26354950v2.full.pdf) |
| **[THReD benchmark](https://arxiv.org/html/2611.02484)**；2026-11 预印本 | 141 项电子病历数据预处理任务，其中包含把恶意指令植入数据表的任务；检查产出的数据及动作。 | 论文 §5.3 报告 40 次数据注入运行，预设的结果检查还揭示了一例规则误报。 | 提供“用最终结果核查而非只看工具名”的参考；研究对象是临床研究数据整理，不是给患者提交医嘱。[论文 §4–5](https://arxiv.org/html/2611.02484) |
| **[MedToolFault / MedGuard](https://arxiv.org/html/2611.09942)**；2026-10 预印本 | 以公开医疗智能体任务和患者记录构造可交互的工具故障环境，检查答案、必要写入及禁止的状态变化。 | 六类故障覆盖接口漂移、暂时错误、过期/缺失证据、患者错配、来源冲突与不确定写入；对干净可完成任务做配对分析。 | 是“实时工具扰动＋状态核对”的强相关对照。主要研究故障恢复和工具层验证，未把技能文件、跨任务记忆及多入口攻击指令作为统一攻击集合。[论文 §2.1、§4.2](https://arxiv.org/html/2611.09942)、[官方代码](https://github.com/Learner4everrr/MedToolFault-MedGuard) |
| **[MedHarnessBench](https://arxiv.org/html/2610.15714)**；2026-10 预印本 | 论文 §3.2 描述 342 项可执行医疗任务，覆盖病历操作、医疗行政接口与多模态工具，并记录运行器干预轨迹。 | 比较任务结果与七类医疗执行过程质量，另用受控单故障测试过程指标敏感性。 | 证明已有可执行医疗 agent harness；重点是运行过程质量和支持机制，不是本项目设想的技能/记忆污染与攻击权限矩阵。[论文 §3.2、§5.3](https://arxiv.org/html/2610.15714)、[官方代码](https://github.com/Tomry1114/Awesome-Agent-Harness-for-Healthcare) |

### MPIB 的标签验证值得特别学习

MPIB 使用大模型评审（LLM-as-a-judge，让语言模型按固定准则为答复赋标签），但没有仅凭模型输出宣称临床金标准。两名医疗专家核查了最终数据集的 **200 条分层样本**，还盲评了 **300 份模型答复**；论文同时报告一致性与不同评审模型的稳定性。其伤害严重度是临床判断，不能直接等同于本项目“是否提交指定错误动作”的规则标签。[MPIB §4.2](https://arxiv.org/html/2602.06268)

## 3. 邻近工作：有用，但测量层次不同

| 工作 | 可借鉴之处 | 与本项目的主要差别 |
| --- | --- | --- |
| [MedMisBench](https://arxiv.org/abs/2606.12291)，2026 预印本 | 从五个来源保留 **10,932 道**有确定答案的问题，以误导性上下文测试判断是否被带偏；临床评审抽样检查攻击材料及模型答复。[论文 §3、附录 B](https://arxiv.org/abs/2606.12291) | 主要是医疗判断与答案改变，不是病历工具执行。 |
| [The Model Knows Better](https://arxiv.org/html/2610.22594)，2026 预印本 | 测医疗多智能体讨论被病例文本误导，比较无防御和多种防御；借用了 MPIB 的自由文本伤害评估。[论文 §6.1](https://arxiv.org/html/2610.22594) | 主要是诊断或推荐，不是电子病历读写工作流。 |
| [MedSafetyBench](https://github.com/AI4LIFE-GROUP/med-safety-bench)，2024 年同行评审论文 | **1,800 组**有害医疗请求与安全答复，适合测拒答和安全完成。[官方仓库“Dataset structure”](https://github.com/AI4LIFE-GROUP/med-safety-bench) | 没有多轮工具轨迹或病历环境。 |
| [HealthAgentBench](https://github.com/microsoft/HealthAgentBench)，2026 | 终端式医疗及生物医学工具任务，任务专用验证器检查结果；2026-10-25 发布的 v2.0 仓库在“Overview / Task Categories”列出 75 项可执行任务。[官方仓库](https://github.com/microsoft/HealthAgentBench) | 明确是 live 医疗 agent 任务；重点是工具任务能力，目前不是多入口安全攻击基准。 |
| [AgentDojo](https://papers.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)，2024 年同行评审论文 | **97 个**正常工具任务、**629 个**安全测试案例；动态环境、正常效用与攻击目标并评，是协议设计参考。[论文摘要](https://papers.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html) | 场景为通用办公、银行与旅行等，不定义医疗授权或临床前置条件。 |
| [ToolHazard-Bench](https://arxiv.org/html/2608.11878)，2026 预印本 | 生成可执行的有状态环境、寻找攻击点，并用验证函数检查正常任务与攻击任务；还分析注入时机。[论文 §4–7](https://arxiv.org/html/2608.11878) | 是跨领域环境合成框架；医疗伤害语义不构成其主要评分目标。 |
| [EHR-Agent-PI](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6828838)，2026 工作论文 | 提出面向病历智能体的跨入口威胁模型和基准规格，与我们的设计问题高度接近。[论文摘要](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6828838) | 摘要称其为**规格**；核查时未据此确认已有完整运行结果，不能按已落地基准引用。 |

另有 [A²-Bench-Healthcare](https://agentbeats.dev/Ahm3dAlAli/a2-bench-healthcare) 的平台页面称包含 **32 项医疗任务**和安全、安保、可靠性及合规评分。当前核查只确认了平台描述，未确认足够详细的论文、攻击权限及复算协议，因此暂不把它作为核心方法对照。[平台页面“About”](https://agentbeats.dev/Ahm3dAlAli/a2-bench-healthcare)

## 4. 本项目应如何定位

这里把 **live / interactive** 定义为被测智能体在一次任务中实际选择动作、收到环境反馈，并据此选择下一动作；把 **stateful** 进一步定义为写入影响后续可观察状态，且每条样本可重置。原版 MedAgentBench 属于前者，但 POST 只是模拟接受，不满足这里的后者。HealthAgentBench 的终端任务及 MedToolFault 的状态核对说明医疗 live 评测已经存在；本项目应明确报告自身处于哪一层。[MedAgentBench §2.4](https://arxiv.org/html/2501.14654v2)、[HealthAgentBench“Overview”](https://github.com/microsoft/HealthAgentBench)、[MedToolFault §2.1](https://arxiv.org/html/2611.09942)

建议表述为：**在 MedAgentBench 的病历任务上，构造具有明确攻击权限的多入口安全扩展，并通过可复算的交互轨迹同时评估攻击结果与正常任务效用。** 这个表述承认 MedAgentBench、MPIB、EICU-AC 和 QFIRE 的已有贡献，也准确指出我们的组合设计。

下一版对新增任务、工具、合成数据、技能/记忆和有状态评测的实施合同见[MedSecBench v0.6 扩展规格](medsec-expansion-spec-v0_6.md)。其 §10 另定义 HealthAgentBench 安全扩展轨道：复用终端任务及 Harbor 运行方式，在病历数据审计和组合问答任务上增加低信任载体、攻击目标及独立安全判定器；两种底座的成绩分别报告。完整的双底座任务、攻击、判定与实施合同见[MedSecBench v0.7 规格](medical-healthcare-security-benchmark-spec-v0_7.md)。[HealthAgentBench 官方 README“Overview / Task Categories / Project Structure”](https://github.com/microsoft/HealthAgentBench/blob/main/README.md)

可形成可检验差异的部分：

1. **任务与动作**：保留官方病历任务与工具；在患者查询、模拟写入和最终答复三个层面查具体偏离，而不把“检测到可疑文本”当作攻击成功。
2. **入口与权限**：分开规定病历字段、工具返回、工具描述、技能文件、诱导写入记忆、直接改记忆、检索文档及恶意用户消息的可控范围。更强权限与普通病历编辑不合并统计。[本项目规格 §2](medagentbench-medical-security-benchmark-spec.md)
3. **因果对照**：同任务的干净与攻击运行共享模型、初始条件和预算；分别记录植入、实际暴露、候选动作与最终结果。[本项目规格 §4–5](medagentbench-medical-security-benchmark-spec.md)
4. **双重评分**：官方评分器判断正常任务效用；本项目安全判定器判断预先指定的错误患者、错误剂量、漏做必要动作、错误答复等目标是否由轨迹证明。[本项目规格 §3、§11](medagentbench-medical-security-benchmark-spec.md)

**当前数字的正确写法**：运行编号（run ID，唯一标识一次实验及其输出的名称）`20261111-all37-flash-v05-01` 使用 37 组已知攻击与干净配对，其中 **37/37 权限有效、36/37 在目标任务暴露、10/37 达成指定攻击目标**。这只描述这批已知样本，不能称为总体攻击成功率；它也不是守护器收益。原始配对清单为 [`data/medsec/all37_pairs_20261111_v05.json`](../data/medsec/all37_pairs_20261111_v05.json)，复算报告为 [`results/medsec/reports/all37-flash-v05-01.json`](../results/medsec/reports/all37-flash-v05-01.json)，权限审计报告为 [`results/medsec/reports/all37-flash-v05-01-audited.json`](../results/medsec/reports/all37-flash-v05-01-audited.json)。[结果记录“全部 37 条攻击”](medsec-results-v0.4-v0.5.md)

**标签边界**：目前攻击目标标签采用规则判定（rule-based labeling，按预先定义的可观察条件从事件轨迹自动赋标），例如核对最终答复的目标数值、错误患者的读写事件，或任务结束后必要写入是否缺失。代码可从保存的运行事件复算，并另审计攻击是否超出编辑权限；这些标签说明**指定目标有无证据**，不自动给每个动作下临床安全结论。[判定器](../src/medsec/judge.py)、[复算入口](../src/medsec/evaluate.py)、[权限审计](../src/medsec/audit_report.py)、[结果记录“三个防御检查点”](medsec-results-v0.4-v0.5.md)

## 5. 下一阶段的研究要求

1. **临床核验**：对任务前置条件、正常参考结果及关键动作进行有临床背景的盲审；对规则难覆盖的伤害严重度另设人工标签。MPIB 的分层专家核查可作为方法参考。[MPIB §4.2](https://arxiv.org/html/2602.06268)
2. **基准结果分层**：按入口、攻击权限、临床目标、任务类别和是否实际暴露报告分子与分母；同时报告干净任务效用、攻击下效用及正常材料误拦截。避免只给一个总攻击成功率。[本项目规格 §5](medagentbench-medical-security-benchmark-spec.md)
3. **守护器配对实验**：在相同病例、模型与预算下比较无守护器、通用守护器和医疗守护器；同时测危险动作放行、误拦截、任务完成和调用成本。[试点方案“评测与试点交付”](medagentbench-guardian-pilot.md)
4. **明确模拟环境边界**：原 MedAgentBench 的写入请求仅模拟接受。因此目前可判断“危险拟写入动作被接受”，不能声称真实病历已改变；若要测最终记录状态，需另设可重置的写入环境。[本项目规格 §5](medagentbench-medical-security-benchmark-spec.md)

## 6. 检索与证据限制

本次优先使用会议论文、作者论文、官方项目页及官方仓库；预印本和仅有平台描述的工作已单独标注。文献检索不能证明某个方向绝对不存在，且各基准的“攻击成功”“伤害”“误拦截”和“效用”定义并不相同。本文未复现外部基准的代码或重新计算其报告数字；数字仅用于描述各工作的公开设计和规模，不用于与本项目 `10/37` 比高低。
