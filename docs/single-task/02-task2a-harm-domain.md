# Task 2a 单任务方案：Harm Domain Classification

创建日期：2026-11-04 · 修订：2026-11-04（统一口径：20 格、k=3/5/10/20、关卡 I 不拦截）
状态：方案，未开跑 · 共用设计见 [00-common.md](00-common.md)

本文是 Task 2a 的可执行方案，20 格 dev 实验从头到尾。命名、目录、代码改动一律以
[00-common.md](00-common.md) 为准，本文只写 Task 2a 特有的东西。流程骨架和
[Task 1 方案](01-task1-risk-level.md) 完全一致——**三个任务口径统一**，差别集中在
§1、§2、§4.2–4.4 和 §6。

Task 1 已经跑完，它踩过的坑和实测数字见 [01 的 §7 进展日志](01-task1-risk-level.md)，开跑前值得先读一遍。

## 1. 本任务是什么

给定交互轨迹和待评估的 `proposed_action`，**只**预测损害领域
（harm domain，即这个动作可能损害什么），不预测严重度、不预测风险成因。

- 输出字段：`risk_domains`，**1 或 2 个标签的无序集合**
- 标签空间：11 个，见 `src/common.py` 的 `DOMAINS`
- 硬约束：`No Material Harm` 必须单独使用，不能和别的标签共存（`src/common.py` 的 `_check_labels()`）
- 指标：**平均集合交并比（Mean Jaccard，逐样本算预测与标准标签集合的交集占并集之比再平均）**，越高越好

和 Task 1 的根本不同：这是**多标签分类（multi-label classification，即一条样本可以同时属于多个类别）**。
判错有两种形态——**漏标**（gold 有、pred 没有）和**多标**（pred 有、gold 没有），
两者病因不同，分诊和归因都要分开看。

多任务基线的已知病灶：模型**倾向多给第二个标签**（[README.md](../../README.md)，
运行 `multitask/zero-shot-v1/20261022-051556`）。Task 2a 的 Jaccard 在多任务里是三项中最高的
（zero-shot v1 为 0.811，few-shot 最高 0.873），**提升空间本来就比另外两个任务小**，判读时要记住。

dev 上标准答案的标签分布与「几个标签」的分布：

```bash
.venv/bin/python -c "
import json,collections
rows=[json.loads(l) for l in open('data/raw/dev.jsonl')]
print('标签数分布:', collections.Counter(len(r['risk_domains']) for r in rows))
c=collections.Counter(d for r in rows for d in r['risk_domains'])
for k,v in c.most_common(): print(f'{v:4d}  {k}')"
```

## 2. 提示词

四份提示词，命名规则见 [00-common.md](00-common.md) §3.2：

| 标识 | 文件 | 多任务对应 | 怎么来的 |
| --- | --- | --- | --- |
| `task2a-answer-v1` | `prompts/single/task2a/zero_shot_answer_v1.txt` | `v1` | `src/make_single_prompts.py` 生成 |
| `task2a-reason-v1` | `prompts/single/task2a/zero_shot_reason_v1.txt` | `v4` / `v4b` | 同上 |
| `task2a-answer-v2` | `prompts/single/task2a/zero_shot_answer_v2.txt` | `v2` | `src/assemble_instruction.py` 生成 |
| `task2a-reason-v2` | `prompts/single/task2a/zero_shot_reason_v2.txt` | `v5` | 同上 |

前两份一条命令生成，**不要手抄**：

```bash
.venv/bin/python src/make_single_prompts.py --task task2a
.venv/bin/python src/make_single_prompts.py --task task2a --check   # 复验
```

生成器从 `prompts/zero_shot_v1.txt` **切片**，所以保留的段落逐字节一致：开头两段、
第 2 节 `risk_domains` 的 11 个标签定义、`Assess the proposed action itself…` 一段，
全部原样搬过来；第 1 节 `risk_severity` 和第 3 节 `risk_drivers` 整节删除；
输出格式改成只有一个键。`tests/test_reasoning_output.py` 的 `SingleTaskTests` 会守住这件事。

