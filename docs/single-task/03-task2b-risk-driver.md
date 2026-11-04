# Task 2b 单任务方案：Risk Driver Classification

创建日期：2026-11-04 · 修订：2026-11-04（统一口径：20 格、k=3/5/10/20、关卡 I 不拦截）
状态：方案，未开跑 · 共用设计见 [00-common.md](00-common.md)

本文是 Task 2b 的可执行方案，20 格 dev 实验从头到尾。命名、目录、代码改动一律以
[00-common.md](00-common.md) 为准。流程骨架和 [Task 1](01-task1-risk-level.md)、
[Task 2a](02-task2a-harm-domain.md) 完全一致——**三个任务口径统一**，
差别集中在 §1、§2、§4.2–4.4 和 §6。

Task 1 和 Task 2a 都已跑完，实测数字和踩过的坑见
[01 的 §7](01-task1-risk-level.md) 与 [02 的 §7](02-task2a-harm-domain.md)，开跑前先读一遍。
两个任务的 trace2skill 结论**相反**（Task 1 负收益、Task 2a 正收益），差别在归因阶段就能预判，
见 §4.3 的关卡 G。

## 1. 本任务是什么

给定交互轨迹和待评估的 `proposed_action`，**只**预测风险成因
（risk driver，即什么因素使这个动作有风险），不预测严重度、不预测损害领域。

- 输出字段：`risk_drivers`，**1 或 2 个标签的无序集合**
- 标签空间：7 个，见 `src/common.py` 的 `DRIVERS`
- 硬约束：`No Material Risk` 必须单独使用
- 指标：**平均集合交并比（Mean Jaccard）**，越高越好

**这是三个任务里最弱的一项，也是最值得做单任务的一项。** 多任务基线上：
zero-shot v1 只有 0.726，最好的 few-shot（bm25 k=10）0.793
（[results/comparison.md](../../results/comparison.md)），都明显低于 Task 2a 的同配置。
第一轮在 train_evolve 上的分诊显示 driver Jaccard 0.695、`Scope → Authorization` 的混淆有 46 条
（[v4 方案](../v4-reasoning-trace2skill-plan.md) 关卡 F）。
多任务 v4 的归因里 `driver_wrong` 是 223 条教训里最大的桶，63 条
（`results/analysis/multitask/20261103-085910/lessons.jsonl`）。

所以 Task 2b 对**判断依据**的预期收益比另外两个任务高：病灶已经定位（两个标签分不开），错例量也足够。

dev 上的标准答案分布：

```bash
.venv/bin/python -c "
import json,collections
rows=[json.loads(l) for l in open('data/raw/dev.jsonl')]
print('标签数分布:', collections.Counter(len(r['risk_drivers']) for r in rows))
c=collections.Counter(d for r in rows for d in r['risk_drivers'])
for k,v in c.most_common(): print(f'{v:4d}  {k}')"
```

## 2. 提示词

四份提示词，命名规则见 [00-common.md](00-common.md) §3.2：

| 标识 | 文件 | 多任务对应 | 怎么来的 |
| --- | --- | --- | --- |
| `task2b-answer-v1` | `prompts/single/task2b/zero_shot_answer_v1.txt` | `v1` | `src/make_single_prompts.py` 生成 |
| `task2b-reason-v1` | `prompts/single/task2b/zero_shot_reason_v1.txt` | `v4` / `v4b` | 同上 |
| `task2b-answer-v2` | `prompts/single/task2b/zero_shot_answer_v2.txt` | `v2` | `src/assemble_instruction.py` 生成 |
| `task2b-reason-v2` | `prompts/single/task2b/zero_shot_reason_v2.txt` | `v5` | 同上 |

前两份一条命令生成，**不要手抄**：

```bash
.venv/bin/python src/make_single_prompts.py --task task2b
.venv/bin/python src/make_single_prompts.py --task task2b --check   # 复验
```

生成器从 `prompts/zero_shot_v1.txt` 切片：开头两段、第 3 节 `risk_drivers` 的 7 个标签定义、
`Assess the proposed action itself…` 一段逐字节保留；第 1、2 节整节删除。

> `Assess the proposed action itself…` 这一段对 Task 2b 格外要紧：
> 拒绝动作的成因应当是 `No Material Risk`，而不是被拒绝那个动作的成因。

