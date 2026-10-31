# 下一轮方案：从「检索示例」转到「轨迹蒸馏」

更新日期：2026-10-27 · 依据：本地三次 dev 运行 + 新做的 triage（错误分诊）+ arXiv:2603.25158（Trace2Skill）
状态：方案 + 三个可运行脚本已落地，API 实验待跑

## 0. 三句话结论

1. **现在的 few-shot 是「检索式记忆」（retrieval memory）**：把相似样例塞进上下文。它在同分布上不弱（bm25 k=10 → MAE 0.189），但增益来源是示例相似度，不是规则理解——k 从 3→5→10 一路涨，看不到规则层面的收敛。
2. **最大的错误是标签边界，不是缺失知识**：`Scope / Safeguard Failure` 标准答案 27 条，只预测出 13 次，**漏掉 20 条，其中 11 条被错标成 `Authorization / Consent Failure`**。这类错误加多少示例都修不了，只能改判定规则。
3. 因此下一轮不是 k=20，而是：**train 上跑基线 → 逐条错例回到轨迹取证归因 → 合并成一版静态 instruction → train 内部验证 → dev 只测一次**。

## 1. 现状（数字可复算）

三次 dev 运行（`src/triage.py` 生成，见各 run 目录下 `triage/summary.md`）：

| 运行 | MAE | domain J | driver J | 完全正确（三字段全对） |
| --- | --- | --- | --- | --- |
| zero-shot v1 | 0.301 | 0.811 | 0.726 | 70/143（49.0%） |
| few-shot random k=10 | 0.245 | 0.843 | 0.740 | 73/143（51.0%） |
| few-shot bm25 k=10 | **0.189** | **0.862** | **0.793** | **81/143（56.6%）** |

bm25 k=10 的 62 条错例分布（桶 = 互斥分类）：

| 桶 | 条数 | 含义 |
| --- | --- | --- |
| severity_over | 18 | 严重度高估 |
| severity_under | 9 | 严重度低估 |
| driver_wrong | 17 | 严重度对、driver 错 |
| labels_both_wrong | 11 | 两个标签集都错 |
| domain_wrong | 7 | 严重度对、domain 错 |

四条硬事实（都由 triage 直接从预测与标准答案统计）：

1. **严重度 1 和 5 满分**（66/66、2/2），错误全部集中在 2/3/4；`3→4` 仍是最大单格（14 条），`2→1` 次之（4 条）。
2. **`Scope / Safeguard Failure` 是本轮最大系统性错误**：gold 27、预测 13、漏 20、多给 6；`Scope → Authorization / Consent Failure` 单条混淆对出现 11 次。这是定义边界问题（"越权"和"越界/护栏失效"没有区分开）。
3. **拒绝类动作基本不是问题**：启发式标出 52 条「拒绝/澄清」动作，其中 48 条标准答案是 1 级、47 条全字段预测正确；错的只有 5 条——4 条标准答案是 2 级（`AGENTRISK-235/501/614/696`，driver 统一是 `Insufficient Grounding / Uncertainty`）被判成 1 级，另 1 条 `AGENTRISK-282` 是 1 级但标签应为 `Privacy / Confidentiality` + `Authorization / Consent Failure`。所以不能写「拒绝 → 无风险」的一刀切规则：那会 90% 对、10% 全错。
4. **domain 错误很少**（完全一致 113/143），主要多给 `Financial / Assets`（6 条）；优化重点应放在 driver 和严重度锚点上。

## 2. 评测协议（先立规矩，再动手）

| 数据集 | 用途 | 来源 | 状态 |
| --- | --- | --- | --- |
| `train_evolve` 461 条 | 跑轨迹、出错误、做归因 | train 的 238 个 scenario group | 已生成 `data/splits/train_evolve.json` |
| `train_val` 107 条 | 所有 instruction 版本的验证集 | train 的 64 个 scenario group，与 evolve 零重叠 | 已生成 `data/splits/train_val.json` |
| `dev` 143 条 | **最终测试，只跑一次** | 官方 dev | 冻结，只作最后报告 |

规则：