> **一处删除的连带影响**：v1 第 1 节里有一句 `Assess severity within the relevant harm domain.`
> 把两个任务绑在一起。它属于第 1 节，随第 1 节整节删除，**不会**出现在 Task 2a 的提示词里，
> 否则任务拆分就不干净了。生成器的切片逻辑保证了这一点。

`reason-v1` 的判断依据段落是 Task 2a 专有的，见 `src/make_single_prompts.py` 的 `TASKS["task2a"]`：

```
..., and justify
each selected harm domain, including why a second domain is or is not added.
```

`including why a second domain is or is not added` 针对已知的「多给第二个标签」偏置：
**逼模型把「加不加第二个标签」这个决定说出来**，而不是顺手加上。这是有意引入的任务专属差异，
报告里要写明 `reason-v1` 不是 `v4` 的纯删减版。

few-shot 配置同样由生成器写出，`assistant_output_keys` 只有 `["risk_domains"]`，
`reason` 一侧带 [00-common.md](00-common.md) §5 解释过的最后一条用户消息格式提醒。

## 3. 20 格 dev 实验

示例文件直接用 `data/fewshot/` 里已有的 `bm25_dev_top10/top20.json` 与
`random_seed0(.json|_top20.json)`，**不重新检索**；选择是嵌套的，k=3/5/10 走 top10、k=20 走 top20。

```bash
set -a; . ./.env; set +a
for V in answer-v1 reason-v1; do
  .venv/bin/python src/run.py --task task2a --version $V --strategy zero-shot --concurrency 8
  for K in 3 5 10 20; do
    .venv/bin/python src/run.py --task task2a --version $V --strategy few-shot --selection bm25 --k $K --concurrency 8
    .venv/bin/python src/run.py --task task2a --version $V --strategy few-shot --selection random --seed 0 --k $K --concurrency 8
  done
done
```

或者一条 `make single-dev TASK=task2a`。这是 18 格；第 19、20 格是两条输出格式线各自的 trace2skill，见 §4。

### 3.1 跑之前必做的两步

```bash
# 1) 全部配置先 dry-run，不花 token
.venv/bin/python src/run.py --task task2a --version reason-v1 --strategy zero-shot --dry-run
.venv/bin/python src/run.py --task task2a --version reason-v1 --strategy few-shot --selection bm25 --k 20 --dry-run

# 2) 每种配置先探 5 条，看解析失败率
.venv/bin/python src/run.py --task task2a --version reason-v1 --strategy few-shot --selection bm25 --k 3 --limit 5
grep -o '"status": "[a-z_]*"' \
  results/deepseek-flash/task2a/few-shot-bm25-k3-reason-v1/<run_id>/raw_responses.jsonl | sort | uniq -c
```

> **探路判据**：5 条里出现 `invalid_output` 就停下。`reason-v1` 的 few-shot 是最可能出事的地方。
> Task 1 实测 20 个配置探路零失败，全量只有 1 条样本需要第三次重试，所以这个风险是可控的，但要测。

**Task 2a 探路时要多看一项**：`--dry-run` 打印的第一条预览里，示例的 assistant 回答应当是
`{"risk_domains": ["Privacy / Confidentiality"]}` 这样的短 JSON，确认**没有残留
`risk_severity` 或 `risk_drivers`**。`src/run.py` 的 `dry_run()` 会按任务校验每条示例答案，
字段多了会直接报错，但还是人眼扫一遍。

## 4. 第 19、20 格：trace2skill

两条输出格式线各做一遍，`answer-v2` 的规则从 `answer-v1` 的错误蒸馏，`reason-v2` 的从 `reason-v1` 的错误蒸馏。
下面写 `reason` 这一侧，另一侧把命令里的 `reason` 换成 `answer`。

### 4.1 train_evolve 基线

```bash
.venv/bin/python src/make_splits.py --check        # ok (461 ids) / ok (107 ids)
.venv/bin/python src/run.py --task task2a --version reason-v1 --strategy zero-shot --concurrency 8 \
  --split train_evolve --data-file data/splits/train_evolve.jsonl
```

### 4.2 分诊：Task 2a 的桶拆成漏标 / 多标 / 换标

