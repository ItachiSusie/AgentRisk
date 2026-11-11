# 给 Codex 的任务：完成 evolve 方法在 Task 2b 上的验证运行

请全程用中文回复。专业名词第一次出现时给出英文原文，并用一句话解释。

## 0. 背景（先读，不要跳过）

- 仓库：`/Users/CS/AgentRisk/AgentRisk-evolve`。这是一个 git worktree（同一仓库的第二份工作副本），分支是 `feat/evolve-design`。**只在这个目录里写文件。**
- 原仓库 `/Users/CS/AgentRisk/AgentRisk` 里有用户没提交的工作：**只读**，只用来读取下面「已有运行」表里列出的 train_val 运行目录，不要在那里写、改、提交任何东西。
- 项目约定：先读 `AGENTS.md` 和 `README.md`。
- 方法设计：`docs/evolve/spec.md`（实现规格）和 `docs/evolve/eval.md`（成功标准），由老师 Qi 编写。**本任务完全按这两份文档执行**；与文档字面不同的任何参数，都要先停下问用户。
- 已有实现：`src/evolve.py`、`tests/test_evolve.py`、`prompts/evolve/proposer_*_v1.txt`。实现时做的决定和已知问题记在 `docs/evolve/implementation.md`，**请完整读一遍**，尤其是 §3、§4 和 §6。
- 环境：
  - Python 用 `.venv/bin/python`。
  - API 密钥先加载：`set -a; . ./.env; set +a`。
  - `data/raw`、`.env`、`.venv` 是指向原仓库的符号链接，已被 git 忽略，不要提交。
- 当前状态：代码已写完，`make test`（80 条）和 `make validate` 都通过。**代码还没提交，还没有做过任何真实 API 调用。**

### 已有运行（对照组，不要重跑）

eval.md §2 的对照组里，下面这些已经跑过，直接复用：

| 编号 | 配置 | train_val（107 条） | dev（143 条） |
|---|---|---|---|
| B0 | zero-shot `reason-v1`（种子，主要对照） | `/Users/CS/AgentRisk/AgentRisk/results/_smoke/task2b/zero-shot-reason-v1/20261104-094517` | `results/deepseek-flash/task2b/zero-shot-reason-v1/20261104-092410` |
| B1 | zero-shot `reason-v2`（上一轮 Trace2Skill） | `/Users/CS/AgentRisk/AgentRisk/results/_smoke/task2b/zero-shot-reason-v2/20261104-094540` | `results/deepseek-flash/task2b/zero-shot-reason-v2/20261104-094648` |
| B2 | few-shot BM25 k=10 `answer-v1`（参考上限） | **没有，第 3 步新跑** | `results/deepseek-flash/task2b/few-shot-bm25-k10-answer-v1/20261104-092401` |

注意：原仓库 `results/_smoke/task2b/` 下还有 `20261110-*` 和其他版本（reason-v3/v4、facts-*）的运行，那是用户另一条实验线的，**不要用**。使用前用 `config.json` 核对 split=train_val、`prompt_sha256` 与 worktree 里 `prompts/single/task2b/zero_shot_reason_v1.txt`（或 v2）一致，不一致就停下汇报。

## 1. 硬性规则（来自老师，必须遵守）

1. evolve 循环里只用 train_evolve。train_val 和 dev 都不能进循环。
2. 跑 dev 之前，先按 eval.md §3.1 写好预登记文件（preregistration，事先写下比较对象和判定规则）并提交。每个任务的 dev 只跑一次，结果不回头改。
3. prompt 一旦用于正式运行就不再修改，要改就新建版本号。每次运行都开新的 run_id，旧的保留。所有分数要能用 `src/evaluate.py` 复算。
4. git 提交信息里**不要**加任何 AI 署名，比如 `Co-Authored-By`、`Generated with ...`。
5. 遇到下面标着「⛔ 停下」的地方，必须停下来，把结果汇报给用户，等用户同意后再继续。
6. 不要 `git push`，不要切换分支，不要删除任何已有的结果目录。

## 2. 步骤

### 第 1 步：独立检查代码（不调 API）

1. 对照 spec.md 和 eval.md 独立审查 `src/evolve.py` 和两个提议器（proposer，负责提出 prompt 改动的模型调用）prompt。重点看三处：
   - 数据角色：提议器载荷里不能出现提议折以外的 id；
   - 闸门 G1–G6 是否按 spec 实现；
   - 续跑时会不会重复请求。
2. 运行：
   - `make test`
   - `make evolve-dry`
   - `make evolve-dry EVOLVE_TASK=task1`
