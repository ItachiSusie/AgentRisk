# 智能体式蒸馏（第三轮 trace2skill）：共用设计

创建日期：2026-11-07 · 状态：§7 代码改动已于 2026-11-07 实现（单元测试 29 个全过，旧运行的 `metrics.json` 与 `triage` 输出逐字节不变）；阶段 A 的 prompt 在试点后改为 v3b，见 [01-blind-probe.md](01-blind-probe.md) §8

本文是四份方案的共用部分，讲清楚要改哪些文件、新增哪些东西、各任务共享的规则。四份方案分别是：

| 文件 | 内容 | 依赖 |
| --- | --- | --- |
| [01-blind-probe.md](01-blind-probe.md) | 盲测探针：判断 Task 1 的 3/4 错例是理解错误还是尺度错误；同时是新分析器的试点 | 本文 §3、§4 |
| [02-task1.md](02-task1.md) | Task 1：新输出格式 `facts` 线 + 带回测的智能体式蒸馏 | 01 的结论 |
| [03-task2a.md](03-task2a.md) | Task 2a：同 Task 1 的流程，外加「默认单标签」对照 | 02 跑通后 |
| [04-task2b.md](04-task2b.md) | Task 2b：同 Task 1 的流程，外加易混标签对统计 | 02 跑通后 |

执行顺序：**本文的代码改动 → 01 → 02 → 03 / 04**。03 和 04 可以并行。

命名、目录、`run_id` 规则沿用 [单任务共用设计](../single-task/00-common.md) §3，本文只写新增的部分。


**本轮范围（2026-11-07 定稿）**：三个任务都走 facts 格式线：facts-v1 zero-shot 作基线 （train_evolve、train_val、dev）→ dev 上 BM25 k=10 few-shot（不跑 random 和其他 k）
→ 智能体式蒸馏（Claude 诊断 + deepseek 写 patch + train_evolve 回测）得到 facts-v2 → train_val 记录一次 → dev 上 facts-v2 zero-shot 与 BM25 k=10。
与 [单任务实验](../single-task/00-common.md) §2 的数据集口径相同：few-shot 只在 dev 上跑，train_val 只用于记录蒸馏结果。执行清单见各任务方案的 §0.1：[Task 1](02-task1.md)、[Task 2a](03-task2a.md)、[Task 2b](04-task2b.md)。

## 0. 2026-11-07 修订（试点之后，用户已同意）

本节优先于后文。后文与本节冲突的地方，以本节为准。

