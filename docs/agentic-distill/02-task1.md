# Task 1（风险等级）：`facts` 输出格式 + 带回测的智能体式蒸馏

创建日期：2026-11-07 · 状态：方案；共用代码已实现，§0 的关卡 G1–G3 待做 · 共用设计见 [00-common.md](00-common.md)

前置条件：[00-common.md](00-common.md) §7 的代码改动已完成（2026-11-07）；探针结果见 [01-blind-probe.md](01-blind-probe.md) §8–§9，但要先过 §0 的关卡才能用来改实验顺序。

模型分工：预测模型 deepseek-flash（要提交的系统）；分析器 Opus 5.5；审阅器 Opus 5。


## 0. 2026-11-07 修订（盲测探针之后，用户已同意；按另一会话的审阅意见调整了顺序）

依据：[01-blind-probe.md](01-blind-probe.md) §8、§9。本节优先于后文。

**先校准工具，再根据工具的结论改计划。**探针本身还没被证明可靠：v3 → v3b → v3c 每改一版 prompt，结论就大幅变化；
DeepSeek 和 Claude 两个分析器的结论也不一样。所以下面分成两段：G 段是关卡（gate），T 段要等 G 段通过后才执行。

| 编号 | 关卡（按顺序做） | 通过标准 |
| --- | --- | --- |
| G1 | **拆开混杂**：用 DeepSeek 跑 v3c，样本仍是这 41 条（API 调用，几分钟）。这样「Claude + v3c」与「DeepSeek + v3c」只差分析器模型 | 只是记录：两个分析器在事实层和判断层上的一致率各是多少 |
| G2 | **同一组合重跑一次，看分析器稳不稳定**：Opus 5.5 + v3c 在这 41 条上再独立跑一遍（新的子代理，看不到第一次的结果） | 两次之间判断层一致率 ≥ 70%；不到就说明分类本身不稳定，先改分类再继续 |
| G3 | **人工抽查**：v3c 抽出的 10 条，先交给 **Opus 5** 的新会话审阅（审阅器与分析器用不同模型），用户本人再看 3–5 条 | 事实层 ≥ 8/10，判断层 ≥ 7/10 |

**关卡状态（2026-11-07）**：G1 完成（DeepSeek 不适合做分析器）；G2 在 v3d 上通过（92%）；G3 判断层 7/10 达标、事实层 7/10 差 1 条。
按停止规则，**分析器定版为 v3d**（Opus 5.5，审查 facts 格式的输出）；修复循环只处理两次运行都判为 reading 的样本，其余交给示例。
E1 已完成：facts-v1 在 train_val 上与 reason-v1 无显著差别（0.280 对 0.290），在 train_evolve 上显著更差（0.299 对 0.247）。详见 [01-blind-probe.md](01-blind-probe.md) §12–§13。

**用户决定（2026-11-07）：本轮整条线用 facts。**facts-v1 是为了便于诊断和蒸馏而设计的脚手架，不单独比较它的优劣；
真正参与比较的是蒸馏之后的 facts-v2（以及 facts-v2 + few-shot）。数据集分工不变：

| 数据 | 用途 |
| --- | --- |
| train_evolve（461 条） | 跑 facts-v1 找错例 → 分析器诊断 → 修复循环写规则、做回测 → 合并后整体回测。规则**从这里学** |
| train_val（107 条） | 规则定稿后只跑一次，和 answer-v1、reason-v1 的 train_val 结果比较，决定是否上 dev。规则**不从这里学** |
| dev（143 条） | 最终只跑一次 |

注意：facts-v1 在 train_evolve 上起点更低（判高更多），facts-v2 要先把这段差距补回来，才谈得上比 reason-v1 好。

G1–G3 都通过后，执行下面的 T 段（**本轮只执行 T2、T5、T6、T7；T1、T3 的对比示例部分和 T4 移到下一轮**，见 §0.1）：

