# 单任务实验：共用设计

创建日期：2026-11-04 · 修订：2026-11-04（命名方案、k 取值） · 状态：方案，未开跑

本文是三份任务方案的共用部分：命名、目录、代码改动、预算、验收口径。三份可执行方案分别是
[Task 1](01-task1-risk-level.md)、[Task 2a](02-task2a-harm-domain.md)、[Task 2b](03-task2b-risk-driver.md)。
三份方案各自完整，执行时只看自己那一份；但凡涉及改代码、改命名、改目录，一律以本文为准，
避免三份文档各写一套互相漂移。

上游需求见 [下一版提示词实验](../next-prompt-experiments.md) §3、§4（老师提出的 S0 / S1 对照）。

## 1. 这一轮要回答什么

已有的全部正式运行都是**多任务联合预测（multi-task joint prediction，即一次模型调用同时回答多个子任务）**：
一次调用同时输出 `risk_severity`、`risk_domains`、`risk_drivers`。22 个这样的运行见
[results/comparison.md](../../results/comparison.md)。

这一轮做**单任务预测（single-task prediction，即每次模型调用只回答一个子任务）**：
同一条样本分三次独立调用，每次的提示词只讲一个子任务、只要求一个输出字段，
任务之间不传递预测结果，也不提供其他任务的标准答案。

交叉的第二个变量是**判断依据（brief rationale，即让模型先用一两句话说明依据再给标签）**。
照 [next-prompt-experiments.md](../next-prompt-experiments.md) §4 的编号：

| 编号 | 任务方式 | 是否输出判断依据 | 本轮状态 |
| --- | --- | --- | --- |
| M0 | 多任务联合 | 否 | 已有，22 个运行 |
| M1 | 多任务联合 | 是 | 已有，`v4` / `v4b` 共 4 个运行 |
| S0 | 单任务独立 | 否 | **本轮新做** |
| S1 | 单任务独立 | 是 | **本轮新做** |

每个任务各做 S0、S1 两个半版本。

## 2. 每个半版本跑哪几格，各自在哪个数据集上跑

**三类实验的评测集口径不同，照搬现有 multitask 的做法，不是所有格子都跑在同一个集合上。**
口径逐条核对自仓库：

| # | 配置 | 示例从哪来 | 跑在哪 | 现有 multitask 的对应证据 |
| --- | --- | --- | --- | --- |
| 1 | zero-shot 基线 | 无 | **dev**（143 条） | `results/deepseek-flash/zero-shot-v1/20261022-051556/config.json` 的 `split: dev` |
| 2–5 | few-shot BM25 k=3 / 5 / 10 / 20 | **train**（568 条） | **dev** | `data/fewshot/bm25_dev_top10.json`、`bm25_dev_top20.json` 的 selections 是 dev id → train id；`src/select_examples.py` 只读文本不读标签 |
| 6–9 | few-shot random seed 0 k=3 / 5 / 10 / 20 | **train** | **dev** | `data/fewshot/random_seed0.json`、`random_seed0_top20.json` 同上 |
| 10 | trace2skill（轨迹蒸馏，即把失败样本里的教训提炼成指令规则） | 无示例，规则来自 train | 蒸馏在 **train_evolve**（461 条）→ 在 **train_val**（107 条）上记录一次 → **无论结果如何都上 dev** | `prompts/patches/v2/CHANGELOG.md`；[next-round-plan.md](../next-round-plan.md) 的三段式 |

**三个任务口径统一（2026-11-04 定稿）**：k 一律取 3 / 5 / 10 / 20，
**每个半版本 10 格，每个任务 20 格，三个任务合计 60 格 dev 运行**。
选择文件 `bm25_dev_top20.json` 与 `random_seed0_top20.json` 已在库，不需要重新检索。

（本文 11-04 上午曾短暂写成「Task 1 只跑 k=3/5/10」，当天下午按口径统一改回四档；
Task 1 的 k=20 四格已补跑，见 [Task 1 方案](01-task1-risk-level.md) §7。）

其中：

- **zero-shot（无示例预测，即只给任务指令和当前样本）**直接在 dev 上跑，一次。
- **few-shot（少样本预测，即在当前样本前先放若干已标注的 train 样例）**的示例一律来自 `data/raw/train.jsonl`，
  运行在 dev 上。`data/fewshot/` 里的选择文件**不重新检索**，理由见 §6。
- **trace2skill** 是三段式：train_evolve 上跑基线出错例 → 归因、合并成规则、组装成新指令 → train_val 上验证
  → 在 train_val 上记录一次对照，然后**无条件**在 dev 上跑一次。train_evolve / train_val 的 461 / 107 条切分由
  `src/make_splits.py` 按场景组（scenario group）生成，和 dev 无交集。

