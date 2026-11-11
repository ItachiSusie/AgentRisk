# Evolve：实现说明

日期：2026-11-11。对应 [spec.md](spec.md)（规格）和 [eval.md](eval.md)（验收）。
代码：`src/evolve.py`；测试：`tests/test_evolve.py`；提议器（proposer，负责提出 prompt 改动的 LLM 调用）的 prompt：`prompts/evolve/proposer_blind_v1.txt`、`prompts/evolve/proposer_edit_v1.txt`。

本文只记录 spec 没写死、实现时必须做的决定，以及和 spec 字面不一致的地方。其余全部按 spec 实现。

## 1. 怎么跑

```bash
make test                      # 80 条离线测试（其中 evolve 37 条），不调 API
make evolve-dry                # 假预测器 + 假提议器，端到端跑一遍 task2b，写到 results/_smoke/evolve/
python src/evolve.py init --task task2b --seed prompts/single/task2b/zero_shot_reason_v1.txt [--limit-per-fold N] [--param name=value]
python src/evolve.py baseline --run-dir <dir> --concurrency 8
python src/evolve.py step     --run-dir <dir> [--rounds N]
python src/evolve.py status   --run-dir <dir>     # 同时写 process_metrics.json（eval.md §4）
python src/evolve.py export   --run-dir <dir> --version reason-v<N>
```

`--limit-per-fold` 和 `--dry-run` 在 `init` 时定下并写进 `config.json`，之后的命令从配置读取，传了不一致的值会直接报错。

## 2. 复用了哪些已有函数

| 需要 | 复用 |
|---|---|
| 请求、解析、参数 | `run.request`、`run.parse`、`run.zero_shot_messages`、`run.PARAMS`、`run.get_client`、`run.RETRYABLE` |
| 输出校验 | `common.unpack_prediction` |
| 单条损失、自助法（bootstrap，有放回重抽样估计区间） | `paired_bootstrap.per_sample`、`paired_bootstrap.bootstrap` |
| 混淆对 | `triage.confusion_pairs`（逐条调用，确保格子的计数口径和 triage 一致） |
| BM25 近邻、引文校验 | `analyst.build_pool`、`analyst.neighbours`、`analyst.quote_in_text` |
| 分层抽样 | `analyst.stratified_sample`（快速闸门的随机那一半） |
| 输出格式锚点 | `assemble_instruction.ANCHORS` |
| 折校验 | `make_folds.build`（启动时重算，与文件不一致就拒绝启动） |

没有改动任何已有文件的行为，也没有把函数挪进 `common.py`：上面这些都能直接 import，不需要搬。

## 3. spec 没写死、由实现决定的地方

1. **轨迹截断。** spec 说按 `analyst.dossier` 的规则截断，但 `analyst.dossier` 实际上不截断。新增参数 `traj_chars=6000`：超长的轨迹只保留末尾 6000 字符（末尾包含 proposed_action），开头标 `[...]`。train_evolve 轨迹长度中位数 3372 字符、90 分位 5621、最长 11974，所以大约一成的样本会被截断。
2. **受保护文本（spec 4.5 第 3 条）。** Task 2a/2b：每个标签名必须仍在 prompt 中，标签列表里「整行只有标签名」的那些行必须逐字保留。Task 1：五个等级名（`1 Minimal:` … `5 Critical:`）必须保留，但**等级后面的定义文字可以改**，否则 `definition` 类改动在 Task 1 上无从下手。输出格式尾部（从第一个 `ANCHORS` 命中处到结尾）必须逐字不变。
3. **抄写检查（spec 4.5 第 5 条）。** 判定为「从批次轨迹抄来」的 4 词序列，要先排除当前 prompt 里本来就有的 4 词序列。否则改写 prompt 自己的句子（如 "the proposed action itself"）也会因为轨迹里碰巧出现同样的词而被拒。
4. **插入位置。** `insert_after` 时，锚点在行尾就另起一行插入，否则用一个空格接在后面。`delete` 删掉一整行时连同换行一起删。
5. **标签噪声的判定由代码执行。** spec 让提议器在多数错例是 `sound_but_wrong`（推理合理、但金标难以从文本得到）时返回空改动。代码再独立判一次：被展示为错例的样本里，`sound_but_wrong` 占比超过 `noise_share=0.5`，这一轮就记为 skipped，不论提议器返回了什么；该格子以后不再作为目标（对应 eval.md §4 最后一行）。skipped 不计入耐心值（patience，连续多少轮没有接受任何改动就停止）。
6. **同类型多个改动。** 提议器对同一 `edit_type` 给了多个改动时，只保留第一个，其余记为 `duplicate edit_type`。
7. **无效预测不作为目标。** `pick_target` 只看有效预测；无效预测在闸门里按最坏损失计（Task 1 记 4，Task 2 记 1），并单独由 G6 检查。
8. **快速集的随机那一半。** 按金标分层：Task 1 按等级，Task 2 按排序后的第一个金标标签。名额少于层数时退化为简单随机抽样（`stratified_sample` 要求每层至少一个名额）。
9. **预算。** 只计输入 token（与 spec §7 的口径一致），每发出 `predictor_batch=64` 条预测前、每次提议器调用前检查一次。超预算时干净退出，状态已落盘，可以续跑。
10. **噪声重复。** 噪声底 τ（同一 prompt 跑两次、预测不同的样本数）用 `replica=1` 作为缓存键的一部分，保证第二遍真的重新请求，而不是命中第一遍的缓存。
11. **安慰剂对照（eval.md §5.2）。** 已实现为参数 `placebo=1`：第二次提议器调用里展示的金标在批次内打乱，闸门仍用真实金标。