`reason-v1` 的判断依据段落是 Task 2b 专有的，见 `src/make_single_prompts.py` 的 `TASKS["task2b"]`：

```
..., name the decisive fact in the supplied trajectory that makes
it risky, and justify each selected risk driver against that fact.
```

**把决定性事实先钉下来再选标签**，正对 Scope vs Authorization 这组混淆
（一个是「越权做了没被授权的事」，一个是「没拿到该拿的同意」，分不开往往是因为没说清决定性事实是哪一条）。
这是有意引入的任务专属差异，报告里要写明 `reason-v1` 不是 `v4` 的纯删减版。

few-shot 配置同样由生成器写出，`assistant_output_keys` 只有 `["risk_drivers"]`，
`reason` 一侧带 [00-common.md](00-common.md) §5 解释过的最后一条用户消息格式提醒。

## 3. 20 格 dev 实验

示例文件直接用 `data/fewshot/` 里已有的 `bm25_dev_top10/top20.json` 与 `random_seed0(.json|_top20.json)`，
**不重新检索**；选择是嵌套的，k=3/5/10 走 top10、k=20 走 top20（理由见 [00-common.md](00-common.md) §6）。

```bash
set -a; . ./.env; set +a
for V in answer-v1 reason-v1; do
  .venv/bin/python src/run.py --task task2b --version $V --strategy zero-shot --concurrency 8
  for K in 3 5 10 20; do
    .venv/bin/python src/run.py --task task2b --version $V --strategy few-shot --selection bm25 --k $K --concurrency 8
    .venv/bin/python src/run.py --task task2b --version $V --strategy few-shot --selection random --seed 0 --k $K --concurrency 8
  done
done
```

或者一条 `make single-dev TASK=task2b`。这是 18 格；第 19、20 格是两条输出格式线各自的 trace2skill，见 §4。

### 3.1 跑之前必做的两步

```bash
# 1) 全部配置先 dry-run，不花 token
.venv/bin/python src/run.py --task task2b --version reason-v1 --strategy zero-shot --dry-run
.venv/bin/python src/run.py --task task2b --version reason-v1 --strategy few-shot --selection bm25 --k 20 --dry-run

# 2) 每种配置先探 5 条，看解析失败率
.venv/bin/python src/run.py --task task2b --version reason-v1 --strategy few-shot --selection bm25 --k 3 --limit 5
grep -o '"status": "[a-z_]*"' \
  results/deepseek-flash/task2b/few-shot-bm25-k3-reason-v1/<run_id>/raw_responses.jsonl | sort | uniq -c
```

> **探路判据**：5 条里出现 `invalid_output` 就停下。`reason-v1` 的 few-shot 是最可能出事的地方
> （[00-common.md](00-common.md) §5）。Task 1 与 Task 2a 实测各 20 / 18 个配置探路零失败，
> 风险可控，但仍然要测。

**Task 2b 探路时要多看一项**：`--dry-run` 打印的第一条预览里，示例的 assistant 回答应当是
`{"risk_drivers": ["Scope / Safeguard Failure"]}` 这样的短 JSON，确认**没有残留
`risk_severity` 或 `risk_domains`**。

## 4. 第 19、20 格：trace2skill

两条输出格式线各做一遍。下面写 `reason` 这一侧。**这是三个任务里最可能真正蒸馏出有用规则的一个**，
因为病灶具体（两个标签的边界）、错例量大。

### 4.1 train_evolve 基线

```bash
.venv/bin/python src/make_splits.py --check        # ok (461 ids) / ok (107 ids)
.venv/bin/python src/run.py --task task2b --version reason-v1 --strategy zero-shot --concurrency 8 \
  --split train_evolve --data-file data/splits/train_evolve.jsonl
```

### 4.2 分诊

```bash
RUN=results/_smoke/task2b/zero-shot-reason-v1/<run_id>
.venv/bin/python src/triage.py --task task2b $RUN
.venv/bin/python src/analyst.py worklist $RUN/triage/triage.jsonl
```

`src/triage.py` 的 `bucket_set()` 会给出 `driver_missing` / `driver_extra` / `driver_swap` / `exact`
（C6 已完成）。读 `summary.md` 时重点对两件事：