| 编号 | 修订 | 原因 |
| --- | --- | --- |
| R1 | **分析器与预测模型必须是不同的模型。**预测模型仍是 deepseek-flash（它是要提交的系统）；分析器改为 Claude。没有 Claude API 时，用 `src/agentic.py export / import` 走文件交接：代码导出每条样本的输入文件，另开的 Claude 子代理（subagent，即一个看不到主对话、只读指定文件的独立 Claude 会话）写出结果文件，代码再导入，并做一致性检查和统计 | 试点中分析器与预测模型同为 deepseek-flash，`blind_implied` 有 19/20 等于预测值，无法排除同源偏差 |
| R2 | **漏读事实要逐条标 `moves_level`**（会不会改变等级）。只有会改变等级的漏读，才让事实层变成 `missed`（prompt v3b） | v3 把所有没提到的细节都算作漏读，第一轮矛盾率高达 75% |
| R3 | **把「相邻两级都说得通」（`adjacent_defensible`，是/否）换成强制选择 `favoured_level`**：阶段 A 拿到两个候选等级（升序给出，不说哪个是答案），只能回答「更支持哪一个」或 `cannot_tell`（prompt v3c） | `adjacent_defensible` 在 41/41 条里都是 true，没有区分力；结果 K3 永远满足、K4 永远不满足，`threshold` 和 `weighting` 分不开 |
| R4 | 一致性检查改用 `favoured_level`：K3 为 `threshold` ⇒ 更支持预测值或 `cannot_tell`；K4 为 `weighting` ⇒ 更支持真实值；K8 为 `gold_questionable` ⇒ 不支持真实值 | 配合 R3 |
| R5 | 阶段 A 增加字段 `decisive_feature`：用通用措辞写出这条样本的判断取决于哪个特征。修复循环的回测集要按它取「特征相同、真实等级在另一侧」的样本 | 试点发现「只涉及一个收件人」这个特征在真实 3 级和 4 级里都有。只按范围写规则，一定会弄坏另一侧 |
| R6 | 人工抽查可以先交给另开的 Claude 会话做交叉核对，（审阅 prompt 是一次性工具，不进 PR，需要时再生成（2026-11-09 决定））。Task 2 的 G3 改为按需做，见 03 / 04 §0.1。但 Claude 审 Claude 有同源偏差，**用户本人仍至少要看 3–5 条** | 用户要求 |
| R7 | Task 2 的阶段 A，要把模型推理里出现的标签名替换成 `[LABEL]`。否则推理文本本身就泄露了预测结果。代码尚未实现，列为 D13 | 盲审要求 |
| R8 | **探针结论要先过校准关卡才能用来改计划**（另一会话审阅后加入）：同一个 prompt 换不同分析器模型重跑，检查分析器之间的一致率，再人工抽查。关卡定义见 [02-task1.md](02-task1.md) §0 的 G1–G3。模型分工固定为：**分析器 Opus 5.5，审阅器 Opus 5**（不用 Sonnet：分析和审阅都需要较强的模型），预测模型仍是 deepseek-flash | v3 → v3b → v3c 每改一版，结论就从一个极端跳到另一个极端，工具还不稳定 |
| R9 | `factor`（原名 `decisive_feature`，阶段 B 里叫 `factor`）统一作为边界或标签对下面的子键：`severity-3\|4 / factor=…`、`driver:<A>\|<B> / factor=…` | 避免另起一套分组口径 |
| R10 | **「特征相同、等级不同」的样本对先分两类**：能说出区别的，用作对比示例和回测；说不出区别的，当作噪声，只用来估计提升上限 | 否则同一批样本对会同时被当成教学示例、回测约束和噪声证据，三者目的互相矛盾 |

| R11 | **分析器按任务分开**：三个任务的错误形态不同（Task 1 是等级的尺度，Task 2 是标签个数与易混标签），分析器的判断层类别和一致性检查也不同。做法是 prompt 按任务分文件（`prompts/single/<task>/analyst_v3d_*.txt`），代码共用、按任务分支（`agentic.py` 的 `CATEGORIES` 与 `consistency_check`）。已知风险：Task 2 校准时如果要改分析器，Task 1 与 Task 2 的分析器就不再是同一版；届时用 `<task>-analyst-v<N>` 分别编号，报告里写清各任务用的是哪一版。如果改动变大，再考虑拆成按任务的独立模块 | 用户 2026-11-07 提出，先记录，不一定改 |

修订后新增的代码：

| 编号 | 文件 | 改动 | 状态 |
| --- | --- | --- | --- |
| D12 | `src/agentic.py` | `export --stage a/b/b2` 与 `import`：文件交接、重问（re-ask）排队、导入后统计与抽查表 | 已实现 |
| D13 | `src/agentic.py` | Task 2 的标签名遮盖（`mask_labels`），以及标签集合的盲选（`favoured_labels`） | 已实现（2026-11-07） |
| D14 | `src/agentic.py` | `repair` 的文件交接模式：Claude 写 patch，deepseek 跑回测（用户 2026-11-07 决定写 patch 也用 Claude） | 未实现，Task 1 第 3 步前补上 |

## 1. 为什么要做这一轮

上一轮 trace2skill（轨迹蒸馏，即从模型的错例里提炼规则、写进 prompt）在三个任务上都没有起作用：

- Task 1 无推理版：dev MAE（Mean Absolute Error，平均绝对误差）从 0.266 变差到 0.350，有显著差异；
  有推理版从 0.238 变差到 0.336，处在显著边界。见 [results/SUMMARY.md](../../results/SUMMARY.md)「主要结论」第 3 条。
- 在 train_val 上复查（`results/_smoke/task1/zero-shot-answer-v1/20261104-083500` 对比 `zero-shot-answer-v2/20261104-083512`），
  它把 14 条真实 1 级判成了 2 级，3→4 的混淆也没有减少。

逐条对照 Trace2Skill 原论文（读稿见 [reading-notes-trace2skill.md](../reading-notes-trace2skill.md) §3）之后，
我们的实现和论文有四处不同。这四处就是本轮要补上的：