3. 发现 bug 就修，并补测试。`prompts/evolve/*_v1.txt` 还没被任何真实运行用过，现在仍可修改；第 2 步开始后就冻结。

⛔ **停下**（先不要提交）：汇报
- 审查发现的问题和你的修改（附 `git diff`）；
- 三个命令的结果。

用户同意后再提交，提交信息例如：`feat: evolve 实现（spec §6）与离线测试`。只提交这些路径：
`src/evolve.py`、`tests/test_evolve.py`、`prompts/evolve/`、`docs/evolve/implementation.md`、`docs/evolve/codex-task2b.md`、`Makefile`、`.gitignore`。**不要**提交 `results/_smoke/`。

### 第 2 步：Task 2b 试跑（spec §9 第 2–3 步，会花少量 API 费用）

**按 spec 原样**用 `--limit-per-fold 10`：

```bash
set -a; . ./.env; set +a
R=$(.venv/bin/python src/evolve.py init --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt --limit-per-fold 10 | tail -1)
.venv/bin/python src/evolve.py baseline --run-dir $R --concurrency 8
.venv/bin/python src/evolve.py step --run-dir $R --rounds 1 --concurrency 8
.venv/bin/python src/evolve.py status --run-dir $R
```

implementation.md §4 第 1 点预计：每折 10 条时，可能凑不够 `min_wrong=4` 条同类错例，这一轮会因为「没有目标格子」被跳过。**这只是离线推演，请用真实结果验证。**

- 如果这一轮被跳过：不要自己改参数，停下汇报（见下）。
- 如果没被跳过：检查下面四件事。

1. `$R/rounds/round_01/` 下的文件：
   - `proposer_blind.json`、`proposer_edit.json`：引文是否真实；4 个改动是否真的不同；是否只改了几句话。
   - `candidates.json`：每个改动被拒的原因，看是否合理。
   - `quick_gate.json`、`full_gate.json`：闸门的数字。
2. `$R/lineage.md` 是否可读。
3. 噪声底 τ（同一 prompt 跑两次、预测不同的样本数）：在 `baseline.json` 里。另外，用 `s0` 和它的重复运行 `s0_repeat1` 这一对**纯噪声**预测，手算一下 G3 的「标签互换」规则（某个标签 FP 减少、FN 增加，且 FP+FN 不降）会不会误触发（implementation.md §6 第 1 点）。
4. 实际花了多少输入、输出 token（`status` 会报）。

⛔ **停下**：汇报以下内容，然后等用户确认：
- 这一轮是否被跳过；如果被跳过，原因是什么；
- 试跑的 τ；
- 提议器的输出质量、4 个改动的有效率、快速闸门的通过情况（如果没被跳过）；
- G3 在纯噪声下会不会误触发；
- 实际花了多少 token；
- 你建议的参数调整（例如 `--limit-per-fold 30` 或 `--param min_wrong=2`）。按 spec §9 第 3 步，调整一律开新的 run，旧的试跑保留。**由用户决定是否调整、怎么调整。**

### 第 3 步：Task 2b 全量运行，以及 train_val 上的比较

用户同意后：

```bash
R=$(.venv/bin/python src/evolve.py init --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt | tail -1)
.venv/bin/python src/evolve.py baseline --run-dir $R --concurrency 8
.venv/bin/python src/evolve.py step --run-dir $R --concurrency 8
.venv/bin/python src/evolve.py status --run-dir $R
```

- 只有用户在第 2 步确认过的参数改动才加 `--param`，其余全用 spec 默认值。
- 预算约 2100 万输入 token（spec §7）。如果因为 API 中断而停止，重跑同一条命令即可续跑，已完成的部分不会重复请求。
- 导出：`.venv/bin/python src/evolve.py export --run-dir $R --version reason-v5`。**版本号用 v5 或更高**，因为用户的另一个分支已经占用了 `reason-v3` 和 `reason-v4`。

然后在 train_val 上跑三个配置（eval.md §2：B2、E、E+R 在 train_val 上都要新跑）：

```bash
# E：导出的 prompt，zero-shot
.venv/bin/python src/run.py --task task2b --version reason-v5 --strategy zero-shot --split train_val --data-file data/splits/train_val.jsonl --concurrency 8
# B2：few-shot BM25 k=10 answer-v1
.venv/bin/python src/run.py --task task2b --version answer-v1 --strategy few-shot --selection bm25 --k 10 --split train_val --data-file data/splits/train_val.jsonl --concurrency 8
# E+R：导出的 prompt + BM25 k=10 few-shot
.venv/bin/python src/run.py --task task2b --version reason-v5 --strategy few-shot --selection bm25 --k 10 --split train_val --data-file data/splits/train_val.jsonl --concurrency 8
```