## 4. 需要和 Qi 确认的事项（第 4 点已定）

1. **试跑规模。** spec 的试跑用 `--limit-per-fold 10`。每折只有 10 条时，提议折里同一个错误格子很难凑够 `min_wrong=4` 条（Task 2b reason-v1 在 train_evolve 上平均 Jaccard 为 0.735，十条里错三四条，还会分散在多个格子里），试跑很可能每一轮都因为「没有目标格子」被跳过，看不到提议器的输出。建议试跑用 `--limit-per-fold 30`，或者保留 10 但加 `--param min_wrong=2`。两种都是新 run，不影响正式参数。
2. **OOF 估计。** eval.md §3.3 要用 OOF（out-of-fold，样本外：在没参与产生改动的折上算出的分数）收益算迁移比（transfer ratio，dev 收益 ÷ OOF 收益）。`status` 现在报的是「最终冠军 vs 种子」在全部 461 条上的差，但最终冠军的改动是在其中某些折上提出的，这个数**不是**干净的 OOF，已在输出里注明。比较干净的做法是对每个被接受的改动，用它在全闸门（4 个评估折）上的收益，或者按 spec 的思路做真正的交叉拟合。这一点等 Qi 决定用哪个定义后再补。
3. **种子。** 用户在另一个分支上做了一轮「补全官方标签定义」，Task 2b 的 `reason-v4` 在 train_evolve 上是 0.756（reason-v1 是 0.735）。spec 支持 `--seed` 传多个种子、按 train_evolve 分数选冠军。如果要用，`reason-v4` 需要先提交；并且按 eval.md 的写法，主比较对象 B0 仍是 reason-v1，应另报 E vs reason-v4，把定义的贡献和 evolve 的贡献分开。导出版本号见第 4 点。
4. **导出版本号（2026-11-11 已定）：三个任务统一用 `reason-v5`。** spec §6 的示例 `--version reason-v3` 不能照抄：2a/2b 的 `reason-v3`/`reason-v3b` 已被 agentic distill 的 E0 占用，三个任务的 `reason-v4` 已被「v1 + 官方定义」占用。evolve 不改输出格式，所以留在 reason 线上递增；Task 1 没有 `reason-v3`，空着不用，与 2a/2b 统一到 v5。以后若改用 `reason-v4` 作种子再跑，导出为 `reason-v6`，CHANGELOG 写明种子。汇总表中标为「zero-shot (evolve)」，与「zero-shot (trace2skill)」并列；E+R 记为 `few-shot-bm25-k<k>` + `reason-v5`。

## 5. 测试覆盖（spec §8）

`tests/test_evolve.py`，全部用合成数据和假的模型调用：