| | 原论文 | 我们上一轮（`src/analyst.py`、`src/merge_lessons.py`） | 本轮 |
| --- | --- | --- | --- |
| 错误分析方式 | ReAct 循环（Reasoning + Acting，边推理边调用工具的 agent 循环），可以反复尝试 | 两次固定调用（先解释、再写规则），中间只检查引文是否出自原文 | **改成循环**，见 §5 |
| 修法验证 | 每条候选修法都重新运行回测 | 只让分析器「声称」不会弄坏邻近样本，并没有真的重跑 | **每条 patch 都真跑回测**，见 §5 |
| 找不到因果解释的失败 | 直接丢弃 | 102/102 全部保留（`results/analysis/task1/20261104-082558/lessons.jsonl` 的 `status` 全是 `kept`） | **丢弃**，见 §4.4 |
| 合并 | 层次合并，去重并**消解冲突** | 按「真实等级 vs 预测等级」的方向分组，组内各自合并，组与组之间**不检查冲突** | **按边界分组 + 合并后整体回测**，见 §6 |

论文里的成功分析师（𝒜⁺，从判对的样本里提炼可复用做法）**本轮不做**，记入 TODO（§9）。

## 2. 新的预测输出格式：`facts` 线

### 2.1 为什么是新的格式线，而不是 `reason-v3`

按 [单任务共用设计](../single-task/00-common.md) §3.1 的约定，**版本号只表示同一件东西的第几次迭代，
内容上的分叉属于名字**。把输出从「一段推理」改成「事实 + 判断」是换了输出格式，
所以要新开一条格式线（lineage，即一类输出格式），不能占用 `reason` 线的版本号：

| 标识 | 内容 |
| --- | --- |
| `<task>-facts-v1` | 基础指令（与 `reason-v1` 相同的定义部分）+ 「先列事实、再写判断、最后给标签」的输出格式 |
| `<task>-facts-v2` | `facts-v1` + 本轮智能体式蒸馏出的规则 |

`facts-v1` 和 `reason-v1` 只差输出格式，两者构成单变量对照。

### 2.2 输出 JSON 结构

```json
{"facts": [
   {"quote": "从轨迹里逐字复制的一段原文", "note": "这段原文说明了什么（一句话）"},
   ...
 ],
 "judgment": "把上面的事实对到等级/标签定义上的判断，至多 80 词",
 "answer": {"risk_severity": 3}}
```

- `facts` 写 2–6 条。`quote` 必须是轨迹的连续子串，这样代码就能机械地检查事实是否真的出自原文，
  事实层的审查就不再依赖分析器的判断（§4.2）。
- `facts` 必须覆盖：最终动作实际做了什么；它作用在什么资源或信息上（这些内容常常来自 history，
  例如 `mailctl send --draft X` 的草稿内容）；收件方或影响范围；有没有授权、确认或撤回手段。
- `judgment` 只能引用 `facts` 里已列出的事实，不得引入新事实。
- 这个结构也落实了用户提出的「分步阅读」想法（先抽取动作 × 资源，再判断），只是把步骤放在输出里，
  而不是写在 prompt 的操作流程里。如果日后要做真正的分步 prompt，那是另一个实验（§9）。

few-shot 的示例仍然只给标签，与 `reason-v1` 的处理方式相同（`prompts/single/task1/zero_shot_reason_v1.txt` 倒数第二段）。

### 2.3 数据依据

train 里最终动作很短（少于 60 字符）的样本有 95 条，其中 75 条（79%）是 3 级或更高，
例如 `mailctl send --draft QP-73146`（AGENTRISK-030，4 级）、`ledgerctl payment release ST-8841 --confirm`（AGENTRISK-083，4 级）。
这类动作的风险完全由 history 里的内容决定。所以 `facts` 必须要求模型说清「这个动作作用在什么东西上」。
统计脚本写在 [02-task1.md](02-task1.md) §2。

## 3. 新的分析器：两阶段，先盲审、后看答案

### 3.1 上一轮的逻辑陷阱

上一轮的 `prompts/single/task1/analyst_reason_explain.txt` 有三个问题：

