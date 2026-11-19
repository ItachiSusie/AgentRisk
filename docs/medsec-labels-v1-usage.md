# 标签与评分模块使用说明

实现入口为 `src/medsec/labels_v1/`。适用两条合成扩展轨；不需要模型接口或密钥，全部基于保存证据复算。规则库（rule base，由固定判定函数、证据要求和版本组成的集合）在 `data/medsec/labels_v1/rule_registry.json`。该库尚未经过人工审核，正式发布标志始终关闭。

## 输入及命令

准备受控 `bundle.json`，包含 `cases` 数组、`split_manifest` 数组、冻结的 `similarity_threshold`。每个 case 包含 `task`、`attack`（干净条件为 null）、`run`、`events`、`outcome`、`controls`。完整必填字段见实施规格第 2 节及 `schema.py`；可运行的最小结构见 `tests/test_medsec_labels_v1.py` 的 `case()`。该测试使用无临床含义的占位值。

`controls` 是独立受控引用表：任务授权引用指向 `patient_ids`；任务结果引用包含 `verifier_sha256` 和参考 `answer`，Health 奖励判定还需 `pass_threshold`；攻击编辑引用包含 `within_allowlist` 与 `trusted_inputs_unchanged` 的审计结果；触发引用包含 `kind`、`object_ref`、受控 `exposure_span`；攻击目标引用包含目标参数。`threat_mapping` 将以竖线连接的 `surface|injection_point|source_trust` 映射为威胁模型。不得让被测智能体写入这些审计结果。

事件必须保留真实 `run_id`、递增 `seq` 与 `kind`。可核验读取使用 `file_read`、`skill_body_read`、`memory_retrieved`、`tool_call_executed` 或 `user_message_received`，同时记录 `attack_id` 和 `object_ref`。实际模型请求使用 `model_request.messages`；提交写入需 `state_write_executed.committed=true`；实际交付答复/工件使用 `delivered`。旧日志缺少这些证据时不得补造。`run.evidence_complete=true` 必须有采集器完整性审计依据，不能因进程正常退出就设置。

`events_sha256` 与 `outcome_sha256` 使用 `schema.digest()` 的规范化 JSON 指纹。整个 bundle 和评分代码的字节指纹由冻结命令生成。指纹只能证明冻结后未变，不能证明采集内容真实；采集来源与人工审核仍需独立治理。

```bash
PYTHONPATH=src python -m medsec.labels_v1.pack /controlled/bundle.json results/medsec/labels-v1/NEW_RUN_ID --run-id NEW_RUN_ID
python src/evaluate.py results/medsec/labels-v1/NEW_RUN_ID
python -m pytest tests/test_medsec_labels_v1.py tests/test_medsec_v08.py -q
```

冻结命令要求新目录，复算写入 `labels_v1/` 下的五个输出文件。同样输入可重复复算；已存在但内容不同的报告会拒绝覆盖。代码或规则有变更时应保留旧版本并创建新运行。输出包含每项指标的分子、分母、未知及无效计数和运行编号。两底座分别分组；不完整四条件配对单列。按场景组重采样的不确定性区间使用固定种子，场景组不足时返回空区间。

## 旧日志与发布

`import_v08.read_saved(path)` 校验 v0.8 事件和结果文件指纹，保留原始事件语义，输出 `needs_review` 和缺失字段清单。它是迁移辅助读取器；需要审核者补充场景分组、受控引用和完整性证据后才能形成新合同输入。不得把旧 `attack_presented_to_model` 改成实际模型请求，或把旧文件写入触发改成文件读取。

发布审计检查场景、模板、生成器、快照、记忆链与攻击家族交叉，以及隐藏集合是否曾公开、答案是否进入工作区和近似重复。近似重复目前使用标准库字符串相似性，候选重复一律阻止发布，需人工处理后重新冻结；不能据此声称语义层面的独立性已获证明。

当前 `split_manifest.json` 为空且未冻结，`review_log.jsonl` 等待真实审核决定。实施规格 L0—L4 的计算模块已落地；L5 临床、许可和数据集审核以及隐藏测试托管仍待落实。尚未将现有候选数据升级为正式测试，也没有产生新的模型实验分数。

## 验证范围

回归测试文件为 `tests/test_medsec_labels_v1.py`、`tests/test_medsec_v08.py` 与 `tests/test_medsec_v07.py`。检查包括：安装/呈现声明不算读取、实际请求片段、执行与提交区别、越权读取、目标答案冲突、披露交付位置、Health 奖励阈值、四条件配对、指纹篡改、重复复算与拒绝覆盖、数据跨集合交集、场景组区间。测试结果用于软件验收，不是模型攻击成功率；本次未调用模型接口。

规则冲突通过冻结的单一目标映射避免：未知目标输出未知，每种目标只选一个判定函数，不接收外部标签或任意规则表达式。规则表为上述函数的版本化注册信息，修改表或实现均要求新的冻结目录。旧日志迁移辅助读取器尚不自动推断权限、患者图、模板或记忆来源；这些内容不能由运行答案可靠恢复，必须由数据来源补齐并审核。
