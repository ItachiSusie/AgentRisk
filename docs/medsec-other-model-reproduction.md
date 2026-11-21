# 在另一台机器运行其他模型

本说明用于在 DeepSeek 已完成的实验基础上，使用相同任务、攻击内容和判定规则收集其他模型的结果。攻击成功率（Attack Success Rate, ASR，表示攻击达成目标的比例）和效用（utility，表示正常任务的完成情况）分别统计；不需要重新运行 DeepSeek。

## 1. 同步代码与环境

本次代码位于 `medical` 分支。首次获取：

```bash
git clone --branch medical git@github.com:ItachiSusie/AgentRisk.git
cd AgentRisk
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

已有仓库时，在保存本地修改后执行：

```bash
git switch medical
git pull --ff-only origin medical
```

Med 的合成接口实验不需要医疗服务或容器。Health 实验需要另外安装 Harbor（用于执行隔离任务的容器评测框架）及可访问的 Docker 容器运行环境。当前桥接代码以 Harbor `0.23.0` 为依据；仓库的 `requirements.txt` 尚未包含该依赖。以下安装仅用于需要 Health 的机器：

```bash
.venv/bin/python -m pip install 'harbor==0.23.0'
docker info
```

Python、依赖和容器镜像版本应随新实验保存；依赖安装成功并不等于容器权限已经配置完成。

## 2. 配置其他模型

应用程序编程接口（Application Programming Interface, API，指程序调用模型服务的接口）需要与仓库使用的 OpenAI 客户端兼容；不兼容的原生接口需要另写适配器。模型名称、地址和参数以服务商实际支持的接口为准。

在本机 `.env` 中添加下列变量，不要提交真实密钥：

```dotenv
OTHER_MODEL_API_KEY=replace_locally
OTHER_MODEL_BASE_URL=https://your-provider.example/v1
OTHER_MODEL_NAME=your-model-id
```

从仓库根目录加载：

```bash
set -a
. ./.env
set +a
```

旧实现 `src/medsec/v08/models.py` 固定使用 DeepSeek 的地址、密钥和 `thinking` 参数。仅替换模型名称不能切换服务商。下面通过进程内适配运行 Med，保留已用于 DeepSeek 的代码和提示词不变。

## 3. Med：在固定攻击集上运行其他模型

使用已经入库的 `data/medsec/medbench_v1/`，不要重新执行构建或校准脚本。校准（calibration，指在参考模型上筛选有效攻击的过程）与新模型测试应分开，避免每个模型使用不同攻击集合。

以下命令运行完整的 `none` / `scope` 对照：`none` 表示不启用防御，`scope` 表示患者范围防御。脚本每次创建新的运行编号（run_id，用于唯一标识本次实验）。

```bash
.venv/bin/python - <<'PY'
import json
import os
from pathlib import Path
from openai import OpenAI
from scripts import medsec_bench_run as experiment