| 编号 | 修订 |
| --- | --- |
| T4 | **先估计标注噪声，并把样本对分成两类**（原 T4，提前到最前面）。在 train_evolve 里，对同一边界（`severity-3\|4`）下 `factor` 相同的样本两两配对，挑出真实等级不同的对，逐对判断：<br>① **能说出区别**（例如「都是单人隐私泄露，但一个含完整卡号，一个不含」）：可以当对比示例（T1），也放进回测集（T3）；<br>② **说不出区别**：算作噪声，排除在示例和回测之外，只用来估计提升的上限。<br>040 配 464 这一对也要先过这一步，才能当示例用 |
| T1 | **E4（固定对比示例）升为主实验**，但只用 T4 里第 ① 类的样本对 |
| T3 | **修复循环的回测集**必须包含第 ① 类中「同一 `factor`、真实等级在另一侧」的样本；第 ② 类不放进回测集，否则任何规则都不可能两侧都对，所有 patch 都会被拒掉 |
| T2 | **E1（`facts-v1`）照做，它负责修阅读错误那一部分。**此条只适用于 Task 1 的 3/4 边界；Task 2 没做过探针，03 / 04 的 E1 不受影响 |
| T5 | **分析器与预测模型分开**（00 §0 的 R1）。修复循环里由 Claude 写 patch（文件交接），回测重跑预测仍用 deepseek-flash；先 `--limit 10` |
| T6 | 分析器 prompt 用 v3c（00 §0 的 R2–R4） |
| T7 | **`factor` 作为边界下面的子键**，与 00 §6.1 的分组对齐：`severity-3\|4 / factor=单个收件人`。T1、T3、T4 找样本对时都按这个口径 |

## 0.1 本轮执行清单（2026-11-07 定稿，优先于 §0 的 T 段和 §2–§5）

本轮与 [单任务实验](../single-task/00-common.md) §2 的设计平行，只是换成 facts 格式线，并改用新的蒸馏方式。各数据集的用途照旧：

| 实验 | 跑在哪 | 说明 |
| --- | --- | --- |
| zero-shot 基线 | dev | 与 single-task 相同 |
| few-shot | dev | **只跑 BM25 k=10**（不跑 random、k=3/5/20，节省 token）；示例来自 train，选例文件用已有的 `data/fewshot/bm25_dev_top10.json`。已知风险：reason 线上 k=10 最好，换成 facts 格式后最好的 k 可能移位；如果 facts-v2 + k=10 的结果可疑，再补 k=5 或 k=20 |
| trace2skill 蒸馏 | train_evolve 学规则 → train_val 记录一次 → **无论结果如何都上 dev** | 与 single-task 相同，只是蒸馏方式换成本轮的智能体式循环 |

**不跑**：random 选例、BM25 k=3/5/20、对比示例、T4 噪声估计、分步 prompt、成功分析师。这些移到下一轮。

### 准备

| 编号 | 内容 | 状态 |
| --- | --- | --- |
| P1 | `prompts/single/task1/zero_shot_facts_v1.txt` | 已有 |
| P2 | `prompts/single/task1/few_shot_facts_v1.json`：few-shot 的**消息组装规范**（不是选例文件），和已有的 `few_shot_reason_v1.json` 同一格式。示例只给标签，在最后一条用户消息末尾提醒模型「这一条按系统指令输出 facts、judgment、answer」 | 待新建 |

### 运行矩阵

| 步 | 数据 | 运行 | 状态 |
| --- | --- | --- | --- |
| 1 | train_evolve | facts-v1 zero-shot（蒸馏的错例来源） | **已完成** `20261107-082751`，MAE 0.299 |
| 1 | train_val | facts-v1 zero-shot | **已完成** `20261107-082951`，MAE 0.280 |
| 2 | dev | facts-v1 zero-shot、facts-v1 + BM25 k=10 | 待跑 |
| 3 | train_evolve | **蒸馏**（见下）→ facts-v2 zero-shot 整体回测 | 待跑 |
| 4 | train_val | facts-v2 zero-shot，记录一次 | 待跑 |
| 5 | dev | facts-v2 zero-shot、facts-v2 + BM25 k=10 | 待跑 |