1. **第 1 步要求先解释为什么标准答案是对的**，分析器在审查推理之前就被答案锚定了。
2. **第 3 步要求「找出推理第一个出错的地方」**，预设了推理一定有错。
3. **`sound_but_wrong` 被锁死**：第 5 步几乎总说「严格按 instruction 会得到标准答案」（102 条里有 99 条）。
   既然 instruction 指向标准答案、模型却答错了，就只能是「读错」，`sound_but_wrong` 永远选不上。

结果是同一条记录自相矛盾。例如 AGENTRISK-040：`reasoning_fault = misread_evidence`（理解错误），
`root_cause_type = severity_anchor`（等级定义不清，属于尺度问题），而它自己写的 `gold_basis` 里也写着 "a precise home address"。
全部 102 条中，84 条标成读错或漏读，93 条的根因是 severity_anchor。

### 3.2 新流程

| 阶段 | 分析器能看到什么 | 看不到什么 | 产出 |
| --- | --- | --- | --- |
| A 盲审 | 轨迹、最终动作、当前 instruction、模型的 `facts`/`judgment`（或 `reasoning`），**去掉模型给出的等级/标签** | 标准答案、模型的预测值 | 事实层判定；按当前 instruction **自己**会判几级（`blind_implied`）；相邻两级是否都说得通 |
| B 归类 | A 的全部产出 + 标准答案 + 模型的预测值 | — | 判断层判定；是否值得修 |
| C 修复循环 | B 的产出 + 回测工具 | — | 通过回测的 patch，或者丢弃 |

阶段 A 的 `blind_implied` 是关键：它是在**不知道答案的情况下**得出的，所以不受事后合理化偏差
（hindsight bias，即知道答案后总能找出「当时应该看到」的理由）影响，可以拿来和真实值、预测值做机械比较（§4.3）。

### 3.3 prompt 文件

| 文件 | 说明 |
| --- | --- |
| `prompts/single/<task>/analyst_v3d_audit.txt` | 阶段 A，任务相关（要写清楚该任务的事实要点） |
| `prompts/single/<task>/analyst_v3d_classify.txt` | 阶段 B，任务相关（判断层的类别不同，见 §4） |
| `prompts/single/analyst_v3_patch.txt` | 阶段 C 写规则，三个任务共用；在 `analyst_reason_patch.txt` 基础上加「只用通用特征」约束 |

旧的 `analyst_*_explain.txt` / `analyst_*_patch.txt` 一个字都不改，保证上一轮可复算。

## 4. 新的分类

### 4.1 事实层（三个任务共用，阶段 A 判定）

| 值 | 含义 | 判定依据 |
| --- | --- | --- |
| `correct` | 模型列出的事实都有原文支持，也没有漏掉决定性事实 | 每条事实都标为有依据；漏读列表为空 |
| `misread` | 有事实在轨迹里找不到依据（多说了） | 至少一条事实标为无依据，并引用模型原话 |
| `missed` | 轨迹里有决定等级/标签的事实，模型没提（少说了） | 漏读列表不为空，并逐字引用轨迹原文 |
| `misread+missed` | 两者都有 | — |

`facts` 线的 `quote` 先由代码检查是否为原文子串：不是子串的直接记为 `misread` 的证据，不必由模型判断。

### 4.2 判断层（阶段 B 判定，按任务区分）

**三个任务共用的值：**

| 值 | 含义 | 处理 |
| --- | --- | --- |
| `reading` | 错误来自事实层（`misread` / `missed`） | 进入修复循环，规则写成「该看哪个事实」 |
| `target_confusion` | 把 history 里已完成的步骤、或已被拒绝的请求的风险，算到了当前动作头上 | 进入修复循环。注意：用 history 来理解当前动作作用在什么东西上，**是正确做法，不属于这一类** |
| `weighting` | 事实读对了；`blind_implied` 等于真实值；但模型把某个因素放得太重或太轻（例如一看到「注入」就自动升级） | 进入修复循环，规则写成「这个因素单独出现时不足以升/降」 |
| `gold_questionable` | 分析器认为标准答案本身站不住 | **丢弃**，并单独记录供人工复核 |
| `unexplained` | 说不清原因 | **丢弃** |

**Task 1 特有：**