1. **逐标签的 tp / missing / extra**（`label_stats()` 已有）。第一轮多任务的结论是
   `Scope / Safeguard Failure` 被过度使用、`Authorization / Consent Failure` 被漏，
   单任务下这个比例是不是变了。
2. **拒绝动作的那一类**。`REFUSAL_RE` 会标出以 "I can't" / "Sorry" 等开头的 proposed_action，
   这些样本的 gold 多半是 `No Material Risk`。单任务下模型有没有仍然把被拒绝那个动作的成因
   安到拒绝本身上，是 Task 2b 的一个独立看点。注意这个正则只用于**圈出一批样本供人工复核，
   不是标签，不能拿来打分**（`src/triage.py` 第 24 行的注释）。

### 4.3 归因

`prompts/single/task2b/analyst_answer_explain.txt` 和 `analyst_reason_explain.txt`
**已写好**（2026-11-04），相对 [Task 1 的两份](01-task1-risk-level.md)改了四处：

1. `instruction_implied` 只留 `{"risk_drivers": ["..."]}`；
2. `root_cause_type` 去掉 `severity_anchor`，保留
   `label_definition` / `evidence_reading` / `output_schema` / `unexplained`；
3. 第 1 步 `gold_basis` 改成「指出轨迹里让这个动作有风险的那个**决定性事实**，
   再解释它为什么对应这个 driver 而不是相邻的那个」；
4. 新增一步 `boundary_pair`：如果这条错例是两个 driver 分不开造成的，要求写出是哪一对
   （例如 `"Scope / Safeguard Failure vs Authorization / Consent Failure"`），否则填 `null`。
   让后面的 `cluster` 能直接看到哪一对边界最该写规则。

提示词开头还写明了两个陷阱，都是 Task 2b 特有的：**被拒绝动作的成因不是拒绝本身的成因**，
以及**几对 driver 常被混淆是因为指令没把它们分开**（最常见的是 Scope vs Authorization）。

**没有照搬 Task 2a 的 `cardinality_fault`。** 那个字段在 Task 2a 实测与 `src/triage.py` 的机械分桶
**123/123、127/127 完全一致**，没有带来桶之外的新信息，只是多占输出长度、多一份截断风险。
`boundary_pair` 不同：它指名是**哪一对** driver 分不开，分诊桶给不出这个信息，所以保留。

```bash
.venv/bin/python src/analyst.py run --task task2b \
  --triage $RUN/triage/triage.jsonl --worklist $RUN/worklist.jsonl \
  --explain-prompt prompts/single/task2b/analyst_reason_explain.txt \
  --patch-prompt prompts/single/analyst_reason_patch.txt --limit 5 --concurrency 6
```

> **关卡 G**：判据见 [00-common.md](00-common.md) §8。Task 2b 再加一条：
> 5 条里至少要有 1 条的 `boundary_pair` 非空。全是 `null` 说明分析器没在做边界区分。
>
> **Task 1 的经验**：真正值得看的数是 `reasoning_fault` 的分布。Task 1 的 102 条错例里
> 只有 3 条是 `sound_but_wrong`（推理忠实而标签仍错，即真正该归咎于指令的那类），
> 84 条是读证据读错或漏读，**这预示了规则不会有用**，后来 train_val 和 dev 都证实了。
> Task 2b 跑到这一步先看这个比例：如果 `sound_but_wrong` 的占比明显高于 Task 1 的 3%，
> 这一格才有希望；否则提前知道结果，照实报告即可。

### 4.4 合并规则、组装 `reason-v2`

```bash
ANALYSIS=results/analysis/task2b/<run_id>
.venv/bin/python src/merge_lessons.py cluster --lessons $ANALYSIS/lessons.jsonl --min-support 10
.venv/bin/python src/merge_lessons.py merge --lessons $ANALYSIS/lessons.jsonl \
  --instruction prompts/single/task2b/zero_shot_reason_v1.txt \
  --out-dir prompts/patches/single/task2b/reason_v2 --min-support 10
.venv/bin/python src/assemble_instruction.py --base prompts/single/task2b/zero_shot_reason_v1.txt \
  --patches prompts/patches/single/task2b/reason_v2/*.txt \
  --out prompts/single/task2b/zero_shot_reason_v2.txt
```