class OtherModel:
    def __init__(self, name, *, json_mode=False):
        self.name = name
        self.model_name = name
        self.json_mode = json_mode
        self.last_response = None
        self.client = OpenAI(
            api_key=os.environ['OTHER_MODEL_API_KEY'],
            base_url=os.environ['OTHER_MODEL_BASE_URL'],
            timeout=120,
            max_retries=1,
        )

    def __call__(self, messages):
        options = dict(model=self.name, messages=messages,
                       temperature=0, max_tokens=1800)
        if self.json_mode:
            options['response_format'] = {'type': 'json_object'}
        response = self.client.chat.completions.create(**options)
        self.last_response = dict(
            response_id=response.id,
            model=response.model,
            usage=response.usage.model_dump() if response.usage else None,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError('empty model response')
        return content

name = os.environ['OTHER_MODEL_NAME']
# 先验证模型可访问且支持本实验需要的 JSON 输出。
probe = OtherModel(name, json_mode=True)
reply = probe([{'role': 'user', 'content': 'Return JSON: {"ok": true}'}])
assert isinstance(json.loads(reply), dict), reply

experiment.MODEL = name
experiment.DeepSeekTextModel = OtherModel
experiment.main()
PY
```

JSON（JavaScript Object Notation，一种结构化文本格式）输出、`temperature` 和 `max_tokens` 必须得到服务商支持；上述命令适用于支持这些参数的兼容接口。若服务商要求不同参数，应新建并保存适配脚本及其参数，先检查少量返回，再启动正式实验，不要直接修改已冻结的旧实现。原生接口不兼容的模型不能直接使用上述命令。

输出在 `results/medsec/medbench-*/`，包含 `report.json`、`table.md`、`jobs/` 和逐次交互的 `runs/*/events.jsonl`。运行结束后检查：

- `report.json` 的 `model` 确实是目标模型，并保存对应的完整 `run_id`。
- 各任务记录中的错误状态，以及事件中的 `model_error`、非法动作和未完成情况；不能把调用失败解释为安全抵抗。
- ASR 的成功数与有效分母。当前脚本按各防御下干净任务通过的攻击计算，不能只比较百分比。
- 效用：当前 Med 汇总主要输出 ASR；干净任务的通过结果在 `jobs/`，攻击条件下的效用需要结合事件和任务要求另行汇总。不要把 ASR 的补数当作效用。

## 4. Health：额外的迁移步骤

Health 的任务清单 `data/medsec/v21health_memory/manifest.json` 至 `v24health_memory/manifest.json` 使用了原机器的绝对路径。若新机器仓库路径不同，须将清单里的旧仓库前缀替换成新仓库根目录；仅调整路径，不重新生成攻击或任务。可以在新机器执行：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

root = Path.cwd().resolve()
old_root = '/home/tuo96248/projects/AgentRisk'

def relocate(value):
    if isinstance(value, str) and value.startswith(old_root + '/'):
        return str(root) + value[len(old_root):]
    if isinstance(value, list):
        return [relocate(item) for item in value]
    if isinstance(value, dict):
        return {key: relocate(item) for key, item in value.items()}
    return value

for version in (21, 22, 23, 24):
    path = root / f'data/medsec/v{version}health_memory/manifest.json'
    path.write_text(json.dumps(relocate(json.loads(path.read_text())),
                               ensure_ascii=False, indent=2) + '\n')
PY
```

Health 的入口对应关系如下：

| 入口 | 内容 | 当前模型配置 |
| --- | --- | --- |
| `src.medsec.v21health.experiment` | 原有扩展任务与判断型记忆任务 | 实验入口固定 DeepSeek |
| `src.medsec.v22health.experiment` | 内容危害任务 | 实验入口固定 DeepSeek |
| `src.medsec.v23health.experiment` | 加强技能文件与请求者消息攻击 | 实验入口固定 DeepSeek |
| `src.medsec.v24health.experiment` | 错患者任务 | 支持 `--model`，但底层服务地址仍固定 DeepSeek |

因此，Health 的其他模型实验还需要在新版本入口中接入上节的模型适配器，并把真实模型名称写入任务配置和报告。**上节的进程内替换仅针对 Med，不会自动改变 Health 的桥接代码。** `v24health --model` 也不能单独完成跨服务商切换。不要直接运行旧入口并把输出重命名成其他模型。

内容过滤防御入口 `scripts/medsec_guardrail_pilot.py` 还会额外调用过滤器模型。新增模型实验应分别记录智能体和过滤器的名称、地址及参数，不能只改报告标题。

## 5. 结果保存与论文更新

`results/medsec/` 被 Git 忽略，`git push` / `git pull` 不会搬运实验结果。需要将新运行目录完整归档并传回汇总机器；不仅复制 `report.json`，也保存任务记录、事件和 Health 的冻结证据。现有 Health 索引使用绝对路径，异地复算还需要保留原目录布局或另做证据路径迁移。

每次实验同时保留：

- 完整 `run_id`、代码提交编号（`git rev-parse HEAD`）、目标模型名称与返回的实际模型名称。
- 适配脚本、无密钥配置、采样参数、服务地址、依赖版本和路径调整记录。
- 干净任务效用、攻击条件效用、ASR 成功数与分母、攻击是否到达模型、调用错误或未知数。
- 使用的任务和攻击集合；不同模型使用相同集合，每个模型重新运行自己的干净任务。

Med 与 Health 分开报告。攻击变体共享同一场景时，按 `scenario_group_id` 记录场景组，不把措辞变体当作独立场景。

目前这些最新入口并未全部接入 `src/evaluate.py`，Med 也尚未实现完整的独立复算命令。发布新增论文分数前，需按仓库约定补齐统一复算入口，记录 `run_id`；保留现有 DeepSeek 代码与结果，不用新实现覆盖旧实验。本文给出的是迁移及调用方法，尚未在其他服务商上完成付费端到端验证。