dev 上一共 4 个运行，与已有的 answer-v1、reason-v1 在 dev 上的 zero-shot 和 BM25 k=10 结果并列，写进 `results/SUMMARY.md`。

### 第 3 步：蒸馏流程

1. **诊断**：对 facts-v1 在 train_evolve 上的全部错例（128 条）运行 v3d 分析器，用 Opus 5.5 通过文件交接独立跑**两次**（`src/agentic.py export / import`）。
2. **筛选**：只有**两次都判为 reading** 的样本进入修复循环（01 §13 的定版规则）。scale 类不写规则，留给 few-shot。
3. **修复循环**：**写 patch 用 Claude（Opus 5.5，文件交接），回测重跑预测用 deepseek**（deepseek 是最终要提交的预测模型）。
   每次尝试是一轮交接：代码导出「待写 patch」文件 → Claude 子代理写 patch → 代码做通用性检查并用 deepseek 跑回测 → 导出回测结果（修好了哪些、弄坏了哪些）→ 下一次尝试。
   - 回测集：目标错例 + 至多 5 条同类错例 + 10 条当前判对的邻近样本（边界两侧各一半），只取自 train_evolve；
   - 通过标准：目标修好、判对的样本一条都不能弄坏（弄坏的重跑一次确认）、同类错例净修复 ≥ 0；
   - 最多尝试 3 次，不过就丢弃。
   - 需要先补代码 D14（`agentic.py repair` 的文件交接模式），见 [00-common.md](00-common.md) §0。
4. **合并**：`src/merge_lessons.py merge --boundary`，无方向边界分组（`severity-3|4` 等），`severity-1|2` 组默认不收。
5. **组装**：`src/assemble_instruction.py`，以 `zero_shot_facts_v1.txt` 为底，生成 `zero_shot_facts_v2.txt`，同时建 `few_shot_facts_v2.json`。
6. **整体回测**：facts-v2 zero-shot 跑完整 train_evolve，`src/regress.py compare` 对比 facts-v1：任一真实等级的正确率下降不超过 5 个百分点，1 级（闸门）不下降；不满足就删掉责任规则重来。
7. 通过后，第 4、5 步各跑一次。**结果不好也不回头改规则**；要改就开 facts-v3，从第 3 步重来。

### 结果怎么读

| 比较 | 回答什么问题 |
| --- | --- |
| facts-v2 vs facts-v1，zero-shot（train_val 与 dev） | 新蒸馏方式写出的规则有没有用；同时看 1 级正确率有没有下降 |
| facts-v2 + k=10 vs facts-v1 + k=10（dev） | 规则加在示例之上还有没有用（上一轮 v2 在这里没有增益） |
| facts 线 vs reason-v1、answer-v1（dev，同为 zero-shot 或同为 k=10） | 结构化推理加新蒸馏，整体是否胜过已有方案 |
| facts-v2 vs reason-v1，zero-shot（train_val） | 已有 reason-v1 的 train_val 结果（`20261104-083523`，MAE 0.290），可直接对比 |

显著性一律用 `src/paired_bootstrap.py` 判断。

### 预算

| 项 | 估算 |
| --- | --- |
| 第 2、5 步：dev 4 个运行（143 条） | zero-shot 每个约 0.3M，k=10 每个约 2M，合计约 5M 输入 token |
| 第 3 步诊断：128 条 × 2 次 | 约 40 个子代理批次（Claude，不走 API） |
| 第 3 步修复：只处理两次都判 reading 的样本（按探针比例估计 40 条左右） | 回测预测（deepseek）最坏 40 × 3 × 16 ≈ 1,900 次，约 3M token；写 patch 由 Claude 子代理完成，最多 3 轮交接、每轮约 6–8 个批次 |
| 第 3 步整体回测、第 4 步 | 约 1.2M token |

## 1. 现状（全部来自 train 一侧，不用 dev）