| 值 | 含义 | 处理 |
| --- | --- | --- |
| `threshold` | 事实读对了；`blind_implied` 等于预测值，或者两个相邻等级都说得通；分歧只在于「线划在哪」 | 进入修复循环，规则写成「这条线在哪」，必须和对比示例一起考虑（[02-task1.md](02-task1.md) §5） |

**Task 2a / 2b 特有：**

| 值 | 含义 | 处理 |
| --- | --- | --- |
| `cardinality` | 标签内容有交集，错在个数（真实 1 个预测 2 个，或者反过来） | 进入修复循环 |
| `confusable_pair` | 选成了一个易混的近义标签，例如 Authorization 和 Scope | 进入修复循环，`targets` 必须写明是哪一对 |
| `missed_harm` | history 里涉及的某个受害对象被忽略（例如中途读了财务数据，最后发邮件时漏了 Financial） | 进入修复循环 |

**删掉的旧值及理由：**

| 旧值 | 理由 |
| --- | --- |
| `none_given` | 有推理版和 `facts` 版不会出现；改成代码层面的检查：没有推理就拒绝分析 |
| `wrong_rule` | `v1` 的 prompt 里几乎没有规则可套；等基础 prompt 带了规则（例如 `facts-v2`）再加回来 |
| `no_rule` | 和 `threshold` 重叠：定义里没有对应规则，本来就是「线在哪」没写清 |
| `root_cause_type` 整个字段 | 被判断层取代。它和 `reasoning_fault` 打架正是上一轮矛盾的来源 |

### 4.3 一致性检查（代码完成，不需要模型）

阶段 B 输出后，`src/agentic.py` 的 `consistency_check()` 用下面的规则机械检查。任何一条不满足就算**矛盾**：

| 编号 | 规则 |
| --- | --- |
| K0 | 阶段 A 声明的事实层，必须等于由它自己列出的 claims 和「会改变等级的漏读事实」推出的事实层（2026-11-07 实施时新增） |
| K1 | 判断层为 `reading` ⇔ 事实层不是 `correct` |
| K2 | 判断层为 `threshold` 或 `weighting` ⇒ 事实层为 `correct` |
| K3 | `threshold` ⇒ `blind_implied` 等于预测值，或者阶段 A 标了「相邻两级都说得通」 |
| K4 | `weighting` ⇒ `blind_implied` 等于真实值，并且没有标「两级都说得通」 |
| K5 | 事实层为 `misread` ⇒ 至少引用一段模型原话（必须是模型输出的子串） |
| K6 | 事实层为 `missed` ⇒ 至少引用一段轨迹原文（必须是轨迹的子串） |
| K7 | Task 2：`cardinality` ⇒ 预测集合与真实集合有交集，且个数不同 |
| K8 | Task 1：`gold_questionable` ⇒ `blind_implied` 不等于真实值（2026-11-07 实施时新增） |

K0、K5、K6 是阶段 A 的问题，重问时阶段 A、B 一起重做；其余只重做阶段 B。

出现矛盾时，把违反的规则和相关字段原样发回给分析器，要求重新判定**一次**。还矛盾就标为 `unexplained` 并丢弃。
每次运行都要报告矛盾率；若超过 20%，说明 prompt 本身有问题，要先改 prompt 再继续。

用代码而不是再加一个模型来做这件事，原因是：这些规则都能写成确定的布尔判断，代码检查零成本、可复现，也不会引入第二个模型的偏差。

### 4.4 丢弃规则

以下情况的错例不进入 patch 池，与论文「无法给出因果解释的失败直接丢弃」一致：

1. 判断层为 `gold_questionable` 或 `unexplained`；
2. 一致性检查重试一次后仍然矛盾；
3. 修复循环用完尝试次数仍没有通过回测（§5）；
4. 引文检查不通过（沿用上一轮的检查）。

被丢弃的错例照常写进 `lessons.jsonl`，`status` 写明丢弃原因，便于统计。

## 5. 修复循环（阶段 C）：带回测的 ReAct

### 5.1 流程

每条进入修复循环的错例：

```
for 尝试 in 1..3:
    分析器写 patch（TRIGGER / RULE / COUNTER-EXAMPLE，至多 80 词）
    代码做通用性检查（§5.3）——不过则把原因发回，算一次尝试
    回测：当前 instruction + 这条 patch，在「回测集」上重跑预测模型
    通过（§5.2）→ 保留，结束
    不通过 → 把回测结果（哪些修好了、哪些弄坏了，附原文）发回分析器，下一次尝试
3 次都不通过 → 丢弃
```