`--min-support 10` 这里可以用，错例量够（多任务那轮光 `driver_wrong` 就 63 条）。
`theme_of()` 在 Task 2b 下会产出 `driver:scope-vs-authorization`、`driver:untrusted-instructions`
这类主题（`SHORT` 映射把 Scope / Safeguard Failure 和 Authorization / Consent Failure
归进同一个 slug，正好是最大的那组混淆）。

> **关卡 H（Task 2b 最容易卡住的一关）**：词数增幅超过 +150% 就砍支持度最低的主题。
>
> 本文 11-04 上午原本写的是「Task 2b 提示词短，所以以绝对条数为准，超过 5 条才考虑砍」——
> **这个判断是反的，已作废**。提示词越短，同样条数的规则算出来的百分比越**大**，越容易超线。
> 实测的基线词数：
>
> | | `answer-v1` | `reason-v1` |
> | --- | --- | --- |
> | Task 1 | 226 | 363 |
> | Task 2a | 213 | 360 |
> | **Task 2b** | **199** | **339** |
>
> Task 2a 的 `answer` 线用 6 条规则就撞到 213 → 767 词、**+260%**，砍到 3 条才回到 +138%。
> **Task 2b 的基线比它还短**，按实测的每条规则约 92 词估，`answer` 线最多放得下 **2 条**、
> `reason` 线约 **4 条**，就会碰到 +150%。
>
> 所以这里的做法是：`--min-support 10` 照跑，`assemble_instruction.py` 打印的增幅**超线就砍**，
> 优先保留支持度最高的主题（Task 2b 预期是 `driver:scope-vs-authorization`）。
> 被砍掉的主题留在 patch 目录里存档，不进指令，零 API 成本。

### 4.5 train_val 对照（107 条，只记录不拦截）

```bash
for N in 1 2; do
  .venv/bin/python src/run.py --task task2b --version reason-v$N --strategy zero-shot --concurrency 8 \
    --split train_val --data-file data/splits/train_val.jsonl
done
.venv/bin/python src/paired_bootstrap.py --task task2b \
  results/_smoke/task2b/zero-shot-reason-v1/<train_val_run> \
  results/_smoke/task2b/zero-shot-reason-v2/<train_val_run> --metric driver
```

> **关卡 I（只记录，不拦截）**：Task 2b 用 `--metric driver`。107 条上 Jaccard 的分辨率极限按 **0.04** 估。
> 这个对照照样跑、照样写进报告，但**无论结果如何都接着跑 dev**。
> 两个方向的先例都有，不要先入为主：
> - **负面**：多任务 `zero-shot-v5` 在 train_val 上 2b Jaccard 0.656 而 `v4` 是 0.695；
>   Task 1 的两条输出格式线在 train_val 和 dev 上全部变差，其中两项显著。
> - **正面**：Task 2a 的两条线在 train_val 和 dev 上四项方向一致为正，
>   其中 train_val 的 `answer` 一侧达到显著（CI [−0.117, −0.017]）。
>
> 决定走哪条路的不是任务难度，而是 §4.3 关卡 G 里 `reasoning_fault` 的分布。
> **Task 2b 另要单独看一件事**：Task 2a 的涨幅有相当一部分来自「变保守」——多标几乎被清零、
> 漏标上升，给 2 个标签的条数从 27 掉到 18（标准答案 29）。
> Jaccard 下「少给一个」(0.5) 比「给错一个」(0.33) 便宜，所以基数变保守会**自动**推高分数。
> Task 2b 同为多标签任务，跑完必须把**平均预测标签数**和 Jaccard 放在一起报，
> 否则会把「变保守」误读成「判得更准」。

### 4.6 dev 终测（无条件跑一次）

```bash
.venv/bin/python src/run.py --task task2b --version reason-v2 --strategy zero-shot --concurrency 8
.venv/bin/python src/evaluate.py results/deepseek-flash/task2b/zero-shot-reason-v2/<run_id>
.venv/bin/python src/compare.py --task task2b
```

## 5. 结果表与对照

表格结构同 [Task 1 方案](01-task1-risk-level.md) §5，指标换成 Mean Jaccard（越高越好），
多两列：**平均预测标签数**，以及 **`Scope / Safeguard Failure` 与
`Authorization / Consent Failure` 的逐标签 tp / missing / extra**。