| 运行 | 数据 | MAE | 来源 |
| --- | --- | --- | --- |
| reason-v1 zero-shot | train_evolve 461 条 | 0.247 | `results/_smoke/task1/zero-shot-reason-v1/20261104-082558/triage/summary.md` |
| reason-v1 zero-shot | train_val 107 条 | 0.290 | `results/_smoke/task1/zero-shot-reason-v1/20261104-083523` |
| reason-v2（上一轮蒸馏） | train_val 107 条 | 0.374 | `results/_smoke/task1/zero-shot-reason-v2/20261104-083543` |

train_val 上 reason-v1 → reason-v2 的变化：修好 14 条（其中 9 条是 4→3 修回 4）；弄坏 22 条（其中 **11 条 1 级变成 2 级**、10 条 3 级变成 4 级）。

本任务已知的三个问题：

1. 3/4 边界是主要误差来源；
2. 闸门（1 级和非 1 级的区分）本来几乎全对，上一轮的规则把它弄坏了；
3. 上一轮的 3-vs-4 规则和 4-vs-5 规则互相矛盾（[00-common.md](00-common.md) §6.1）。

## 2. 实验 E1：输出格式（`facts-v1` 对比 `reason-v1`）

**唯一的变量是输出格式。**`facts-v1` 的定义部分与 `reason-v1` 逐字相同，只替换最后的输出格式说明（[00-common.md](00-common.md) §2.2）。

### 2.1 prompt 里要写的事实要点（Task 1 专用）

`facts` 至少覆盖：

1. 最终动作实际执行了什么（发送 / 删除 / 修改 / 付款 / 只读 / 拒绝……）；
2. 它作用在什么资源或信息上，内容通常要去 history 里找；
3. 影响范围：几个人、几条记录、几个收件人；
4. 这个动作是不是由用户明确要求的，还是由嵌入在数据里的指令触发的；
5. 能否撤回，有没有确认步骤或其他保护措施。

不需要额外写规则，这里只规定模型应该列出哪些事实。

### 2.2 运行

| 运行 | 数据 | 用途 |
| --- | --- | --- |
| `facts-v1` zero-shot | train_evolve 461 条 | E2 的蒸馏基础 |
| `facts-v1` zero-shot | train_val 107 条 | 和 reason-v1（`20261104-083523`）对比 |

```bash
.venv/bin/python src/run.py --task task1 --version facts-v1 --strategy zero-shot --split train_val --data-file data/splits/train_val.jsonl --concurrency 8
.venv/bin/python src/paired_bootstrap.py results/_smoke/task1/zero-shot-reason-v1/20261104-083523 results/_smoke/task1/zero-shot-facts-v1/<run_id> --metric mae
```

### 2.3 要报告的指标

- MAE 和配对自助法（paired bootstrap）的 95% 置信区间；
- 按真实等级拆开的正确率，尤其是 1 级（闸门）；
- `facts` 引文的原文命中率（`facts_quote_ok` 的比例）；
- 输出 token 的增量。

### 2.4 决策

| 结果 | 决定 |
| --- | --- |
| `facts-v1` 不比 `reason-v1` 差（置信区间跨 0，或者整体在更好的一侧） | E2 以 `facts-v1` 为基础，因为它的事实层可以机械审查 |
| `facts-v1` 显著更差 | E2 以 `reason-v1` 为基础，蒸馏结果命名为 `reason-v3`；`facts` 格式留作分析工具，不进入主线 |

另外附一个离线统计（不调用 API，写进本次 `summary.md`）：train 里最终动作短于 60 字符的样本按真实等级的分布，
以及 `facts-v1` 在这些样本上是否列出了「作用对象」这一条事实。

## 3. 实验 E2：智能体式蒸馏（`facts-v2`）

### 3.1 流程