```bash
RUN=results/_smoke/task2a/zero-shot-reason-v1/<run_id>
.venv/bin/python src/triage.py --task task2a $RUN
.venv/bin/python src/analyst.py worklist $RUN/triage/triage.jsonl
```

`src/triage.py` 的 `bucket_set()` 已经实现了这三个桶（C6 已完成）：

| 桶 | 条件 | 病因假设 |
| --- | --- | --- |
| `domain_missing` | gold ⊃ pred（只漏不多） | 模型没看出第二个直接损害 |
| `domain_extra` | pred ⊃ gold（只多不漏） | 已知的「多给第二个标签」偏置 |
| `domain_swap` | 两边互有出入 | 标签定义分不开，典型是 Privacy vs Security |

`label_stats()`（逐标签的 tp / missing / extra）直接给出前两个桶的总量。
读 `$RUN/triage/summary.md` 时重点看哪个标签的 `extra` 最高。

### 4.3 归因

`prompts/single/task2a/analyst_answer_explain.txt` 和 `analyst_reason_explain.txt`
**已写好**（2026-11-04），相对 [Task 1 的两份](01-task1-risk-level.md)改了四处：

1. `instruction_implied` 只留 `{"risk_domains": ["..."]}`；
2. `root_cause_type` 去掉 `severity_anchor`（Task 2a 没有等级），保留
   `label_definition` / `evidence_reading` / `output_schema` / `unexplained`
   （都在 `src/analyst.py` 的 `ROOT_CAUSES` 白名单里，不会被当成非法值丢弃）；
3. 第 1 步 `gold_basis` 改成「解释标准答案为什么是这 1 个（或这 2 个）领域，
   **以及为什么不是相邻的那个领域**」，并要求引用指令里
   `directly affected domains` 和 `an additional direct harm, not a speculative
   downstream consequence` 这两句原话；
4. 新增一步 `cardinality_fault`，取值 `missing` / `extra` / `swap` / `none`，
   让后面的规则能分开治「该加第二个没加」和「不该加却加了」。提示词开头专门写明
   **治好一种往往会让另一种变差**，逼分析器先表态是哪一种。

`reason` 一侧另有 `reasoning_audit` / `reasoning_fault` 两步（和 Task 1 同构），
并特别要求审计模型关于「加不加第二个领域」那句话——这正是 `reason-v1` 指令额外要求它说出来的东西。
`cardinality_fault` 落在 `lessons.jsonl` 的 `explain` 字段里，不是顶层字段，统计时从那里取。

出规则的提示词用共用的 `prompts/single/analyst_reason_patch.txt`（已在库，三任务通用）。

```bash
.venv/bin/python src/analyst.py run --task task2a \
  --triage $RUN/triage/triage.jsonl --worklist $RUN/worklist.jsonl \
  --explain-prompt prompts/single/task2a/analyst_reason_explain.txt \
  --patch-prompt prompts/single/analyst_reason_patch.txt --limit 5 --concurrency 6
```

> **关卡 G**：判据见 [00-common.md](00-common.md) §8，Task 2a 再加一条：
> 5 条里 `cardinality_fault` 不能全是同一个值——全是 `extra` 说明工作清单取样偏了。
>
> **Task 1 的经验**：真正值得看的数是 `reasoning_fault` 的分布。Task 1 的 102 条错例里
> 只有 3 条是 `sound_but_wrong`（推理忠实而标签仍错，即真正该归咎于指令的那类），
> 84 条是读证据读错或漏读——**这预示了后面的规则不会有用**。
> Task 2a 跑到这一步时先看这个比例，它比关卡 I 早得多地告诉你结果。

### 4.4 合并规则、组装 `reason-v2`

```bash
ANALYSIS=results/analysis/task2a/<run_id>
.venv/bin/python src/merge_lessons.py cluster --lessons $ANALYSIS/lessons.jsonl --min-support 5
.venv/bin/python src/merge_lessons.py merge --lessons $ANALYSIS/lessons.jsonl \
  --instruction prompts/single/task2a/zero_shot_reason_v1.txt \
  --out-dir prompts/patches/single/task2a/reason_v2 --min-support 5
.venv/bin/python src/assemble_instruction.py --base prompts/single/task2a/zero_shot_reason_v1.txt \
  --patches prompts/patches/single/task2a/reason_v2/*.txt \
  --out prompts/single/task2a/zero_shot_reason_v2.txt
```

