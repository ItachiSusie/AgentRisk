# 20261104-dev-smoke-03 本地环境

- 病历服务使用官方容器镜像中的 Java 服务、配置与数据库文件，在本机 Java 17 中启动，地址为 `127.0.0.1:18080`。镜像摘要为 `sha256:3fb83d7ed71c5476f9eb6212bd440a909ef7505922bbc757dc488a8fc0701966`。[官方安装说明](https://github.com/stanfordmlgroup/MedAgentBench#quick-start)
- 服务、数据库、输入和官方评分脚本暂存于 `/tmp/agentrisk-medpilot` 及 `/tmp/agentrisk-mab-v2.json`。任务文件和评分脚本的内容指纹见 `metrics.json`。病历号查询使用本地服务的真实返回，写入仅生成载荷并模拟确认。
- 本地模型运行器为 llama.cpp b12119。执行模型及第一评审为 Qwen2.5-3B-Instruct，第二评审为 SmolLM3-3B。两者使用 Q4_K_M 量化（以较低精度储存权重），各自监听本机 18081、18082 端口，分别评审，互不接收对方结果。Qwen 同时是执行模型，因此两份评审不能当作独立于执行模型的验证。
- Qwen 权重 SHA-256 为 `626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d`。SmolLM3 权重 SHA-256 为 `519732558d5fa7420ab058e1b776dcfe73da78013c2fe59c7ca43c325ef89132`。
- 试点采用两个任务专用的匿名动作适配器。工具参数中的患者、测量值和时间使用别名，在本地映射回原任务参数。官方参考评分器评的是映射后的结果，执行模型用的是本试点的动作格式和提示词。源数据未送入外部模型服务。
- 第一次运行 `20261104-dev-smoke-01` 的外部服务在任何轨迹生成前返回 401。后续运行全部在本机。

复跑时使用新的输出目录。以下命令假设本地病历与两个模型服务已启动。

```bash
python3 -B src/run_medagentbench_pilot.py \
  --tasks /tmp/agentrisk-mab-v2.json \
  --grader /tmp/agentrisk-medpilot/grader.py \
  --output results/medagentbench-pilot/<new-run-id>
```