```
E1 的 train_evolve 运行
  → triage（按边界统计混淆，D9）
  → audit：阶段 A 盲审 + 阶段 B 归类 + 一致性检查（01 已验证过的 prompt）
  → repair：修复循环，回测集只来自 train_evolve（00 §5）
  → merge：按边界合并（00 §6.1）
  → regress：完整 train_evolve 整体回测（00 §6.2）
  → assemble：生成 prompts/single/task1/zero_shot_facts_v2.txt
  → train_val 跑一次 → 记录
  → dev 跑一次（无论结果好坏）
```

### 3.2 哪些错例进入修复循环

| 判断层 | 是否进入 | 规则写法要求 |
| --- | --- | --- |
| `reading` | 是 | 指明「该看哪个事实」，例如「判断泄露等级前，先确认导出里实际包含哪些字段」 |
| `target_confusion` | 是 | 指明「当前动作」与「history 里已完成或已拒绝的步骤」的区别 |
| `weighting` | 是 | 写成「X 单独出现时不足以升到 4」这种形式 |
| `threshold` | 是，但**必须走 §3.3 的边界合并** | 只能用通用特征描述 3/4 之间的线 |
| `gold_questionable` / `unexplained` | 否，丢弃 | — |

### 3.3 Task 1 的边界和需要特别保护的东西

- 边界分组：`severity-1|2`、`severity-2|3`、`severity-3|4`、`severity-4|5`。
- **`severity-1|2` 的规则默认不收。**闸门在 reason-v1 上的错误只有约 0.03 MAE（dev 和 train_val 上都是 4–5 条），
  上一轮唯一一条闸门规则却弄坏了 11–14 条。只有在完整 train_evolve 整体回测中，**1 级正确率不下降**的前提下，才接受这一组规则。
- `severity-3|4` 合并时，必须同时满足两个方向：「3 判成 4」的 patch 和「4 判成 3」的 patch 要合成**一条**规则，并在两侧样本上同时回测。
- 上一轮 4-vs-5 规则中「5 级只留给大规模、系统性伤害」这半句，在 train_val answer 线修好了 5 条 4→5 的高估。
  可以作为 `severity-4|5` 组的候选种子，但同样要通过回测才能保留。

### 3.4 验收

| 检查点 | 标准 |
| --- | --- |
| 完整 train_evolve 整体回测 | MAE 低于 `facts-v1`；任何真实等级的正确率下降不超过 5 个百分点；1 级不下降 |
| train_val（只跑一次） | 记录 MAE 和置信区间，不再据此改规则 |
| dev（只跑一次） | 写进 `results/SUMMARY.md` |

**train_val 结果不好也不回头改规则。**要改，就新开 `facts-v3`，从 train_evolve 重新开始。

## 4. 实验 E3：few-shot 叠加

蒸馏的最终目标是「更好的 instruction + few-shot」优于「v1 + few-shot」。为保证单变量，对照组用**同样的 few-shot 配置**：

| 对照 | 实验 | 数据 |
| --- | --- | --- |
| `reason-v1` + BM25 k=10 | `facts-v2` + BM25 k=10 | train_val（选择文件 `data/fewshot/bm25_train_val_top10.json`，已在库） |

dev 上的对比只在最后跑一次，k 取 dev 已有结果里最好的两档（10 和 20）。

如果在 train_val 上「`facts-v2` + few-shot」不优于「`reason-v1` + few-shot」，就说明规则和示例在互相抵消。
这时查看 `facts-v2` 规则对应的那条边界上，检索到的示例标的是什么等级，判断是不是规则和示例在打架（上一轮 v2 疑似就是这样）。

## 5. 实验 E4：固定的对比示例（移到下一轮，见 §0.1）

只有当 [01-blind-probe.md](01-blind-probe.md) 显示 3→4 错例中「事实层为 correct」的占比 ≥ 40% 时才做。

- 从 **train_evolve** 中挑 3 对「场景相近、等级不同」的 3 级 / 4 级样本，写成固定段落放进 instruction。
  挑选方法：对每个 3 级样本找 BM25 最相似的 4 级样本，按相似度排序后人工审核前 10 对，选 3 对差异最清楚的。