**这里原本写的是 `--min-support 5`，实跑改回了和 Task 1 一致的 10。**
当初取 5 的理由是「多任务那轮 223 条教训里 `domain_wrong` 只有 26 条，单独蒸馏错例会更少」——
**这个估计错了**：多任务里 domain 只是三个字段之一，单任务 Task 2a 自己就有 123 / 127 条错例，
`min-support 10` 下两条线各留 6 / 5 个主题，绰绰有余。改用 10 让两个任务的关卡标准一致。
`cluster` 仍然先打印支持度分布，真的不够再往下调并记录。

`theme_of()` 在 Task 2a 下会产出 `domain:privacy-vs-security`、`domain:no-harm` 这类主题
（`src/merge_lessons.py` 的 `SHORT` 映射把 Privacy / Confidentiality 和
Security / System Integrity 归进同一个 slug，正好对应最常见的那组混淆）。

> **关卡 H**：词数增幅超过 +150% 就砍支持度最低的主题。Task 2a 的基础提示词本来就比 Task 1 长
> （11 个标签定义），同样条数算出来的百分比会偏小，**所以这里同时看绝对条数：超过 5 条就要掂量**。
> Task 1 实测 3–4 条规则时增幅是 +107% ~ +118%。

### 4.5 train_val 对照（107 条，只记录不拦截）

```bash
for N in 1 2; do
  .venv/bin/python src/run.py --task task2a --version reason-v$N --strategy zero-shot --concurrency 8 \
    --split train_val --data-file data/splits/train_val.jsonl
done
.venv/bin/python src/paired_bootstrap.py --task task2a \
  results/_smoke/task2a/zero-shot-reason-v1/<train_val_run> \
  results/_smoke/task2a/zero-shot-reason-v2/<train_val_run> --metric domain
```

> **关卡 I（只记录，不拦截）**：Task 2a 用 `--metric domain`，不是 `mae`
> （不指定时 `paired_bootstrap.py` 会按任务自动选对）。107 条上 Jaccard 的分辨率极限按 **0.04** 估。
> 这个对照照样跑、照样写进报告，但**无论结果如何都接着跑 dev**。
> 前车之鉴：多任务 `zero-shot-v5` 在 train_val 上 2a Jaccard 0.770 而 `v4` 是 0.874；
> Task 1 的两条输出格式线也都在 train_val 上变差。**预期这一格大概率也是负收益，照实报告即可。**

### 4.6 dev 终测（无条件跑一次）

```bash
.venv/bin/python src/run.py --task task2a --version reason-v2 --strategy zero-shot --concurrency 8
.venv/bin/python src/evaluate.py results/deepseek-flash/task2a/zero-shot-reason-v2/<run_id>
.venv/bin/python src/compare.py --task task2a
```

## 5. 结果表与对照

表格结构同 [Task 1 方案](01-task1-risk-level.md) §5，把 `MAE` 换成 `Mean Jaccard`（越高越好），
并多两列：**平均预测标签数**和**与 gold 的标签数差**，用来直接看「多给第二个标签」的偏置有没有变。
`src/compare.py --task task2a` 的第 5 节已经给出「给 2 个标签」的条数。

对照要点同 Task 1 §5 的五行，指标换成 Jaccard。另外加一行 Task 2a 专有的：

| 比较 | 回答什么 |
| --- | --- |
| `reason-v1` 的平均预测标签数 vs `answer-v1` 的 | 逼模型说出「加不加第二个标签」的理由，有没有压住多标偏置 |

**Task 1 的经验**：总分看不出来的东西，往往在分布里。Task 1 的 MAE 差全在噪声内，
但平均偏差从多任务的 +0.189 变成单任务加依据的 −0.056。
Task 2a 的对应物就是**平均预测标签数**，一定要单独报。

## 6. Task 2a 特有的风险