### 5.2 回测集和通过标准

**回测集只从 train_evolve 里取，绝不用 train_val 和 dev。**train_val 是用来做选择的「模拟考」，
如果在修复循环里反复用它，它就变成了调参集，最后的 train_val 分数就不再可信。

| 组成 | 条数 | 怎么选 |
| --- | --- | --- |
| 目标错例本身 | 1 | — |
| 同类错例 | 至多 5 | train_evolve 里同一类错误（例如同为 3→4）中 BM25 文本最相似的 |
| 当前判对的邻近样本 | 10 | train_evolve 里 BM25 最相似、当前预测正确的样本，**必须包含等级在边界两侧的样本**（Task 1 是相邻等级，Task 2 是含/不含该标签） |

通过标准（三条同时满足）：

1. 目标错例被修好；
2. 判对的邻近样本**一条都不能被弄坏**；
3. 同类错例的净修复数 ≥ 0。

### 5.3 通用性检查（代码完成）

patch 文本里不得出现：样本 ID、人名、邮箱、域名、文件路径、产品或工具的专有名词（从轨迹里抽取专有名词做黑名单）。
规则只能用通用特征描述，例如受影响的人数、收件人数、能否撤回、是否涉及凭据、是否由嵌入指令触发、用户是否明确要求。
目的是防止分析器看过答案后，写出只适用于这一条的规则。

### 5.4 成本估算

预测模型的输入约每条 1.5k token（train_val 上 107 条 zero-shot answer-v1 共 158,266 prompt tokens，
见 `results/_smoke/task1/zero-shot-answer-v1/20261104-083500/metrics.json`）。

单条错例最坏情况下：3 次尝试 × 16 条回测 = 48 次预测调用 ≈ 72k token。
按 Task 1 reason-v1 在 train_evolve 上的 102 条错例计算（`results/_smoke/task1/zero-shot-reason-v1/20261104-082558/triage/summary.md`）：
最坏约 4,900 次调用、约 7.3M 输入 token。另有分析器调用：每条错例 2 次 + 至多 3 次写 patch，dossier 约 4–6k token，合计约 2–3M token。
实际会少很多：大部分错例在阶段 B 就被丢弃，或者第一次尝试就通过。

**先用 `--limit 10` 跑一遍，记下真实成本再放开。**

### 5.5 已知限制

| 限制 | 影响 | 应对 |
| --- | --- | --- |
| 回测样本少（16 条），patch 可能只对这一小块数据有效 | 单条 patch 过关，合并后整体变差 | §6 的合并后整体回测 |
| temperature 0 下仍有微小的随机波动（同配置重跑两次 MAE 差 0.009） | 回测里偶尔会有一条无故翻转 | 通过标准 2 中，被弄坏的那条再重跑一次，两次都错才算弄坏 |
| 分析器和预测模型是同一个模型（deepseek-flash） | 分析能力有上限 | 与论文一致（论文的合并算子也是同一个模型）；之后可用 `--model` 换更强的分析器做对照 |
| 标准答案有噪声 | 有些错例无论如何都修不好 | 允许丢弃；丢弃率本身就是有用的信息 |

## 6. 合并：按边界分组，合并后整体回测

### 6.1 分组改成无方向的边界

上一轮 `src/merge_lessons.py` 的 `theme_of()` 按 `severity-<真实值>-vs-<预测值>` 分组，
于是 `severity-3-vs-4` 和 `severity-4-vs-3` 被分成两组、各自合并，没有人检查它们是否冲突。
`prompts/patches/single/task1/answer_v2/` 里的 3-vs-4 规则和 4-vs-5 规则对「单条敏感记录发给一个人」给出了不同的等级，冲突就是这样来的。

本轮改成**无方向的边界**：`severity-3|4` 同时收「3 判成 4」和「4 判成 3」的 patch，合并时必须写出一条两个方向都适用的规则。
Task 2 按标签对分组：`domain:<A>|<B>`、`driver:<A>|<B>`、`cardinality:<标签>`。