- 版本：`facts-v3` = `facts-v1` + 对比示例段落（单变量，**不叠加 v2 的规则**）。
- 如果 `facts-v2` 和 `facts-v3` 都有效，再做 `facts-v4` = 规则 + 对比示例。
- 对比示例与 `severity-3|4` 规则的关系：两者针对同一条边界，规则是文字描述，示例是具体展示。
  `facts-v4` 里每条 3/4 规则后面紧跟一对示例。

## 6. 预算

| 项 | 估算 |
| --- | --- |
| E1：两个 split 各一次 | 568 次调用，约 0.9M 输入 token |
| E2：audit + repair + regress | 见 [00-common.md](00-common.md) §5.4：最坏约 10M token；先 `--limit 10` 实测 |
| E3：train_val 两格 | 约 3M token（k=10 时每条约 13–15k token，按 dev 上 k=10 的 1.85–2.11M / 143 条推算，见 `results/SUMMARY.md` 附录） |
| E4 | 与 E1 相当 |

## 7. 给 Task 2a / 2b 留的接口

Task 1 跑通后，2a / 2b 直接复用以下部分，各自方案里只写不同之处：

- `src/analyst.py audit / repair` 两个子命令，以及一致性检查 K1–K6；
- `src/regress.py`；
- `merge_lessons.py --boundary`（2a / 2b 的分组键见各自方案）；
- `facts` 格式解析。

需要按任务修改的部分：

| 部分 | Task 1 | Task 2a / 2b 要改成 |
| --- | --- | --- |
| 判断层专属值 | `threshold` | `cardinality`、`confusable_pair`、`missed_harm` |
| 一致性检查 | K1–K6 | 再加 K7 |
| 事实要点（§2.1） | 动作、对象、范围、来源、可撤回性 | 受影响的对象/资产（含 history 里涉及的）/ 风险成因 |
| 回测的「判对邻近样本」 | 边界两侧等级各一半 | 含该标签和不含该标签各一半 |
| 特别保护 | 1 级闸门 | `No Material Harm` / `No Material Risk` 必须单独出现（与 1 级同一批 262 条） |

## 8. 执行记录（2026-11-07）

**第 2 步（dev）**：facts-v1 zero-shot MAE 0.238（`task1/zero-shot-facts-v1/20261107-091705`），与 reason-v1 的 0.238 持平（配对差 +0.000 [-0.077, +0.077]）；
facts-v1 + BM25 k=10 MAE 0.210（`task1/few-shot-bm25-k10-facts-v1/20261107-091743`），对比 reason-v1 + k=10 的 0.189，差 +0.021 [-0.021, +0.070]，噪声。

**第 3 步 诊断**：facts-v1 在 train_evolve 上的 128 条错例，用 v3d 分析器（Opus 5.5）独立跑两次
（`results/analysis/task1/20261107-082751-audit-v3d-full-r1`、`-r2`）。两次在「读错 / 尺度」两大类上的一致率是 104/128 = 81%（G2 标准 70%）。
第 1 次：scale 82、reading 44；第 2 次：scale 84、reading 42。两次都判为 reading 的有 32 条，进入修复循环。

**第 3 步 修复循环**（`results/analysis/task1/20261107-082751-repair-v1`，Claude 写 patch，deepseek 回测）：

| 轮次 | 通过 | 说明 |
| --- | --- | --- |
| 第 1 次尝试 | 2 | 24 条修好了目标、但弄坏了判对的样本；4 条被通用性检查误拒（见下）；1 条没修好目标 |
| 第 2 次尝试 | 累计 5 | 第 3 次之前，把被弄坏样本的真实等级、改后等级和动作开头也交给写 patch 的模型 |
| 第 3 次尝试 | 累计 10 | 22 条三次都没通过，丢弃 |

实施中修的两个问题：
- 通用性检查把句首的普通词（Check、Access、Before）当成了专有名词，误拒 4 次。已改为只检查句中的大写词，并补了测试。
- 写 patch 的模型原来只看得到被弄坏样本的 ID，看不到内容。从第 3 次尝试起附上样本摘要。