| 风险 | 征兆 | 应对 |
| --- | --- | --- |
| 提升空间本来就小 | Jaccard 从 0.811 起步，三项里最高 | 这是判读前提不是故障。0.02 以内的变化一律按噪声写 |
| 错例太少，蒸馏留不下主题 | `cluster` 打印的全部主题都低于 min-support | §4.4 已降到 5；再不够就降到 3 并在报告里写明支持度 |
| `No Material Harm` 的互斥约束被规则写坏 | `invalid_output` 里出现「No Material Harm must be used alone」 | 规则组装后先对 train_val 跑 5 条探路；`_check_labels()` 会拦住，但会浪费三次重试 |
| Privacy 与 Security 混淆被规则一刀切 | 一个标签的 `extra` 降了，另一个的 `missing` 同量上升 | Jaccard 是净值会显示出来；另外对照 `triage` 的逐标签 tp / missing / extra |
| 示例里只剩标签数组，模型照抄示例的标签个数 | few-shot 的平均预测标签数塌向示例均值 | 跑完比对「示例的平均 gold 标签数」与「预测平均标签数」，和多任务同 k 的值比 |

## 7. 进展日志

### 2026-11-04：18 格 dev 跑完，143/143

提示词由 `src/make_single_prompts.py --task task2a` 生成（保留段落逐字节一致）。
**探路**：18 个配置各 5 条，零 `invalid_output`；`--dry-run` 预览确认示例答案只剩
`{"risk_domains": [...]}`，没有残留另外两个任务的字段。
**全量**：18 个 dev 运行全部 143/143，零解析失败，合计 **30.4M prompt token**。

完整表见 [results/comparison-task2a.md](../../results/comparison-task2a.md)。Mean Jaccard（越高越好）：

| 配置 | `answer-v1`（只输标签） | `reason-v1`（先输依据） |
| --- | --- | --- |
| zero-shot | 0.837 | 0.832 |
| few-shot bm25 k=3 / 5 / 10 / 20 | 0.845 / 0.839 / 0.857 / 0.843 | 0.861 / 0.850 / 0.850 / **0.867** |
| few-shot random k=3 / 5 / 10 / 20 | 0.829 / 0.840 / 0.838 / 0.851 | **0.869** / 0.860 / 0.832 / 0.853 |

**对照结论**（`src/paired_bootstrap.py --metric domain`，143 条上 ≥0.03 才算可分辨）：

| 比较 | 差 | 95% CI | 判读 |
| --- | --- | --- | --- |
| S0 对 M0（`answer-v1` vs 多任务 `v1`，zero-shot） | −0.026 | [−0.063, +0.012] | 噪声，方向有利 |
| S1 对 M1（`reason-v1` vs 多任务 `v4`，zero-shot） | −0.012 | [−0.058, +0.034] | 噪声 |
| 单任务最优 `random k=3 + reason-v1` 对多任务最优 `bm25 k=3 + v2` | +0.003 | [−0.027, +0.034] | 噪声（0.869 vs 0.873） |
| `reason` 对 `answer` 逐格（9 格） | −0.041 ~ +0.007 | 八格跨 0 | 只有 random k=3 越线 |

**按总分 Jaccard，任务拆分在 Task 2a 上没有可分辨收益**，这和开跑前的预判一致：
Task 2a 在多任务里本来就是三项中最高的（0.811 起步），提升空间最小。
九格 `reason` 对 `answer` 里只有 random k=3 越线（−0.041，CI [−0.082, −0.003]）——
**和 Task 1 一模一样，又是 random k=3 这一格**。两个任务同一格成为唯一越线者，
要么是这个配置真有特别之处，要么是两次都撞上同一个小样本波动；
现有证据（每个任务只有一个随机种子）不足以区分，报告里只记录不下结论，
要查清需要补 seed 1（[00-common.md](00-common.md) §11 备选 B3）。

**真正的发现：多标签基数偏置几乎被消掉了。**

| 配置 | 143 条里给 2 个标签的条数 |
| --- | --- |
| **标准答案** | **29** |
| 多任务 `zero-shot-v1` | **55** |
| 多任务 `zero-shot-v4` | 42 |
| 多任务 few-shot 最好的几档 | 32–33 |
| 单任务 `zero-shot-answer-v1` | **27** |
| 单任务 `zero-shot-reason-v1` | 35 |
| 单任务 18 格的范围 | 21–35，多数落在 26–30 |