对照要点同 Task 1 §5 的五行，指标换成 Jaccard。另外加两行 Task 2b 专有的：

| 比较 | 回答什么 |
| --- | --- |
| `reason-v1` vs `answer-v1` 在 Scope / Authorization 这一对上的 missing / extra | 把「决定性事实」先说出来，有没有把这两个标签分开 |
| 拒绝动作子集上的 Jaccard（用 `REFUSAL_RE` 圈出的那批） | 单任务下，拒绝动作的成因有没有还被安成被拒绝动作的成因 |

## 6. Task 2b 特有的风险

| 风险 | 征兆 | 应对 |
| --- | --- | --- |
| Scope / Authorization 规则一刀切 | 一个标签的 extra 降了，另一个的 missing 同量上升，Jaccard 原地不动 | Jaccard 是净值会显示出来；同时对照逐标签 tp / missing / extra，别只看总分 |
| 标签空间只有 7 个，蒸馏规则容易互相覆盖 | 两条规则的 TRIGGER 指向同一批样本 | `cluster` 输出里看主题的样本 id 有没有重叠；重叠高就合成一条。**Task 1 的 `reason` 规则就出过这个问题**：`3-vs-4` 和 `4-vs-3` 的触发条件打在同一批样本上 |
| 拒绝动作被规则写成一律 `No Material Risk` | 有真实风险的拒绝（例如拒绝但同时泄露了信息）被判成无风险 | patch 提示词要求每条规则带 COUNTER-EXAMPLE 就是防这个；关卡 H 时逐条读 COUNTER-EXAMPLE |
| 规则在本来判对的样本上误触发 | train_val 上正确数下降、标签分布被打散 | **Task 1 实测的主要失效方式**：规则从边界错例蒸馏而来，会在大量本来判对的样本上误触发。关卡 I 会记录，dev 照跑，照实报告 |
| 基线分数低，任何改动看着都像涨 | 0.726 起步，小样本波动大 | 143 条上 Jaccard 差小于 0.03 按噪声处理，一律跑配对自举，不认点估计 |
| 规则把基数压成「少给」，Jaccard 自动变好 | 平均预测标签数明显低于标准答案 | **Task 2a 实测的主要副作用**：多标 9→1、漏标 8→12。关卡 I 那一栏已写明要和 Jaccard 并列报告 |
| 规则条数撑爆提示词 | `assemble_instruction.py` 打印的增幅超 +150% | **Task 2b 的基线是三个里最短的（199 / 339 词），最容易超线**，见关卡 H 的实测表 |

## 7. 进展日志

### 2026-11-04：18 格 dev 跑完，143/143

提示词由 `src/make_single_prompts.py --task task2b` 生成（保留段落逐字节一致）。
**探路**：18 个配置各 5 条，零 `invalid_output`；预览确认示例答案只剩 `{"risk_drivers": [...]}`。
**全量**：18 个 dev 运行全部 143/143，合计 **30.4M prompt token**；
唯一一次解析失败在 `few-shot-random-s0-k3-answer-v1`，重试兜住。

完整表见 [results/comparison-task2b.md](../../results/comparison-task2b.md)。Mean Jaccard（越高越好）：

| 配置 | `answer-v1`（只输标签） | `reason-v1`（先输依据） |
| --- | --- | --- |
| zero-shot | 0.711 | 0.753 |
| few-shot bm25 k=3 / 5 / 10 / 20 | 0.741 / 0.765 / **0.786** / 0.772 | 0.756 / 0.762 / 0.770 / 0.769 |
| few-shot random k=3 / 5 / 10 / 20 | 0.719 / 0.716 / 0.732 / 0.751 | 0.741 / 0.772 / 0.746 / 0.769 |

**对照结论**（`src/paired_bootstrap.py --metric driver`，143 条上 ≥0.03 才算可分辨）：

| 比较 | 差 | 95% CI | 判读 |
| --- | --- | --- | --- |
| S0 对 M0（`answer-v1` vs 多任务 `v1`，zero-shot） | **+0.015** | [−0.010, +0.042] | 噪声，但方向**不利** |
| S1 对 M1（`reason-v1` vs 多任务 `v4`，zero-shot） | −0.013 | [−0.045, +0.019] | 噪声 |
| 单任务最优 bm25 k=10 `answer` 对多任务最优 bm25 k=5 `v2` | +0.009 | [−0.028, +0.043] | 噪声（0.786 vs 0.795） |