**合并**：10 条通过的 patch 中，`severity-1|2`（闸门）组的 1 条按规则不收。其余 9 条（3|4 边界 7 条、2|3 边界 2 条）的触发条件都很窄，
每条都单独通过了回测，所以**按原文逐条收录、没有用模型改写合并**（与 §0.1 第 4 步不同：那里设想的是一组 patch 合成一条）。
规则文件在 `prompts/patches/single/task1/facts_v2/`，组装出 `zero_shot_facts_v2.txt`（565 → 1244 词）和 `few_shot_facts_v2.json`。

**整体回测**（facts-v2 zero-shot，完整 train_evolve，`results/_smoke/task1/zero-shot-facts-v2/20261107-094051`，460/461 条；AGENTRISK-623 五次都输出了不合规的格式）：

| 真实等级 | facts-v1 正确率 | facts-v2 正确率 | 变化 | n |
| --- | --- | --- | --- | --- |
| 1（闸门） | 0.953 | 0.972 | +0.019 | 215 |
| 2 | 0.308 | 0.346 | +0.038 | 26 |
| 3 | 0.392 | 0.588 | **+0.196** | 102 |
| 4 | 0.684 | 0.750 | +0.066 | 114 |
| 5 | 0.500 | 0.250 | **-0.250** | 4 |

MAE：facts-v1 0.298 → facts-v2 0.228，差 -0.070 [-0.107, -0.030]，**显著变好**；对比 reason-v1 的 0.246，差 -0.017 [-0.059, +0.022]，噪声。
（因为缺 1 条，这两个置信区间是在 460 条共同样本上自行计算的配对自助法结果，`src/paired_bootstrap.py` 要求样本完全一致。）

**待决定**：5 级的正确率下降了 25 个百分点，超过了「不超过 5 个百分点」的标准。但 5 级只有 4 条，变化的只是一条（AGENTRISK-301，从 5 判成 4）。
这个标准原本是为样本数足够多的等级设计的。按原规则，要找出导致这条变化的规则并删掉；也可以记录为小样本例外、照常进入第 4 步。
**这一点需要用户决定后，才跑第 4 步（train_val），以免先看到 train_val 结果再改规则。**

**用户决定（2026-11-07）**：5 级的下降按小样本例外处理（4 条中变化 1 条），不删规则，照常进入第 4 步。以后的整体回测中，「不超过 5 个百分点」只适用于样本数 ≥ 10 的等级。

**第 4、5 步结果**（Task 1 本轮全部跑完）：

| 数据 | 配置 | facts-v1 | facts-v2 | 差值 [95% CI] | 对比 reason-v1 | 对比 answer-v1 |
| --- | --- | --- | --- | --- | --- | --- |
| train_val | zero-shot | 0.280 | **0.271** | -0.009 [-0.084, +0.065] 噪声 | 0.290，差 -0.019 噪声 | 0.364，差 -0.093 [-0.187, +0.000] 边界 |
| dev | zero-shot | 0.238 | **0.182** | -0.056 [-0.126, +0.014] 噪声（P=0.93） | 0.238，差 -0.056 [-0.119, +0.007] 噪声（P=0.94） | 0.266，差 -0.084 [-0.147, -0.021] **显著更好** |
| dev | BM25 k=10 | 0.210 | 0.210 | +0.000 [-0.063, +0.063] 噪声 | 0.189，差 +0.021 噪声 | 0.196，差 +0.014 噪声 |

运行目录：train_val `results/_smoke/task1/zero-shot-facts-v2/20261107-094651`；dev zero-shot `task1/zero-shot-facts-v2/20261107-094719`；dev k=10 `task1/few-shot-bm25-k10-facts-v2/20261107-094801`。
dev 的两个运行各有 2 条第一次输出格式不合规，续跑后补齐到 143/143。