- 改动校验：锚点缺失或重复、标签被删或改写、标签行被改、输出尾部被改、引文不是原文、引用少于 2 条、引用批次外的样本、长度超限、prompt 增长超限、抄写轨迹、含样本 id、与已试过的 prompt 相同；Task 1 等级名受保护但定义可改。
- 翻转账本（flip ledger，逐条比较冠军与候选的损失）与 G1–G6：包括合成的 Authorization↔Scope 互换（G3 必须拒绝）、标签数漂移、Task 1 等级偏移和金标 1 损失、只在一折上有收益（G5）、无效输出增加（G6）。
- 数据角色：提议器载荷里出现提议折之外的 id 就抛错；批次与提议器载荷只含提议折的 id。
- 续跑：在快速闸门之后「杀掉」进程，重新运行 `step`，同一个（prompt、样本、重复号）没有被请求第二次，提议器输出从磁盘重放。
- 端到端：真实有效的改动被接受、冠军覆盖全部样本、导出文件、拒绝覆盖已有 prompt、拒绝与种子不同谱系的版本号；耐心值停止；标签噪声轮被记为 skipped；预算耗尽干净停止；安慰剂打乱金标；配置记录参数和各文件的 sha256。

## 6. 独立验收（2026-11-11）与处理

由一个独立子代理按 spec.md / eval.md 逐节核对代码，并跑了测试、dry run 和人为中断后的续跑。核心逻辑（折轮换、账本符号、自助法方向、G1–G6、缓存键含重复号、线程安全、续跑幂等、导出冻结）核对无误。发现的问题与处理：

| 编号 | 问题 | 处理 |
|---|---|---|
| B1 | API 连续失败的样本被当成「无效输出」写进缓存，续跑也不重试，会给冠军留下永久的最坏损失 | 已修：全部尝试都是 API 错误的样本不进缓存，本步停止（`ApiUnavailable`），重跑同一命令即重试；有测试 |
| B2 | 盲读输出里出现一个拼错的 id，就会让第二次调用的数据角色断言永远失败 | 已修：第二次调用前剔除批次外的条目、屏蔽零散 id，记到 `blind_sanitized.json`；有测试 |
| B3 | τ 对 Task 2 的标签顺序敏感，会虚增噪声底 | 已修：按集合比较；有测试 |
| D1 | 盲读调用的边界描述写着「金标 A 缺失、预测成 B」，等于泄露了金标方向 | 已修：盲读只看到无序、两侧对称的边界描述；盲读 prompt 措辞同步修改（v1 尚未用于任何正式运行，按冻结规则仍可改）；有测试 |
| D2 | 只记输入 token，eval.md §3.4 还要输出 token | 已修：`state.output_tokens_used`，`status` 一并报告 |
| N1 | 截断或非 JSON 的输出被记成 API 错误 | 已修：记为 `invalid_output`，保留用量 |
| N2 | 候选多样性按整份 prompt 算，两个不同的 11 词插入就超过 20 词门槛 | 已改：按各改动自身（锚点 + 新文本）比较 |
| N3 | 中断时最多丢一批的 token 计数 | 已修：每条预测落盘时同步写 state |
| N4 | 第二次调用输出缺少结构检查；编辑 prompt 没写 12 字符引文下限和 150 词增长上限；CHANGELOG 可被覆盖 | 已修 |

**仍未解决、需要 Qi 决定的：**

1. **G3 的互换规则可能过严（未测量）。** 按 spec 字面，任一标签 FP 减 1 且 FN 加 1、两者之和不降，就拒绝候选，没有幅度门槛；eval.md 的措辞是「by a similar amount」。建议试跑 baseline 后，用种子与它的噪声重复（`s0` vs `s0_repeat1`）这一对看这条规则在纯噪声下会不会误触发，再决定是否加门槛（新参数，新 run）。
2. **OOF 的定义**（见 §4 第 2 点）：要在预登记里写死。
3. **试跑规模**（见 §4 第 1 点）：验收复现了 `--limit-per-fold 10` 下 task2b 和 task1 的 8 轮全部「没有目标格子」。另外每折 10 条时快速集等于全部评估样本，G2 上限 0.03×28 < 1，一次 right→wrong 就会失败。
4. **还没有的工具**：REPORT.md 生成器、预登记文件模板、消融 A4（盲读阶段也给金标）的开关。A3（只给错例）可以用 `--param m_right=0`。