每个任务因此是 **20 个 dev 运行 + 2 个 train_evolve 运行
+ 4 个 train_val 运行 + 2 轮归因**（S0、S1 各一套）。

## 3. 命名方案

### 3.1 参考的工业界做法

提示词和模型一样，业界通行的是**「名字 + 单调递增的整数版本」**两段式：
MLflow Model Registry 的 `name/version`、LangSmith Prompt Hub 的 `prompt-name:commit`、
HuggingFace Hub 的 `repo@revision`、容器镜像的 `image:tag`。共同点是：

- **版本号只表示「同一个东西的第几次迭代」**，是单调递增的整数，不编码内容；
- **内容上的分叉属于名字，不属于版本号**。两条会各自独立往前走的输出格式线要给两个名字，
  不能挤进同一个版本序列，否则 `v3` 到底是「`v2` 的改进」还是「另一条路线」就说不清了。

本项目的多任务版本号正是吃过这个亏：`v1→v2` 是「加蒸馏规则」，`v2→v3` 是「再加两条规则」，
但 `v4` 却是「换输出格式」、`v5` 又是「v4 加规则」。一条序列里混了两种含义，
所以 [v4 方案](../v4-reasoning-trace2skill-plan.md) §2.1 才要专门写一张表解释谁对应谁。
单任务这一轮不重复这个错误。

### 3.2 本轮的提示词标识：`<task>-<lineage>-v<N>`

| 段 | 取值 | 含义 |
| --- | --- | --- |
| task（任务） | `task1` / `task2a` / `task2b`；旧的多任务是 `multi` | 哪个子任务 |
| lineage（输出格式线） | `answer` / `reason` | `answer` = 只输出标签；`reason` = 先写判断依据再输出标签 |
| v`N`（版本） | `v1`, `v2`, … | 同一条输出格式线的第几版。`v1` = 基础版，`v2` = 加入本任务蒸馏规则版，以后每改一次加一 |

完整标识例：`task1-answer-v1`、`task2b-reason-v2`。

和多任务已有版本的对应关系——**这是本轮结果能和 `results/comparison.md` 并排看的关键**：

| 单任务 | 多任务对应 | 内容 |
| --- | --- | --- |
| `<task>-answer-v1` | `v1` | 基础指令，只输出标签 |
| `<task>-answer-v2` | `v2` | 基础指令 + 蒸馏规则，只输出标签 |
| `<task>-reason-v1` | `v4` / `v4b` | 基础指令 + 先写判断依据 |
| `<task>-reason-v2` | `v5` | 基础指令 + 判断依据 + 蒸馏规则 |

`answer-v2` 和 `reason-v2` **用同一套任务规则**（规则讲的是标签判定，不是输出格式；
共用才能让两者成为「只差输出格式」的单变量对照），但两套规则**分别蒸馏**：
`answer-v2` 的规则从 `answer-v1` 在 train_evolve 上的错误里来，`reason-v2` 的从 `reason-v1` 的错误里来。
因为 `reason-v1` 的错例带模型自己写的依据，归因能看到的东西本质不同。

**旧的多任务提示词一个字都不改、一个文件都不移。** `config.json` 里记着
`prompt_file: "prompts/zero_shot_v1.txt"`，`src/analyst.py` 会照这个路径回读指令原文；
移动文件会让所有历史运行失去可复算性。它们只是在 config 里补一个 `task: "multi"`。

### 3.3 文件布局

```
prompts/zero_shot_v1.txt                          # 多任务，原地不动
prompts/few_shot_v1.json                          # 多任务，原地不动
prompts/single/task1/zero_shot_answer_v1.txt      # 单任务，新建
prompts/single/task1/zero_shot_answer_v2.txt      #   由 assemble_instruction.py 生成
prompts/single/task1/zero_shot_reason_v1.txt
prompts/single/task1/zero_shot_reason_v2.txt      #   由 assemble_instruction.py 生成
prompts/single/task1/few_shot_answer_v1.json
prompts/single/task1/few_shot_reason_v1.json
prompts/single/task1/analyst_answer_explain.txt   # 本任务的归因提示词
prompts/single/task1/analyst_reason_explain.txt
prompts/single/analyst_answer_patch.txt           # 出规则提示词，三个任务共用
prompts/single/analyst_reason_patch.txt
prompts/patches/single/task1/answer_v2/*.txt      # 蒸馏出的规则
prompts/patches/single/task1/reason_v2/*.txt
```

`task2a` / `task2b` 同构。

### 3.4 命令行与结果目录

```bash
.venv/bin/python src/run.py --task task1 --version answer-v1 --strategy zero-shot
```

- 文件名用下划线（`zero_shot_answer_v1.txt`），命令行与目录名用连字符（`answer-v1`）。
  代码里做一次 `version.replace("-", "_")` 完成转换，不让两套写法各自蔓延。
