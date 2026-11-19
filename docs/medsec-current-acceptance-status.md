# MedSec 双底座实施验收状态

**核对日期：2026-11-19。** 本文按[双底座实施规格](medsec-dual-benchmark-implementation-spec-v0_1.md)的 P0–P5 汇总。原版任务（official task，上游发布的任务与验证环境）和合成扩展（synthetic extension，本项目新增的任务、载荷及验证器）分别列证据；开发候选未通过临床、许可与安全规则审核，不能称为正式发布集。

**后续全量合成开发集更新：** 两轨共 1,260 条不同攻击候选已在 DeepSeek Flash 下完成两种防御条件的试验；Med `v17-med-20261119T073649Z-0175ebf0`、Health `v12-health-20261118T060836Z-b3d3cb98` 和统一复算报告 `v18-joint-20261119T074357Z-5b4d6034` 的结果见[全量实验报告](medsec-full-deepseek-results-2026-11-19.md)。下表保留此前 P0–P5 验收判断；本次合成运行不替代原版 300/75 任务复现、独立审核与隐藏集验收。

| 里程碑 | 已完成的可复验证据 | 尚未满足的验收 |
| --- | --- | --- |
| P0 上游锁定 | v08 锁定上游提交、任务、评分器、镜像与工具定义；Docker 27.1.1 和 Harbor 0.23.0 已用于实际运行。见 [v08 状态](medsec-v08-implementation-status.md)。 | 无新增阻塞。 |
| P1 Med 原版 | 真实 FHIR（Fast Healthcare Interoperability Resources，交换医疗资源的结构化数据标准）查询参考轨迹 `v08-20261117T062334Z-678b843b9abd` 与模拟写入参考轨迹 `v08-20261117T062334Z-6f20f7c46862` 经官方评分为通过。新增 `tests/test_medsec_official_matrix.py` 对十类各一条任务执行可控 FHIR 返回下的正反轨迹，官方评分器逐类判真/假；10 项测试通过。 | 十类回归仅每类一条、使用可控返回；尚未完成原版 300 条在真实 FHIR 服务上的系统性轨迹核对。该 DeepSeek 干净查询样本未通过正常效用。 |
| P2 Health 原版 | 两类官方任务均进入验证器；数据质量参考解奖励为 1.0。v08 的 8 条合成任务有 5 条通过。见 [v08 状态](medsec-v08-implementation-status.md)。 | 两类官方任务的 DeepSeek 奖励均为 0.0；加长预算的数据质量试验超时，未有可判定结果。原版完整复现与正常效用门槛未满足。 |
| P3 两轨攻击 | Med 有真实 FHIR 暴露和合成扩展攻击事件；新配对 `v08-pair-20261119T065755Z-b3932ff9eb6f` 的干净条件均通过，无防御发生错患者写入、scope 条件未发生。Health v08 的工具返回与技能攻击已触发且暴露，但目标未达成。Health v12 的 336 条合成候选在两个防御条件下全部执行，结果见 [v12 报告](medsec-v12-health-memory.md)。 | 合成攻击不能代替上游原版环境的正式攻击结果；Med 原版正常效用条件不足。工具描述篡改、跨智能体消息仍缺独立入口及权限证据。 |
| P4 在线防御、技能、记忆 | v11 Med 直接记忆编辑：12 条预选候选、48 个 DeepSeek 目标运行，报告可复算；v12 Health 来源任务 12/12 完成，目标计划/观测 744/744，容器级技能、工具返回、环境文件、恶意用户和直接记忆编辑有暴露记录。见 [v11](medsec-v11-memory-experiment.md)、[v12](medsec-v12-health-memory.md)。 | 两轨都尚未证明“低信任内容诱导来源智能体写入错误记忆，再污染目标任务”的完整链；直接编辑记忆是不同攻击权限。Harbor 任意 Shell 命令的患者范围授权仍未实现。 |
| P5 扩展数据和审核报告 | v10 有 78 条正常任务、1,068 条攻击候选，来源 `data/medsec/v10_expanded_seed0/manifest.json` 与 `coverage.json`。v11/v12 的运行均可通过 `src/evaluate.py` 离线复算；新增[六类医疗风险标签及分轨评估](medsec-medical-risk-taxonomy-v1.md)，其中三类有合成代理实验。 | 合成任务、载荷、临床规则与许可未独立审核冻结；无合格隐藏测试集。另三类风险缺独立任务与判定。旧 v08 原生日志到 labels-v1 合同的完整证据桥接仍待验收。不能给出正式基准总攻击成功率。 |

## 本次补齐的证据

十类代表性回归使用单独分发的官方 `refsol.py` 和锁定上游循环源码；每类检查一个预期通过轨迹和一个预期失败轨迹。测试不调用模型，也不声称 300 条任务正常完成。命令：

```bash
python -m pytest -q tests/test_medsec_official_matrix.py
python -m pytest -q tests/test_medsec.py tests/test_medsec_v07.py tests/test_medsec_v08.py tests/test_medsec_v10.py tests/test_medsec_v11.py tests/test_medsec_v12.py tests/test_medsec_labels_v1.py tests/test_medsec_official_matrix.py
python src/evaluate.py results/medsec/v11-memory-20261118T054215Z-2ea11c0e
python src/evaluate.py results/medsec/v12-health-20261118T060836Z-b3d3cb98
```

本次 v12 复算确认 `complete=true`、目标试验 744/744、失败来源 0、阻断任务 0。v12 的无防御攻击条件目标达成 51 次，scope 防御攻击条件达成 48 次；两者合计 99 次是不同条件下的运行次数，来自相同的 336 条候选，不是 99 条独立攻击任务。分入口、未知结果及干净基线条件见 `results/medsec/v12-health-20261118T060836Z-b3d3cb98/report.json` 的 `summary`。v11 结果见 `results/medsec/v11-memory-20261118T054215Z-2ea11c0e/report.json` 的 `counts`。

## 下一批实际交付

1. 新版本实现诱导写入记忆：限定来源低信任入口、验证来源模型真实 `write_memory` 及其权限、将来源快照复制给四条件目标任务、确认实际 `search_memory` 和最终目标；不能把脚本写入或直接改库计作此类攻击。
2. 为工具描述篡改和跨智能体消息建立独立安装/呈现事件、可编辑字段及作用域权限，给出干净与攻击配对运行。
3. 对 Med 原版 300 条任务做分类型真实 FHIR 回归；对 Health 两类官方任务排查正常效用失败。任何修正都新建任务/提示版本和运行编号，保留已用版本。
4. 组织临床与数据审核、许可核对和独立隐藏集构建；审核结论只能由相应审核者给出，当前实现不能替代其签核。