dev zero-shot 按真实等级（facts-v1 → facts-v2）：1 级 1.000 → 1.000（66 条）、2 级 0.250 → 0.375（8）、**3 级 0.344 → 0.531**（32）、4 级 0.857 → 0.886（35）、5 级 0.500 → 0.000（2）。

**怎么读**：

1. **规则在 zero-shot 上有用，方向一致。**train_evolve 显著变好；dev 上 0.238 → 0.182，P(更好) = 0.93，但置信区间刚好跨过 0；train_val 是噪声。
   facts-v2 zero-shot 的 0.182 是本项目 dev 上目前最好的 zero-shot 结果，与最好的 few-shot（reason-v1 + BM25 k=20 的 0.154）差 +0.028 [-0.028, +0.084]，属于噪声。
2. **改善集中在 3 级**：train_evolve +19.6 个百分点，dev +18.8 个百分点。这正是规则针对的 3/4 边界。闸门（1 级）不变。
3. **规则加在示例之上没有额外收益**：dev k=10 下 facts-v1 与 facts-v2 都是 0.210。与上一轮 v2 的现象相同：示例已经提供了规则所含的信息。
4. **5 级在两个数据集上都下降了**（train_evolve 4 条中少对 1 条，dev 2 条中少对 1 条）。样本很少，但方向一致：3/4 边界的规则里有「封顶到 4」的写法，可能把个别 5 级拉了下来。下一轮要专门检查。

**补跑 BM25 k=5（dev，用户 2026-11-07 要求）**：

| 配置 | zero-shot | k=5 | k=10 |
| --- | --- | --- | --- |
| facts-v1 | 0.238 | 0.245（`few-shot-bm25-k5-facts-v1/20261107-095338`） | 0.210 |
| facts-v2 | **0.182** | 0.225（`few-shot-bm25-k5-facts-v2/20261107-095414`，142/143） | 0.210 |
| reason-v1（with reasoning） | 0.238 | 0.210 | 0.189 |
| reason-v2（with reasoning + 上一轮蒸馏规则） | 0.336 | 0.322（`20261107-100033`） | 0.266（`20261107-100101`） |
| answer-v1（without reasoning） | 0.266 | 0.238 | 0.196 |
| answer-v2（without reasoning + 上一轮蒸馏规则） | 0.350 | 0.273（`20261107-100131`） | 0.217（`20261107-100147`） |

reason-v2 / answer-v2 的 few-shot 是 2026-11-07 补跑的（`prompts/single/task1/few_shot_{reason,answer}_v2.json`，与 v1 同格式）。
上一轮蒸馏规则加在示例上：reason k=5 显著变差 +0.112 [+0.035, +0.189]；reason k=10 +0.077 [-0.007, +0.161]、answer k=5 +0.035、answer k=10 +0.021 均为噪声，方向都是变差。
本轮的 facts-v2 是唯一在 zero-shot 上改善、在 few-shot 上不变差的蒸馏版本。

facts-v2 k=5 缺 AGENTRISK-580：18 次尝试都输出了多余的键，格式不合规。下面的比较是在 142 条共同样本上自行计算的配对自助法结果：

- facts-v2 k=5 vs facts-v1 k=5：0.239 → 0.225，差 -0.014 [-0.070, +0.042]，噪声；
- facts-v2 k=5 vs reason-v1 k=5：0.204 → 0.225，差 +0.021 [-0.042, +0.085]，噪声；
- facts-v2 k=5 vs facts-v2 zero-shot：0.176 → 0.225，差 +0.049 [-0.007, +0.113]，噪声，但方向是**加示例反而变差**。

**怎么读**：在 facts 格式线上，示例的作用与 reason / answer 线不同。reason 和 answer 线上，加示例都让 MAE 下降；
facts-v2 上，k=5 和 k=10 都不如它自己的 zero-shot。可能原因：示例只给标签，和要求先列事实的输出格式不一致，示例把模型拉离了逐条列事实的做法。
因此 facts 线最好的配置是 **facts-v2 zero-shot（0.182）**。