### 6.2 合并后整体回测

所有边界合并完成后，把整份规则装进 instruction，在**完整 train_evolve** 上跑一遍：

- 和基础版比，**任何一个真实等级（或标签）的正确率下降超过 5 个百分点**的，找出责任规则，删掉后重跑；
- 特别检查 1 级（闸门）的正确率，不得低于基础版。上一轮就是这里出了问题。

整体回测通过后，再在 train_val 上跑**一次**，作为选择依据。

## 7. 代码改动清单

| 编号 | 文件 | 改动 |
| --- | --- | --- |
| D1 | `src/run.py` | `SINGLE_VERSION_RE` 加入 `facts`；`LINEAGE_FORMATS` 加 `"facts": "facts-judgment-answer-v1"` |
| D2 | `src/common.py` | `unpack_prediction()` 支持新格式：检查 `facts` 是 2–6 条、各有 `quote` 和 `note`，`judgment` 非空，`answer` 合法；返回 `(answer, {"facts": ..., "judgment": ...})` |
| D3 | `src/run.py` | `raw_responses.jsonl` 记录 `facts` / `judgment`；在 `rec` 里额外存 `facts_quote_ok`（代码检查的子串结果） |
| D4 | `src/analyst.py`、`src/agentic.py`（新） | `analyst.py` 的 `load_reasoning()` 兼容 `facts` 格式；`audit`（阶段 A + B + 一致性检查）和 `repair`（阶段 C 循环）**实施时放进了新文件 `src/agentic.py`**，避免 `analyst.py` 继续膨胀；旧的 `analyst.py run` 保持不变 |
| D5 | `src/analyst.py` | `cmd_probe` 的 `--data` 默认值从 `data/raw/dev.jsonl` 改为 `data/splits/train_evolve.jsonl`，防止误在 dev 上调试 |
| D6 | `src/agentic.py` | 新函数 `consistency_check()` 实现 §4.3 的 K1–K7；`generality_check()` 实现 §5.3 |
| D7 | `src/merge_lessons.py` | 新增 `--boundary` 分组方式（§6.1）；默认行为不变，以便复算上一轮 |
| D8 | `src/regress.py`（新） | 给定 instruction 和 patch 集合，在指定数据上重跑预测，按真实等级/标签输出正确率变化；修复循环和 §6.2 都调用它 |
| D9 | `src/triage.py` | 输出里增加「按边界」的混淆统计，供 §6 和各任务方案使用 |
| D10 | `tests/test_agentic.py`（新；现有测试在 `tests/test_reasoning_output.py`） | 新增 `facts` 格式解析、一致性检查、通用性检查的单元测试 |
| D11 | `Makefile` | 新增 `audit`、`repair`、`merge-boundary`、`regress` 四个入口 |

全部改动必须保证**旧运行可复算**：改完后，用已有运行重算 `metrics.json` 并重跑 `triage.py`，结果必须逐字节一致。
沿用 [单任务共用设计](../single-task/00-common.md) §4 的回归检查方式。

## 8. 版本对照总表

| 标识 | 内容 | 首次出现 |
| --- | --- | --- |
| `<task>-reason-v1` | 已有，基础指令 + 一段推理 | 已有 |
| `<task>-reason-v2` | 已有，上一轮蒸馏 | 已有 |
| `<task>-facts-v1` | 基础指令 + 事实/判断/标签输出 | 本轮 |
| `<task>-facts-v2` | `facts-v1` + 本轮蒸馏规则 | 本轮 |
| `task2a-reason-v3` | `reason-v1` + 「默认单标签」一句话（**基于 v1，不基于 v2**） | [03-task2a.md](03-task2a.md) |

## 9. TODO（本轮不做）

- 成功分析师（𝒜⁺）：从判对的样本里提炼可复用做法，与错误 patch 一起合并。
- 真正的分步 prompt：把「通读 → 列出动作 × 资源 → 判断」写成 prompt 里的操作步骤，而不只是输出格式。
- 自洽采样（self-consistency，多次采样取中位数）：最终提交时再考虑。
- 用概率输出做校准映射：需要先确认官方后续数据的分布不变。
- 分层检索 few-shot：每条样本额外附上最相似的边界两侧样例（Task 1 是 3 级和 4 级）。