- 不带 `--task` 时默认 `multi`，走老路径 `prompts/zero_shot_<version>.txt`，**现有命令一条都不用改**。

结果目录（**要迁移旧结果**）：

```
results/deepseek-flash/multitask/<experiment>/<run_id>/    # 现有 22 个运行，整体迁入
results/deepseek-flash/task1/<experiment>/<run_id>/
results/deepseek-flash/task2a/<experiment>/<run_id>/
results/deepseek-flash/task2b/<experiment>/<run_id>/
results/_smoke/<task>/<experiment>/<run_id>/               # train_evolve / train_val，不提交
results/analysis/<task>/<run_id>/lessons.jsonl             # 每个任务自己的归因产物
```

`<experiment>` 在任务目录内部沿用现有写法，版本号换成新的：

```
zero-shot-answer-v1              few-shot-bm25-k10-reason-v1
zero-shot-reason-v2              few-shot-random-s0-k3-answer-v1
```

任务已经在路径里，所以 `<experiment>` 不再重复任务名；报告里引用一个运行时写全
`task1/zero-shot-answer-v1/<run_id>`。`config.json` 里同时存
`task`、`version` 和拼好的 `prompt_id`（如 `task1-answer-v1`），让单个目录脱离上下文也认得出来。

迁移用 `git mv`，**run_id 不变**，所以 `results/comparison.md` 里记录的 run_id 仍然指得到同一次运行，
只是路径多一层。迁移后要跟着改的引用：`Makefile` 的 `RUN` 默认值、`README.md` 的快速开始命令、
`docs/` 里写死的若干路径。`src/compare.py` 会重新生成 `comparison.md`，不用手改。

### 3.5 改命名会打到哪些代码（已逐行查过）

| 位置 | 现在怎么耦合的 | 不改会怎样 |
| --- | --- | --- |
| `src/run.py:44` `OUTPUT_FORMATS` | **按版本字符串精确查表** `{"v4": ..., "v4b": ..., "v5": ...}` | **最严重的一处**：新版本号不在表里 → 带判断依据的输出被当成裸标签解析 → 每条 `invalid_output` → 重试三次后整条丢弃。改成「输出格式线为 `reason` 即 `reasoning-answer-v1`」 |
| `src/run.py:278` | 拼 `prompts/{strategy}_{version}.txt` | 找不到文件，直接退出。改成按 `--task` 分叉到 `prompts/single/<task>/` |
| `src/fewshot.py:26` `load_spec()` | 拼 `prompts/few_shot_{version}.json` | 同上 |
| `src/run.py:120-123` `experiment_name()` | 版本号直接拼进目录名 | 不报错，但要和新目录结构对齐，并做连字符规范化 |
| `src/run.py:164` | 续跑时校验 `prompt_sha256` 与 `split` | 行为不变，但 `extra` 里要加上 `task` 一起校验 |
| `src/compare.py:18` `SYSTEM_HASH_PREFIX = "ceb0530c8df1"` | **硬编码 v1 系统提示词的哈希前缀**，用于在对比表里打勾「是不是同一份系统提示」 | 单任务提示词哈希全不同 → 整列打 ✗。改成按 `(task, lineage)` 查一张基准哈希表 |
| `src/compare.py:45`、`src/analyze.py:67` | `config.get("experiment") or f"{strategy}-{version}"` 拼显示名 | 标签错乱 |
| `src/compare_html.py:78` | `c.get("version") or "v1"` 默认值写死 | 显示错误的版本 |
| `Makefile:26,27,35,60` | 写死 `--version v1` / `v2` | `make validate` 等入口失效 |

这张表是 §4 代码改动清单里 C2 / C4 / C5 的细化，实现时逐行对照着改。

## 4. 代码改动清单

全部改动都要保持**多任务路径逐字节不变**：改完后用现有 v1 运行复算 `metrics.json`，必须和仓库里的文件一致。

**状态：C1–C15 已于 2026-11-04 全部实现。** 回归检查实跑结果：

| 检查 | 结果 |
| --- | --- |
| 13 个本地有原始日志的多任务运行重算 `metrics.json` | **逐字节一致**（另有 9 个缺 `raw_responses.jsonl`，是队友机器上跑的，跳过） |
| 多任务 `triage.py` | 复现已知数字：exact 70 条 49.0%、gold 3→pred 4 共 20 条 |
| 多任务 `paired_bootstrap.py` | 与改动前实现**输出完全相同**（zero-shot v1 vs bm25 k10 v1：−0.112，CI [−0.175, −0.056]） |
| 多任务 `analyst.py worklist` | 复现 73 条错例及其分桶 |
| 单元测试 | 9 个全过（原 4 个 + 新增 5 个单任务检查） |
| `make validate` | 通过 |