多任务 zero-shot 给出的双标签条数接近标准答案的两倍（55 vs 29），这是
[README.md](../../README.md) 记了很久的「倾向多给第二个标签」。
**只把任务拆出来，这个偏置就基本消失了**：单任务 zero-shot 只输标签给 27 条，几乎正好校准。

但要注意两件事，不能把这条写成「所以单任务更好」：

1. **Jaccard 只涨了 0.026，远小于基数校准的幅度。** 少报 26 条虚假的第二标签，
   单看这一项该值约 +0.09；实际只拿到 +0.026，说明单任务在别处丢了分
   （train_evolve 的分诊显示 `domain_swap` 是最大的桶，见下）。**基数准了，但选错领域的问题还在。**
2. **加判断依据没有压住基数，反而略微推高**。`reason-v1` 的 zero-shot 给 35 条，比 `answer-v1` 的 27 条多；
   train_evolve 上 `domain_extra` 也是 `reason` 更多（52 vs 40）。
   提示词里那句「说明为什么加或不加第二个领域」是专门为压制这个偏置写的，
   **它没有达到预期效果**，照实记下来。

**train_evolve 基线（461 条，各 461/461）**：`answer-v1` domain Jaccard 0.822、`reason-v1` 0.817。
错例分桶（`src/triage.py` 的 `bucket_set()`）：

| | 错例 | `domain_swap` 换标 | `domain_extra` 多标 | `domain_missing` 漏标 |
| --- | --- | --- | --- | --- |
| `answer-v1` | 123 | **58** | 40 | 25 |
| `reason-v1` | 127 | **54** | 52 | 21 |

**换标是最大的桶**，也就是「领域选错了」而不是「个数给错了」，这和上面 Jaccard 涨幅有限是同一件事的两面。

### 2026-11-04：trace2skill 两条线都是正收益——本项目第一次

两套规则分别蒸馏，互不共用来源。流水线全程无人工干预，三处关卡由执行的 agent 判读。

**关卡 G（归因质量）：通过。** 250 条教训全部保留，引文逐字校验零拒绝。
`reasoning_audit` 逐字引了模型自己写的话，并且正好逮到设计时想抓的东西——
例如 AGENTRISK-005 引出模型那句「…also creates a direct legal/compliance exposure…,
so a second domain is warranted」，指认它把下游监管后果当成了直接损害。
`cardinality_fault` 与 `src/triage.py` 的机械分桶 **100% 一致**（123/123、127/127），
说明这个字段是可靠的，但也说明它没带来桶之外的新信息——**下一轮可以省掉这一步**。
归因模型是默认的 `deepseek-flash`，即被分析的模型分析自己，这一点要披露。

**`reasoning_fault` 的分布和 Task 1 完全不同，这是本轮最关键的一个对照：**

| fault | Task 1 | Task 2a | 含义 |
| --- | --- | --- | --- |
| `wrong_rule` | 15 | **70** | 套用了不适用的指令规则 |
| `misread_evidence` | 44 | 30 | 推理断言了轨迹没建立的事 |
| `missed_evidence` | 40 | 27 | 推理没提到决定标签的事实 |
| `sound_but_wrong` | 3 | 0 | 推理忠实而标签仍错 |

Task 1 的错以**读证据**为主（加规则治不了，后来 train_val 和 dev 都证实了）；
Task 2a 有 55% 是**套错规则**，`root_cause_type` 里 113/127 是 `label_definition`，
即指令的领域定义分不开。**这类缺陷正是加规则能治的**，而且结果确实不同。
`02 §4.3` 里写的「先看 `reasoning_fault` 占比，它比关卡 I 早得多地告诉你结果」这条经验成立。

**关卡 H（规则条数）：`answer` 一侧没过，按预案砍了。**

`--min-support 10` 下两条线各出 6 / 5 个主题。组装结果：

| | 规则条数 | 词数 | 增幅 | 判定 |
| --- | --- | --- | --- | --- |
| `answer-v2`（6 条，初版） | 6 | 213 → 767 | **+260%** | **超线，作废** |
| `answer-v2`（3 条，取支持度最高） | 3 | 213 → 507 | +138% | 通过 |
| `reason-v2` | 5 | 360 → 854 | +137% | 通过 |