- 切分按 **scenario group（场景组）**，因为同一场景的危险轨迹和安全对照必须同折，否则验证分会虚高。group 字段来自 `metadata/split_manifest.jsonl`（`src/fetch_split_manifest.py` 拉取并校验了 568/143 全覆盖、train 与 dev 组零重叠）。
- 严重度分布已经对齐（evolve/val：1 级 46.6%/46.7%，3 级 22.1%/23.4%，4 级 24.7%/20.6%）。
- 比较用 **paired bootstrap（配对自举）**：同一批样本上 `v_new - v_old` 重采样 1000 次，要求 MAE 改善在 ≥95% 的重采样里成立，且 Jaccard 不下降超过 0.005。
- **最小可分辨差异（minimum detectable difference）**：在 143 条 dev 上做过配对自举，`bm25 k20 − k10 = +0.007，95% CI [−0.028, +0.042]`，即 **MAE 差距小于约 0.03 一律按噪声处理**，不要当结论。
- 一次只改一个主题组，禁止一次上多条规则（否则无法归因）。

## 3. 五个阶段

### Stage 0 冻结与切分（已完成，0 成本）

```bash
.venv/bin/python src/fetch_split_manifest.py     # 拉 metadata/split_manifest.jsonl 并校验覆盖
.venv/bin/python src/make_splits.py --target-val 100   # 场景组级、按严重度分层
```

验收：`data/splits/*.json` 有 461/107 条、`leakage check: False`、val 与 evolve 的组交集为 0。✅

### Stage 1 在 train_evolve 上跑基线（API，约 0.8M prompt tokens）

```bash
set -a; . ./.env; set +a
.venv/bin/python src/run.py --strategy zero-shot --version v1 --split train --limit 5   # 先探
.venv/bin/python src/run.py --strategy zero-shot --version v1 --split train
```

- 用 zero-shot 而不是 few-shot：dev 上 zero-shot 每条 1,751 prompt tokens，461 条约 0.81M；few-shot k=10 约 6.8M，基线不需要。
- `run.py` 对非 dev split 会写到 `results/_smoke/`（不提交），需要的话改成可配置目录。
- 验收：461/461 合法预测 + `src/triage.py` 出 bucket 表 + 错误清单落盘。

### Stage 2 逐条归因（agentic 分析师，1–2 天）

对应论文里的 **agentic error analyst（𝒜⁻，带工具的错误分析师）**。对每条错例，必须完成五步，少一步就不算：

1. 复述标准答案的判定依据（为什么这条是 3 级、为什么是这个 driver）；
2. 用当前 instruction 的字面规则推一遍，看**应该**得到什么；
3. 定位分歧点，归到四类之一：`label_definition`（标签定义）/ `evidence_reading`（轨迹证据读错）/ `severity_anchor`（严重度锚点）/ `output_schema`；
4. 产出一条 lesson + 一条 patch 提案，patch 必须写清「改成什么文本、针对哪类样本、预期修好哪几条 id」；
5. **给不出可验证解释的错例直接丢弃**（论文明确这么做，避免把日志表面症状当根因）。

为什么必须 agentic：论文 §C.1 审计 33 例，一次非交互调用（single-pass，即 `+Error LLM`）把日志里的解析错误当主根因的比例 **57%**，带工具的只有 **14%**，还会编出不存在的失败原因。

产物：`results/analysis/<run_id>/lessons.jsonl`，字段 `example_id / bucket / root_cause_type / evidence_span / lesson / patch_id`。

验收：≥80% 的错例有 `root_cause_type`；每个 patch 至少 3 条不同场景的证据；丢弃率记在报告里。

### Stage 3 合并成 instruction v2（半天）

对应论文的 **merge operator（ℳ，合并算子）**：把 N 条 lesson 去重、解冲突、高频优先、一次性怪例丢弃。

按主题分三组分别出版本，便于消融：

| 版本 | 主题 | 预期修好 |
| --- | --- | --- |
| `zero_shot_v2a.txt` | `Scope / Safeguard Failure` 与 `Authorization / Consent Failure` 的边界 | 20 条漏标，11 条错标 |
| `zero_shot_v2b.txt` | 3 vs 4 的严重度锚点（可逆性、影响范围、是否有护栏） | 14 条 `3→4` |
| `zero_shot_v2c.txt` | 拒绝/澄清类动作的**条件**规则（拒绝但未消除被请求能力 → 2 级 + 具体标签） | 4 条降级误判 + 1 条标签漏给 |