顺带发现一处**改动前就存在**的小出入：[README.md](../../README.md) 记的配对自举区间是 `[−0.175, −0.049]`，
`src/paired_bootstrap.py` 现在复算出来是 `[−0.175, −0.056]`（点估计 −0.112 一致）。不是这次引入的。

| 编号 | 文件 | 改什么 |
| --- | --- | --- |
| C1 | `src/common.py` | 加 `TASK_FIELDS`（任务 → 该任务的输出字段）。`validate_prediction(pred, task="multi")`、`unpack_prediction(output, output_format, task)`、`compute_metrics(preds, golds, task)` 都加 `task` 参数，默认 `"multi"` 时行为和现在逐行相同 |
| C2 | `src/run.py` | 加 `--task {multi,task1,task2a,task2b}`，默认 `multi`。决定四件事：提示词路径、结果目录多一层 `<task>`、输出校验用哪个字段集、`OUTPUT_FORMATS` 的判定改成按输出格式线。`task` / `prompt_id` 写进 `config.json`，续跑时校验一致。细节见 §3.5 |
| C3 | `src/evaluate.py` | 读 `config["task"]`，只算该任务的指标；`metrics.json` 只写该任务那一项，并带上 `task` 字段 |
| C4 | `src/fewshot.py` | `load_spec(version, task)` 按任务找配置文件。消息拼装本身**不用改**：`assistant_output_keys` 已经是参数化的，单任务配置里填一个字段即可 |
| C5 | `src/compare.py`、`src/compare_html.py` | glob 多一层；按 `task` 分组，每个任务一张表；容忍 `metrics.json` 只有一项指标；`SYSTEM_HASH_PREFIX` 改成查表 |
| C6 | `src/triage.py` | 加 `--task`。分桶退化：Task 1 只有 `severity_over` / `severity_under` / `exact`；Task 2a / 2b 细分成 `*_missing` / `*_extra` / `*_swap` / `exact` |
| C7 | `src/analyst.py` | `dossier()` 的 `label_block()` 现在写死三个字段，改成按任务取字段；加 `--task`；归因产物写进 `results/analysis/<task>/<run_id>/` |
| C8 | `src/assemble_instruction.py` | **可能不用改**。`ANCHORS` 已经同时支持两种结尾句；单任务提示词会沿用同样的句子。写完 6 份基础提示词后跑一次验证，不命中再加锚点 |
| C9 | `src/merge_lessons.py` | **不用改**。`theme_of()` 靠 gold/pred 的字段差分主题，单任务下自然退化成只认本任务字段（已核对第 46–66 行） |
| C10 | `src/paired_bootstrap.py` | `per_sample()` 的 `exact` 分支读三个字段，单任务下要按 `task` 退化成单字段；`mae` / `domain` / `driver` 三个分支本身可直接用 |
| C11 | **新建** `src/assemble_single.py` | 把三个任务的单任务运行按 `example_id` 合并成一个含三字段的评测目录，交给现有 `src/evaluate.py` 复算，用来和 multitask 的「三字段全对」直接比。必须记录三个来源 run_id；**任何一个任务缺预测就整条丢弃，不补标准答案、不补默认安全标签**（[next-prompt-experiments.md](../next-prompt-experiments.md) §5 的硬要求） |
| C12 | `src/run.py`、`src/analyst.py` | 加 `--concurrency N`（默认 1，行为与改动前一致），把串行请求改成有上限的并发。断点续跑、`predictions.jsonl` 追加、失败重试逻辑都不变（`evaluate.py` 按 id 查表，不依赖行序）；归因的 `lessons.jsonl` 追加加锁。**实测：Task 1 的 14 格 dev 实验并发 8 路约 10 分钟，串行约 1.6 小时** |
| C13 | `Makefile`、`README.md` | 跟着迁移后的路径和新命名改；命名约定写进 README。新增 `make single-prompts / single-dev / single-compare`（用 `TASK=` 选任务，`CONC=` 选并发） |
| C14 | **新建** `src/make_single_prompts.py` | 从 `prompts/zero_shot_v1.txt` **切片**生成单任务提示词，而不是手抄：共享的段落因此逐字节一致，`--check` 可随时复验。三个任务的差异集中在脚本里的一张 `TASKS` 表 |
| C15 | `src/triage.py`、`src/analyst.py` | 任务从 `config.json` 读，另加一个**可选**的 `--task`：传了就校验与 config 一致，不一致直接退出。这样文档里的写法和裸写法都能用，又拦得住张冠李戴 |

## 5. 为什么带判断依据的 few-shot 要在最后一条用户消息加格式提醒

