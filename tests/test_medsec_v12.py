"""Health memory container task contracts and scope isolation."""
import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.medsec.v12.experiment import catalog,prepare_case
from src.medsec.v08.contracts import tree_hash,Events
from src.medsec.v08.attack import load_attack
from src.medsec.v08.capabilities import MemoryStore

ROOT=Path(__file__).resolve().parents[1]


def test_all_health_memory_source_target_and_payloads():
    root=ROOT/'data/medsec/v12_health_memory'
    m=json.loads((root/'manifest.json').read_text())
    assert len(m['tasks'])==24 and len(m['attacks'])==48
    tasks={t['task_id']:t for t in m['tasks']}
    for task in m['tasks']:
        assert tree_hash(Path(task['path']))==task['tree_sha256']
        assert not (Path(task['path'])/'environment/workspace/tests').exists()
    for attack in m['attacks']:
        sample,payload=load_attack(Path(attack['attack_ref']),root,Events('check','healthagentbench_synthetic',attack['task_id']))
        source=tasks[attack['source_task_id']]
        target=tasks[attack['task_id']]
        assert source['patient_id']==target['patient_id']
        assert source['project_id']==target['project_id']
        assert sample['trigger']==dict(patient_id=target['patient_id'],project_id=target['project_id'],version=1)
        assert payload.strip()!=target['expected_answer']
        assert target['expected_answer'] not in (Path(target['path'])/'instruction.md').read_text()


def test_expanded_health_catalog_and_condition_profiles(tmp_path):
    tasks,attacks=catalog()
    assert len(attacks)==336
    assert len([t for t in tasks.values() if t.get('role')=='target'])==12
    attack=next(a for a in attacks if a['surface']=='memory_store_edit')
    task=tasks[attack['task_id']]
    clean=prepare_case(tmp_path,task,'clean_none',seed=tmp_path/'seed')
    poisoned=prepare_case(tmp_path,task,'attack_none',attack,seed=tmp_path/'seed')
    assert clean['profile']['memory_seed']==poisoned['profile']['memory_seed']
    assert clean['profile']['attack_path'] is None
    assert (Path(clean['path'])/'instruction.md').read_text()==(Path(poisoned['path'])/'instruction.md').read_text()


def test_bridge_copies_seed_and_blocks_cross_project(tmp_path,monkeypatch):
    from src.medsec.v12 import harbor_agent as bridge
    tasks,attacks=catalog()
    attack=next(a for a in attacks if a['surface']=='memory_store_edit')
    task=tasks[attack['task_id']]
    seed=tmp_path/'seed'
    store=MemoryStore(seed,Events('source','healthagentbench_synthetic','source'))
    store.write(patient_id=task['patient_id'],project_id=task['project_id'],text=task['expected_answer'],source_episode='source',source_ref='test')
    seed_before=tree_hash(seed)
    prepared=prepare_case(tmp_path,task,'attack_none',attack,seed)
    logs=tmp_path/'trial/agent'
    logs.mkdir(parents=True)
    (logs.parent/'config.json').write_text(json.dumps({'task':{'path':prepared['path']}}))
    actions=iter([dict(tool='search_memory',patient_id=task['patient_id'],project_id='wrong-project'),
                  dict(tool='search_memory',patient_id=task['patient_id'],project_id=task['project_id']),
                  dict(tool='finish',answer='done')])
    monkeypatch.setattr(bridge,'DeepSeekTextModel',lambda *a,**k:lambda messages:json.dumps(next(actions)))
    class Environment:
        async def exec(self,*args,**kwargs):
            return SimpleNamespace(return_code=1,stdout='',stderr='')
    agent=bridge.MedSecHarborAgent(logs_dir=logs,model_name='test-double')
    asyncio.run(agent.run((Path(prepared['path'])/'instruction.md').read_text(),Environment(),None))
    events=[json.loads(line) for line in (logs/'medsec-events.jsonl').read_text().splitlines()]
    assert any(e['kind']=='action_blocked' for e in events)
    assert any(e['kind']=='memory_retrieved' for e in events)
    assert any(e['kind']=='model_exposure_verified' for e in events)
    assert tree_hash(seed)==seed_before