砍掉的三条（`no-harm` 13、`legal-compliance` 10、`operational-service` 10）留在
`prompts/patches/single/task2a/answer_v2/` 里，没有进指令，零 API 成本。
保留的三条正对查出来的三组混淆：披露行为该标 Privacy 而不是被披露数据的主题领域、
Privacy vs Security 的边界、Physical / Health vs Legal / Compliance 的边界。

**关卡 I（train_val 107 条）与 dev 终测：两条线、两个集合，方向全部为正。**

| 比较 | train_val 差 | 95% CI | dev 差 | 95% CI |
| --- | --- | --- | --- | --- |
| `answer-v2` vs `answer-v1` | **−0.065** | **[−0.117, −0.017]** | −0.026 | [−0.061, +0.009] |
| `reason-v2` vs `reason-v1` | −0.019 | [−0.062, +0.023] | −0.034 | [−0.079, +0.010] |

（差是 1 − Jaccard 的损失差，负号表示变好。）
四个区间里只有 train_val 的 `answer` 一侧不跨 0，其余三个在噪声内，
**所以准确的说法是「四项方向一致为正，一项达到显著」，不是「trace2skill 有效」。**
但这和 Task 1「两条线在两个集合上全部变差、其中两项显著变差」是质的区别。

**收益从哪来——不只是变保守。** train_val 上的错误结构：

| | 完全正确 | 漏标 | 多标 | 换标 |
| --- | --- | --- | --- | --- |
| `answer-v1` → `v2` | 75 → **85** | 8 → 12 | 9 → **1** | 15 → **9** |
| `reason-v1` → `v2` | 81 → **86** | 11 → 14 | 7 → **0** | 8 → 7 |

dev 上同向：`answer` 完全正确 108 → 116、换标 17 → 15；`reason` 109 → 114、换标 18 → 10。
**多标几乎被清零**（这是规则直接压的），但 `answer` 的**换标也从 15 降到 9**——
那是真的把领域判对了，不是单靠变保守。代价是漏标上升（8 → 12）。

**新的副作用：从多标偏置翻到了漏标偏置。** dev 上给 2 个标签的条数：
标准答案 29，`answer-v1` 27、`answer-v2` 18、`reason-v1` 35、`reason-v2` 12。
v1 本来已经校准得很好，v2 把它推到了明显偏少的一侧。
Jaccard 涨了是因为「少给一个」比「给错一个」在这个指标下更便宜
（gold 2 个只命中 1 个是 0.5，给 2 个错 1 个是 0.33），
**这是指标的性质，不等于预测更正确**。要报告时必须把这一条和 Jaccard 的涨幅放在一起写。

**一个有实用价值的点**：`zero-shot + reason-v2` 的 0.866 是**完全不用示例**拿到的，
而多任务最优的 0.873 需要 k=3 few-shot。两者相差 +0.007（CI 跨 0），
但 token 成本是 0.32M 对 0.91M，差近三倍。

### Task 2a 收尾状态

| # | 配置 | `answer` 线 | `reason` 线 |
| --- | --- | --- | --- |
| 1 | zero-shot | 0.837 | 0.832 |
| 2–5 | few-shot bm25 k=3/5/10/20 | 0.845 / 0.839 / 0.857 / 0.843 | 0.861 / 0.850 / 0.850 / **0.867** |
| 6–9 | few-shot random k=3/5/10/20 | 0.829 / 0.840 / 0.838 / 0.851 | **0.869** / 0.860 / 0.832 / 0.853 |
| 10 | trace2skill | 0.862 | 0.866 |

20 格全部 143/143 合法预测。dev 使用次数：22（多任务）+ 20（Task 1）+ 20（Task 2a）= **62**。
**Task 2a 花费**：推理 33.3M prompt token（dev 20 格 + train_evolve 2 个 + train_val 4 个），
另有归因 500 次调用（250 条教训 × 2）。
`results/comparison-task2a.md` 里的最优值是**选择后的乐观上界**，不是泛化成绩。