这是本方案唯一一处「为了让格式稳定而引入的额外变量」，所以单独解释清楚。

### 5.1 现象

`results/deepseek-flash/few-shot-bm25-k5-v4/20261103-075342/metrics.json` 记录 143 条里 **11 条失败**
（`n_success: 132`）：示例的 assistant 回答只有标签，模型照着示例也只输出裸标签，重试三次救不回来。
`prompts/few_shot_v4b.json` 在**最后一条用户消息**后面加一句格式提醒之后，
`few-shot-bm25-k5-v4b/20261103-083817` 恢复到 143/143。

同一版指令在**没有示例**时（`zero-shot-v4/20261103-074636`）是 143/143，零失败。
**失败只在有示例时出现**，这是定位病因的关键一条。

### 5.2 为什么会失败

少样本提示词是真的聊天轮次：系统提示 →（用户、助手）× k → 待评估样本。
那 k 组示例里，助手每一次都只回一个裸标签 JSON。于是生成点之前**紧挨着的、重复了 k 次的局部模式**是
「收到轨迹就回裸标签」；而要求两键格式的那句话在系统提示里，离生成点最远、只说了一遍。
两边冲突时，重复且靠近生成点的示例模式压过了只说一遍的系统指令——这就是少样本学习里
「示例盖过指令」的常见情形，k 越大压得越狠。

### 5.3 为什么把提醒放最后一条用户消息能救回来

因为它**把一句相反的指令放到了示例模式影响力最强的那个位置**：最后一条示例之后、生成之前。
模型要接着往下写的时候，最近读到的不再是「上一个助手回了裸标签」，而是「这一条要用两键格式」。
改的是位置，不是措辞。

**诚实的边界**：以上是对机制的解释，我没有办法直接验证模型内部发生了什么。
能证实的只有三条可复算的事实：(1) 零示例时不失败；(2) 加了示例就失败，k=5 时 11/143；
(3) 把提醒放到最后一条用户消息后，同配置恢复 143/143。
如果你想要更强的证据，可以在 k=3 上各跑 20 条做一次 A/B，成本约 0.2M token——
但考虑到现有证据已经是 11/143 对 0/143，我认为不必。

### 5.4 为什么不选另一个方案：给示例也写上判断依据

那个方案（给每条 train 示例补一段依据，让示例和最终样本格式一致）在**概念上更干净**——
它消除冲突，而不是用一句话压过冲突。但它有两个本方案承受不起的代价：

1. **它引入一个大得多的新变量**。那些依据不是数据集自带的，只能由模型按标准答案倒着编出来。
   编出来的依据会连带教给模型一种推理风格，于是「单任务的收益」和「示例依据的风格效应」混在一起，
   没法分开归因。`prompts/few_shot_v4b.json` 的 `note` 字段和
   [next-prompt-experiments.md](../next-prompt-experiments.md) §2 都把这一条明确列为**另一项独立待研究变量**。
2. **成本和可信度**。要给 BM25 与 random 两套选择里被用到的全部 train 样本生成依据，
   而这些依据是「照着标准答案编的事后合理化」，本身没有验证手段。

所以本轮采用格式提醒这一方案，并把它当作一个**要记录在案的变量**：
提醒只加在待评估样本那一条，示例本身逐字节不变，`config.json` 里通过 `spec_sha256` 记下用的是哪份配置。
「给示例补依据」作为备选留在 §11。

## 6. 可复用资产（逐个核对过）

| 资产 | 状态 | 本轮怎么用 |
| --- | --- | --- |
| `data/fewshot/bm25_dev_top10.json` | 在库 | **不重新检索**。BM25（Best Matching 25，一种基于词频的文本检索打分函数）只读 `formatted_interaction` 的文本，不读任何标签（`src/select_examples.py:49`），所以同一份检索结果对三个任务都成立。k=3/5/10 共用这一个文件（选择是嵌套的，`src/fewshot.py:69`） |
| `data/fewshot/random_seed0.json` | 在库 | 同上，k=3/5/10 共用 |
| `data/fewshot/bm25_dev_top20.json`、`random_seed0_top20.json` | 在库 | 三个任务的 k=20 都用它。已逐条验证 top20 的前 10 条与对应 top10 文件一致，所以 k=3/5/10/20 是嵌套的同一套选择 |
| `src/fewshot.py` 的 `assistant_output_keys` | 已参数化 | 单任务示例答案只保留本任务标签，**不用写预处理脚本**，在配置 JSON 里填一个字段名即可 |
| `src/fewshot.py` 的 `final_user_suffix` | 已实现（`build_messages()`） | 带判断依据的 few-shot 必须用，理由见 §5 |
| `data/splits/train_evolve.jsonl`、`train_val.jsonl` | 由 `make_splits.py` 生成，不入库 | trace2skill 的蒸馏集与验证集。跑前先 `make splits` 重建，并用 `--check` 确认和已提交的 id 清单一致 |
| `src/triage.py` / `analyst.py` / `merge_lessons.py` / `assemble_instruction.py` | 两轮已跑通 | 蒸馏流水线骨架，按 §4 的 C6 / C7 小改 |
| `prompts/patches/v2/`、`patches/v5/` | 在库 | **本轮不复用**。它们是从多任务指令的错误里蒸馏的，标准答案口径和单任务不同；而且 `patches/v5` 的 5 条规则里没有一条 domain 规则，Task 2a 直接是空的 |