- 两条 few-shot 命令先各加 `--dry-run` 跑一次，确认用的选例文件是 `data/fewshot/bm25_train_val_top10.json`（检索池是 train_evolve，不含 train_val 本身，否则会泄漏答案）。不是的话停下汇报。
- 对每个新运行目录执行 `src/evaluate.py`，再用 `src/paired_bootstrap.py` 比较：E 对 B0、E 对 B1、E 对 B2、E+R 对 B2、E+R 对 E。B0、B1、B2 的目录见上面的「已有运行」表。

⛔ **停下**：汇报以下内容，等用户确认：
- 接受了几个改动、每个改动的 diff；
- train_evolve 和 train_val 上 E 对 B0 的差值及 95% 置信区间（confidence interval / CI），以及其他比较；
- eval.md §3.2 的各项护栏：没有改坏、没有标签互换、全部预测有效；
- eval.md §4 的过程指标（`process_metrics.json`）；
- 是否要跑第 3b 步的安慰剂对照，由用户决定。

### 第 3b 步：安慰剂对照（eval.md §5 第 2 点，用户同意才跑）

安慰剂运行（placebo）：参数和第 3 步完全相同，只是提议器第二次调用里看到的金标在批次内被打乱，闸门仍用真实金标。成本约等于一次全量运行（约 2100 万输入 token）。

```bash
P=$(.venv/bin/python src/evolve.py init --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt --param placebo=1 [第 3 步用过的其他 --param] | tail -1)
.venv/bin/python src/evolve.py baseline --run-dir $P --concurrency 8
.venv/bin/python src/evolve.py step --run-dir $P --concurrency 8
.venv/bin/python src/evolve.py status --run-dir $P
```

安慰剂运行**不导出、不跑 train_val、不跑 dev**，只比较它接受的改动数和样本外收益是否接近真实运行。

⛔ **停下**：汇报安慰剂运行接受了几个改动、收益是多少，与真实运行对比。

### 第 4 步：预登记，然后跑 dev

1. 按 eval.md §3.1，写 `results/evolve/task2b/<run_id>/preregistration.md`，内容包括：
   - 导出 prompt 的路径和 sha256；
   - 主比较：E 对 B0（reason-v1），B0 的 dev 运行见「已有运行」表；次要比较：E 对 B1、E 对 B2、E+R 对 B2、E+R 对 E；
   - 指标：1 − Jaccard；
   - 判定表：Success / Promising / No effect / Harmful 四档，照抄 eval.md §3.1；
   - OOF（out-of-fold，样本外：在没参与产生改动的折上算出的收益）的定义。spec 没有写怎么算（implementation.md §4 第 2 点），请写出你建议的定义，标注「待老师确认」。

⛔ **停下**（先不要提交）：把预登记文件内容给用户看。OOF 的定义要等用户和老师确认后再提交。

2. 用户确认后，**先提交预登记文件**，再跑 dev，每个配置只跑一次：

   ```bash
   .venv/bin/python src/run.py --task task2b --version reason-v5 --strategy zero-shot --split dev --concurrency 8
   .venv/bin/python src/run.py --task task2b --version reason-v5 --strategy few-shot --selection bm25 --k 10 --split dev --concurrency 8
   ```

3. 对 dev 运行目录执行 `src/evaluate.py`，再用 `src/paired_bootstrap.py` 做预登记里的全部比较。
4. 按 eval.md §7 写 `results/evolve/task2b/<run_id>/REPORT.md`，内容包括：
   - 所有用到的 run_id 和目录（包括原仓库里的 B0、B1 train_val 目录）；
   - 预登记内容；
   - 结果表（OOF、train_val、dev 三处的差值和置信区间）；
   - 迁移比（transfer ratio，dev 收益除以 OOF 收益）；
   - 护栏检查；
   - 过程指标（`process_metrics.json`）；
   - 对照实验：噪声底 τ，以及安慰剂运行（如果跑了）；
   - 最终 prompt 与种子的 diff；
   - 总 token 数。

   报告里所有数字都要能由上面列出的运行目录复算。

⛔ **停下**：汇报 dev 判定结果，以及按 eval.md §8 应该采取的下一步。**不要**自行开始 Task 2a。

## 3. 汇报格式

每次停下时，用中文、简洁地列出以下内容：
- 做了什么；
- 结果数字（附 run_id 和文件路径）；
- 有什么异常；
- 你的建议。

不确定的地方明确标注出来，不要猜。