约束：
- 每条新规则必须写成「触发条件 + 判定 + **反例**」三段，只写正向描述会被模型过度泛化；
- instruction 长度上限 +30%，超了必须删旧规则（论文表 1 的教训：人写 skill 让 35B 从 19.00 掉到 9.67，skill 不是免费午餐）；
- `prompts/` 新建文件，不改 v1；`CHANGELOG.md` 记录每条规则来自哪些 lesson。

### Stage 4 验证（API，约 0.8M tokens）

实验矩阵（全部先跑 `train_val` 107 条）：

| 编号 | instruction | 示例 | 目的 |
| --- | --- | --- | --- |
| E0 | v1 | 无 | 已有（dev 上 0.301） |
| E1 | v1 | bm25 k=10 | 已有（dev 上 0.189） |
| E2 | v2a / v2b / v2c 各自 | 无 | 单主题消融 |
| E3 | v2 合并版 | 无 | 规则总效果 |
| E4 | v2 合并版 | bm25 k=10 | 规则 + 示例是否叠加 |

判定：E2 三个版本各自与 E0 配对 bootstrap；只有稳定改进的主题才进合并版；E3 或 E4 胜出后**在 dev 上跑唯一一次**，写进最终报告。

验收：对比表 + bootstrap 置信区间 + 每个版本的 prompt hash、run_id。

### Stage 5 分布外（OOD，可选但评委会问）

现在所有数字都是同分布（in-distribution, ID）。两种做法：

- **A（零成本）**：用 scenario group 做 **group-holdout** 评估——从 dev 里抽出若干完整场景组不用，看模型在没见过的场景上表现如何（弱 OOD）。
- **B（推荐但费时）**：找第二个 agent 风险数据集，人工把标签映射到 10 个 harm domain 的子集，只评 domain/driver。

没有这一节，结论只能写「在同分布上更好」。

## 4. 成本估算（token，不给单价）

| 项 | 估算 |
| --- | --- |
| Stage 1 train 基线（461 条 zero-shot） | ≈0.81M prompt tokens |
| Stage 2 归因（约 200 条错例 × 5 次调用 × 5k tokens） | ≈5M tokens |
| Stage 4 验证（4 个版本 × 107 条 + 重跑） | ≈0.8M tokens |
| 合计 | ≈7M tokens |

## 5. 风险与反制（都来自论文的坑）

| 风险 | 论文证据 | 我们的反制 |
| --- | --- | --- |
| 验证集太小，选择增益是噪声 | 论文用 32 条验证集做 patch 选择（附录 E），作者自己承认不够 | 107 条 + 配对 bootstrap |
| skill/instruction 越写越有害 | 人写 xlsx skill 让 35B 从 19.00 掉到 9.67 | 每条规则必须回测；长度上限 +30%；允许删规则 |
| 只读日志的归因不可靠 | 单趟把表面症状当根因 57% vs 14% | Stage 2 强制回轨迹取证 + 证据片段 |
| 贪心挑「最好的几条」反而更差 | 论文 §4.3：patch 价值是组合性的，贪心平台化 | 全量合并一个版本，不挑单条 |
| 在 dev 上调参 | — | dev 冻结，只在最后跑一次 |

## 6. 本轮已交付

| 文件 | 作用 |
| --- | --- |
| `src/triage.py` | 离线错误分诊：桶分类、严重度混淆矩阵、标签漏/多统计、混淆对、拒绝类子集；不调 API |
| `src/fetch_split_manifest.py` | 按 MANIFEST 钉住的 revision 拉场景组元数据并校验覆盖 |
| `src/make_splits.py` | 场景组级、按严重度分层的 train→evolve/val 切分，带泄漏检查 |
| `data/splits/train_evolve.json` / `train_val.json` | 461 / 107 条，零组重叠 |
| `results/.../<run_id>/triage/summary.md` | 三次 dev 运行的分诊报告（真实输出） |

## 7. 今天就能做的三件事

1. 把 `results/few-shot-error-analysis.md` 的结论换成 triage 的口径（它现在没有「完全正确率」和「拒绝类 52 条里 47 条本来就对」这两个事实）。
2. 跑 Stage 1 的 5 条试探，确认 `--split train` 的落盘目录和断点续跑没问题。
3. 开 `prompts/zero_shot_v2a.txt`，只写 `Scope / Safeguard Failure` 与 `Authorization / Consent Failure` 的区分，用 107 条 val 回测，再决定 v2b/v2c 要不要做。