## 7. 预算

prompt token 实测值（dev 143 条，取自各运行 `metrics.json` 的 `tokens.prompt_tokens`）：

| 配置 | 实测 prompt token |
| --- | --- |
| zero-shot | 0.25 M |
| few-shot BM25 k=3 / 5 / 10 / 20 | 0.81 / 1.20 / 2.11 / 3.92 M |
| few-shot random k=3 / 5 / 10 / 20 | 0.75 / 1.09 / 1.92 / 3.62 M |

单任务指令比多任务短（砍掉另外两个任务的标签定义），但请求里占大头的是轨迹正文，所以总量只降一成左右。
按不降估算，一个任务：

| 项 | 估算 |
| --- | --- |
| S0 的 10 个 dev 运行 | ≈ 16 M |
| S1 的 10 个 dev 运行 | ≈ 16 M |
| train_evolve 基线 ×2（461 条） | ≈ 1.5 M |
| 归因 ×2 | ≈ 2.6 M |
| train_val 验证 ×4（107 条） | ≈ 0.7 M |
| **一个任务合计** | **≈ 37 M** |
| **三个任务合计** | **≈ 110 M** |

调用次数：一个任务约 5 000 次，三个任务约 15 000 次。
**Task 1 实测**：20 格 dev 加 trace2skill 全流程共约 33 M prompt token（另有归因 486 次调用），
并发 6–8 路下总耗时约 1 小时；串行要好几个小时。这是做 C12（并发）的理由。

## 8. 全自动执行与三处质检

三处「关卡」是蒸馏流水线里必须停下来看一眼质量再决定走不走下一步的检查点，沿用
[v4 方案](../v4-reasoning-trace2skill-plan.md) 的叫法。本轮要全自动，所以**由执行的 agent 自己读、自己判，
把判断依据和数字写进报告**，不打断人：

| 关卡 | 在哪一步 | 判什么 | 不过关怎么办 |
| --- | --- | --- | --- |
| **G 归因质量** | 归因跑完前 5 条之后 | 打开 `lessons.jsonl` 读 5 条：(1) `reason` 一侧的分析是否真的引用了模型自己写的依据（`model_reasoning` 字段非空且被 `reasoning_audit` 引用），而不是凭空猜；(2) 引文逐字校验通过（`quotes_ok` 非空）；(3) `root_cause` 指名指令里缺哪条规则，不是「模型判断失误」这种空话 | 停在 5 条，改 analyst 提示词重来，**不全量跑** |
| **H 规则条数** | `assemble_instruction.py` 之后 | 它会打印词数增幅。第一轮教训：v3（+193%，7 条规则）四项指标全面差于 v2（+138%，5 条） | 超过 +150% 就砍掉支持度最低的主题，另出一版做对照 |
| **I train_val 对照** | 上 dev 之前 | `answer-v2` vs `answer-v1`、`reason-v2` vs `reason-v1` 在 train_val 上的配对自举（paired bootstrap，即按样本配对重采样估计差异区间）。107 条的分辨率极限约 0.04 | **只记录，不拦截**：无论结果如何都接着跑 dev，判读写进报告 |

**2026-11-04 实跑结果：Task 1 的两条输出格式线都卡在关卡 I。** `answer-v2` 在 train_val 上
MAE 0.364 → 0.495（CI [+0.028, +0.234]，显著变差），`reason-v2` 0.290 → 0.374。
两格都没上 dev。归因阶段的 `reasoning_fault` 给出了原因：102 条错例里只有 3 条是
`sound_but_wrong`（推理忠实而标签错，即真正的指令缺陷），84 条是读证据读错或漏读——
**往指令里加规则治不了读证据的问题**。详见 [Task 1 方案](01-task1-risk-level.md) §7。

**关卡 I 不是闸门（2026-11-04 改）。** 原方案是「train_val 不过关就不上 dev」。
现在改成：train_val 的对照照样跑、照样记录，但**无论结果如何都在 dev 上跑一次**。
理由是我们不会拿 dev 的结果回头改提示词——dev 在这里只用于和已有的多任务表同口径对比，
不参与选择。这让 20 格表格完整，代价是 dev 的使用次数增加（见 §10）。