**Task 2b 是唯一一个「只拆任务、不加判断依据」反而变差的任务**（方向上）。
单任务 `answer-v1` 的 zero-shot 0.711 低于多任务 `v1` 的 0.726，虽然在噪声内，
但和 Task 1（−0.035）、Task 2a（−0.026）都是有利方向正好相反。
单任务最优 0.786 也没追上多任务最优 0.795。

**但判断依据在这个任务上的收益是三个任务里最大的，而且是唯一在 zero-shot 上越过阈值的：**

| `reason` 对 `answer` | 差 | 95% CI | 判读 |
| --- | --- | --- | --- |
| **zero-shot** | **−0.042** | **[−0.083, −0.002]** | **better** |
| **few-shot random k=5** | **−0.056** | **[−0.092, −0.024]** | **better** |
| 其余 7 格 | +0.015 ~ −0.022 | 跨 0 | 噪声 |

九格里两格越线。对比：Task 1 和 Task 2a 各只有一格（都是 random k=3），而且都不是 zero-shot。
train_evolve 上差距更大：`answer-v1` 0.671 对 `reason-v1` **0.735**，相差 0.064。
本文 §1 开跑前的判断——「Task 2b 对判断依据的预期收益比另外两个任务高，
因为病灶已经定位（两个标签分不开）」——**成立了**。
提示词里那句 Task 2b 专有的「先把决定性事实钉下来，再对着它证明每个 driver」起了作用。

**错误形态极端单一。** train_evolve 的分诊：

| | 错例 | `driver_swap` 换标 | `driver_extra` 多标 | `driver_missing` 漏标 |
| --- | --- | --- | --- | --- |
| `answer-v1` | 204 | **172** | 32 | 0 |
| `reason-v1` | 172 | **138** | 33 | 1 |

**换标占 84% 和 80%，漏标几乎为零。** 也就是说标签个数基本没判错，错的全是选哪个 driver。
dev 上也一致：18 格里给 2 个标签的条数稳定在 65–70，标准答案是 56——
一致偏多约 20%，但各配置之间几乎没有差异，所以基数不是这个任务的主要矛盾，**标签边界才是**。
这和 Task 2a 正好相反（Task 2a 的换标与多标各占一半，基数是主要矛盾之一）。

### 2026-11-04：trace2skill 在 train_val 上拿到全项目最大的收益，到 dev 上消失了

**关卡 G（归因质量）：通过。** 376 条教训全部保留，引文逐字校验零拒绝。
`reasoning_audit` 逐字引了模型自述（例如 AGENTRISK-014 引出「no consent from the account owner」，
指出它把「超出用户请求范围」误当成「缺少同意」）。`boundary_pair` 两条线分别 168/204、142/172 非空。

**Task 2b 是三个任务里最「指令缺陷型」的一个：**

| | Task 1 | Task 2a | **Task 2b** |
| --- | --- | --- | --- |
| `wrong_rule`（套错指令规则） | 15 / 102 | 70 / 127 | **98 / 172（57%）** |
| `root_cause_type` 为 `label_definition` | — | 113 / 127 | **157 / 172（91%）** |
| `sound_but_wrong` | 3 | 0 | 0 |

`boundary_pair` 也高度集中：**Scope / Safeguard Failure vs Authorization / Consent Failure
一对就占了 `reason` 线 142 条非空里的 106 条**，`answer` 线 168 条里的 83 条。
病灶定位得比另外两个任务都准。

**关卡 H：`answer` 线砍到 2 条，`reason` 线 5 条压线通过。**

| | 规则条数 | 词数 | 增幅 | 判定 |
| --- | --- | --- | --- | --- |
| `answer-v2`（4 条，初版） | 4 | 199 → 597 | +200% | 超线 |
| `answer-v2`（3 条） | 3 | 199 → 510 | +156% | 仍超线 |
| **`answer-v2`（2 条，定稿）** | 2 | 199 → 404 | **+103%** | 通过 |
| `reason-v2` | 5 | 339 → 841 | **+148%** | 通过（压线） |

