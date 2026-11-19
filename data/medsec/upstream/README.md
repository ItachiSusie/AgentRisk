# MedAgentBench 官方公开输入

- `test_data_v2.json`：[官方原文件](https://raw.githubusercontent.com/stanfordmlgroup/MedAgentBench/main/data/medagentbench/test_data_v2.json)，SHA-256 `b6e89b2ef82f1bef27c5778a644a8a66c7b25738bbd6a48d03ab3e5182df6ca8`，300 个任务实例。
- `funcs_v1.json`：[官方原文件](https://raw.githubusercontent.com/stanfordmlgroup/MedAgentBench/main/data/medagentbench/funcs_v1.json)，SHA-256 `c977266db5eca75182c0d12cac1962b33ae6b5a54b9029ceb104e1a93b4c38c1`，9 条工具定义。

下载于 2026-11-10。官方 `refsol.py` 需从项目说明指定的 Stanford Box 单独取得，不随这两份公开文件提供。运行器只有拿到 `--grader` 时才尝试计算官方效用；未取得时结果明确为 `null`。