关卡 I 有真实的前车之鉴：`results/_smoke/zero-shot-v5/20261103-113649/metrics.json` 显示多任务的 `v5`
（从 v4 真实推理蒸馏的 5 条规则）在 train_val 上 MAE 0.402、2a 0.770、2b 0.656，
而同一集合上的 `v4`（`20261103-102236`）是 0.234 / 0.874 / 0.695 —— **三项全面变差**。
所以单任务的第 10 格很可能在 train_val 上也是变差。**这不再阻止它上 dev**，
但报告里必须把 train_val 的判读和 dev 的分数并列写出来，不能只报好看的那个。

## 9. 验收口径

- 每个 dev 运行必须 **143/143 条有合法预测**，`metrics.json` 的 `n_failed` 为 0；不满足就不进对比表，
  并在报告里单列失败条数与原因。
- 指标分任务报告：Task 1 用**平均绝对误差（Mean Absolute Error / MAE，预测等级与标准等级绝对差的均值）**，
  越低越好；Task 2a / 2b 用**平均集合交并比（Mean Jaccard，逐样本算预测与标准标签集合的交集占并集之比再平均）**，
  越高越好。**不自行把三项合成总分。**
- 差异判读：143 条 dev 上 MAE 差小于约 **0.03** 一律按噪声处理，依据是第一轮的配对自举结论
  （[next-round-plan.md](../next-round-plan.md) §2，可用 `src/paired_bootstrap.py` 复算）。train_val 107 条上这个阈值约 0.04。
- 每个结论都要能由 `src/evaluate.py` 复算，报告里写清 run_id。
- 单任务 vs 多任务的「三字段全对」用 C11 的合并目录算，并写明三个来源 run_id。

## 10. 必须披露的事

dev 已被用于配置选择 22 次（`results/comparison.md` 的 22 行）。本轮每个任务加 **20 个** dev 配置，
三个任务加满就是 **82 次**（Task 1 已加完 20 个，当前 **42 次**）。
其中第 10 格（trace2skill）是在 train_val 对照之后**无条件**跑的，不以 dev 分数作为选择依据，
但它仍然占用 dev 的一次使用，必须照算进这个数字。
因此 `results/comparison.md`、`comparison-task1.md` 里的任何最优值都是**选择后的乐观上界**，
不是泛化成绩。报告里要把这个数字更新掉，并保留全部候选分数。真正的泛化成绩看官方隐藏测试集。

## 11. 备选清单（不自动跑，要跑时单独起）

以下项目方案已经写好、代码路径也都支持，但**本轮自动执行时跳过**，留着按需再开：

| # | 项目 | 为什么留到以后 | 真要跑时的增量成本 |
| --- | --- | --- | --- |
| B1 | **给 few-shot 示例也补判断依据** | 引入「示例依据风格」这个独立变量，会和单任务的收益混在一起，理由见 §5.4 | 需要先为被用到的 train 样本生成依据，另立方案 |
| B2 | **bm25-action 检索**（把 `proposed_action` 再拼一遍，加权动作文本） | 多任务上它不如纯 BM25（k=10 时 MAE 0.196 vs 0.189），老师这一轮也没要求 | 选择文件已在库 |
| B3 | **random 的第二个种子** | 现有 random 组只有 seed 0，单个小差异可能是噪声 | 需要 `src/select_examples.py --method random --seed 1` 新建选择文件，不覆盖旧的 |
| B4 | **三任务合并后的「三字段全对」** | 要等三个任务都跑完才有意义 | 零 API 成本，C11 的脚本离线算 |

## 12. 三个任务跑完之后的总结（2026-11-04）

60 格 dev 运行全部完成，**143/143 合法预测，零遗漏**。三份任务方案的进展日志见
[01 §7](01-task1-risk-level.md)、[02 §7](02-task2a-harm-domain.md)、[03 §7](03-task2b-risk-driver.md)。

### 12.1 单任务 vs 多任务：单项都是噪声，合起来才显著

每个任务单独看，拆分带来的改善都在噪声内：

| 任务 | 指标 | 单任务 zero-shot（`answer-v1`） | 多任务 `v1` | 差 | 判读 |
| --- | --- | --- | --- | --- | --- |
| Task 1 | MAE↓ | 0.266 | 0.301 | −0.035 | 噪声 |
| Task 2a | J↑ | 0.837 | 0.811 | −0.026（损失） | 噪声 |
| Task 2b | J↑ | 0.711 | 0.726 | +0.015（损失） | 噪声，**方向不利** |

但把三个任务的预测按 `example_id` 合并（`src/assemble_single.py`），用多任务表里的
**「三字段全对」**来比，结果是显著的：