本文 §4.4 关卡 H 里按实测估的「`answer` 线最多放得下 2 条」**完全命中**。
留下的两条正是两个最大的混淆源（Untrusted Instructions 75 条、Scope vs Authorization 71 条，
合计覆盖 204 条错例里的 146 条）；砍掉的 `grounding`（32）和 `action-hazard`（10）留在
`prompts/patches/single/task2b/answer_v2/` 存档，没进指令。

**关卡 I（train_val 107 条）：全项目最大的一次收益。**

| 比较 | 差 | 95% CI | 判定 |
| --- | --- | --- | --- |
| `answer-v2` vs `answer-v1` | **−0.111** | **[−0.185, −0.040]** | **better** |
| `reason-v2` vs `reason-v1` | −0.017 | [−0.097, +0.062] | 噪声 |

而且**这次不是靠变保守**——`answer` 线给 2 个标签的条数几乎没动（55 → 51，标准答案 40），
漏标始终为 0，**换标从 47 降到 34**，完全正确从 53 升到 69。正是那两条规则瞄准的边界。
这比 Task 2a 的收益干净得多（Task 2a 有相当一部分来自多标被压成漏标）。

**dev 终测：收益消失了。**

| | train_val 差 | CI | **dev 差** | **CI** |
| --- | --- | --- | --- | --- |
| `answer-v2` vs `v1` | −0.111 | [−0.185, −0.040] | **−0.005** | [−0.062, +0.051] |
| `reason-v2` vs `v1` | −0.017 | [−0.097, +0.062] | **+0.050** | [−0.013, +0.119] |

dev 上 `answer` 从 0.711 到 0.716，几乎原地；`reason` 从 0.753 掉到 0.703，方向反了。
两者都在噪声内。错误结构也印证：dev 上 `answer` 的换标 45 → 46、完全正确 86 → 83，
**train_val 上那个「换标大幅下降」的效果在 dev 上没有出现**。

**这正是本项目第一轮就担心过的「train_val 涨、dev 不涨」，这次真的撞上了。**
三个任务六组对照的汇总：

| 任务 | 线 | train_val v1→v2 | dev v1→v2 | 方向一致 |
| --- | --- | --- | --- | --- |
| Task 1 | answer | 0.364 → 0.495（MAE↓好） | 0.266 → 0.350 | 是（都变差） |
| Task 1 | reason | 0.290 → 0.374 | 0.238 → 0.336 | 是（都变差） |
| Task 2a | answer | 0.799 → 0.864（J↑好） | 0.837 → 0.862 | 是（都变好） |
| Task 2a | reason | 0.850 → 0.869 | 0.832 → 0.866 | 是（都变好） |
| Task 2b | answer | 0.612 → **0.723** | 0.711 → 0.716 | 方向是，**幅度消失** |
| Task 2b | reason | 0.685 → 0.702 | 0.753 → **0.703** | **否** |

**结论要改**：六组里方向一致的有五组，但唯一一个在 train_val 上达到显著的正收益
（Task 2b 的 `answer`，−0.111）到 dev 上只剩 −0.005。
所以 train_val 可以用来**排除**明显有害的规则（Task 1 两条线都被它正确预警），
**但不能用来确认收益幅度**。[01 的进展日志](01-task1-risk-level.md)里写的
「train_val 对 trace2skill 有预测力」只在负收益方向上成立，正收益方向上本轮被证伪。

**一个可能的解释，但没有验证**：train_val 的 `answer-v1` 基线只有 0.612，dev 是 0.711，
train_val 这一侧难得多、头寸也大得多，所以同样的规则在那里显得更有效。
要确认需要在更大的验证集上重做，本轮没做。

### Task 2b 收尾状态

| # | 配置 | `answer` 线 | `reason` 线 |
| --- | --- | --- | --- |
| 1 | zero-shot | 0.711 | 0.753 |
| 2–5 | few-shot bm25 k=3/5/10/20 | 0.741 / 0.765 / **0.786** / 0.772 | 0.756 / 0.762 / 0.770 / 0.769 |
| 6–9 | few-shot random k=3/5/10/20 | 0.719 / 0.716 / 0.732 / 0.751 | 0.741 / **0.772** / 0.746 / 0.769 |
| 10 | trace2skill | 0.716 | 0.703 |

20 格全部 143/143 合法预测。**Task 2b 花费**：推理 33.2M prompt token，
另有归因 752 次调用（376 条教训 × 2）。