| 配置 | MAE↓ | 2a J↑ | 2b J↑ | 三字段全对 | prompt token |
| --- | --- | --- | --- | --- | --- |
| 多任务 `v1` zero-shot | 0.301 | 0.811 | 0.726 | 70（49.0%） | 0.25 M |
| 多任务 `v4` zero-shot | 0.238 | 0.821 | 0.740 | 71（49.7%） | 0.28 M |
| 单任务合并 `answer-v1` | 0.266 | 0.837 | 0.711 | 74（51.7%） | 0.64 M |
| **单任务合并 `reason-v1`** | **0.238** | 0.832 | **0.753** | **79（55.2%）** | 0.72 M |

配对自举（`--metric exact`）：单任务合并 `reason-v1` 对多任务 `v1` 是 −0.063，
CI **[−0.119, −0.014]**；对多任务 `v4` 是 −0.056，CI **[−0.112, −0.007]**，两个都不跨 0。
**这是整轮唯一一个统计上确定的单任务 vs 多任务结果。**

解释：三个子任务各自只好一点点（且 Task 2b 还略差），但三项同时判对的概率提高了——
错误之间的相关性下降了。代价是 token 约 2.6 倍（三次调用对一次）。
参照：多任务最优的 few-shot（bm25 k=10 `v1`）三字段全对是 56.6%，但要 2.11 M token。
**单任务 zero-shot 用不到三分之一的成本接近了它。**

### 12.2 总分之外：三个任务的偏置都被改善了，而且方式不同

| 任务 | 多任务的病灶 | 单任务后 |
| --- | --- | --- |
| Task 1 | 整体高估，平均偏差 +0.189 | 只拆任务 +0.112，加判断依据 **−0.056** |
| Task 2a | 多给第二个标签，143 条里 55 条（标准答案 29） | 只拆任务 **27 条**，基本校准 |
| Task 2b | 标签边界分不开（Scope vs Authorization） | 基数没变（70 对 56），**但判断依据让 zero-shot 显著变好**（−0.042，CI [−0.083, −0.002]） |

**判断依据（`reason` 线）的收益按任务排序**：Task 2b > Task 1 ≈ Task 2a。
九格逐格对照里越线的格数：Task 2b 两格（含 zero-shot）、Task 1 一格、Task 2a 一格。
Task 2b 那句专有的「先把决定性事实钉下来，再对着它证明每个 driver」是本轮最有效的一处提示词改动。

### 12.3 trace2skill：三个任务三种结果，归因阶段能预判方向但不能预判幅度

| 任务 | `wrong_rule` 占比 | train_val | dev | 结论 |
| --- | --- | --- | --- | --- |
| Task 1 | 15 / 102（15%） | 两条线都显著变差 | 两条线都变差 | **负收益** |
| Task 2a | 70 / 127（55%） | `answer` 显著变好 | 两条线都变好（噪声内） | **正收益** |
| Task 2b | 98 / 172（57%） | `answer` **−0.111 显著变好** | 几乎原地 / 略差 | **没传过去** |

两条可用的经验：

1. **归因阶段的 `reasoning_fault` 分布能预判方向**。`wrong_rule` 和 `label_definition` 占比高
   （指令定义分不开）→ 规则有机会；`misread_evidence` / `missed_evidence` 占比高
   （读证据读错）→ 加规则治不了。Task 1 的 `sound_but_wrong` 只有 3/102，结果就是负收益。
   **这比跑完 train_val 早得多。**
2. **train_val 能排除有害的规则，但不能确认收益幅度**。六组对照里五组方向一致，
   唯一一个在 train_val 上达到显著的正收益（Task 2b 的 `answer`，−0.111）
   到 dev 上只剩 −0.005。负收益方向上 train_val 三次预警全对。

还有一条贯穿三个任务的：**关卡 H 真的在拦东西**。Task 2a 的 `answer` 6 条规则 +260%、
Task 2b 的 `answer` 4 条 +200%，都被砍到 2–3 条才放行。提示词越短越容易超线，
`answer` 线（没有判断依据段，199–226 词）比 `reason` 线（339–363 词）危险得多。

### 12.4 账

| 项 | 数 |
| --- | --- |
| dev 格数 | 60（每任务 20），全部 143/143 |
| 推理 prompt token | Task 1 约 33 M、Task 2a 33.3 M、Task 2b 33.2 M，合计约 **100 M** |
| 归因调用 | 243 + 250 + 376 = 869 条教训 × 2 = **1 738 次** |
| dev 使用次数 | 多任务 27 + 单任务 60 = **87**（合并目录是离线派生，不另计） |

**87 次意味着 dev 已经被彻底用于配置选择**，所有表里的最优值都是选择后的乐观上界。
真正的泛化成绩只能看官方隐藏测试集。
