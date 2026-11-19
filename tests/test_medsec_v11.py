"""Memory expansion contracts and offline paired experiment replay."""
import json
import re
from pathlib import Path

import pytest
from src.medsec.v11.memory_suite import validate, TOPICS, STRATEGIES
from src.medsec.v11.experiment import run, recompute

SUITE=Path(__file__).resolve().parents[1]/'data/medsec/v11_memory_expanded'


def test_memory_scope_and_distinct_targets():
    result=validate(SUITE)
    m=json.loads((SUITE/'manifest.json').read_text())
    assert result['attack_count']==len(TOPICS)*3*len(STRATEGIES)
    assert result['task_count']==len(TOPICS)*3*2
    assert len({a['clinical_context'] for a in m['attacks']})==len(TOPICS)
    assert all(a['variant'] in (1,2,3) for a in m['attacks'])


def test_offline_four_conditions_replay(tmp_path,monkeypatch):
    from src.medsec.v08 import cli
    class MemoryEchoModel:
        def __init__(self,*args,**kwargs):
            self.turn=0
        def __call__(self,messages):
            self.turn+=1
            if self.turn==1:
                text=messages[1]['content']
                patient=re.search(r'patient (\S+),',text).group(1)
                project=re.search(r'project (\S+) and',text).group(1)
                return json.dumps({'tool':'search_memory','args':{'patient_id':patient,'project_id':project}})
            rows=json.loads(messages[-1]['content'].removeprefix('Tool result: '))
            return json.dumps({'tool':'finish','args':{'answer':rows[0]['text'].strip()}})
    monkeypatch.setattr(cli,'DeepSeekTextModel',MemoryEchoModel)
    result=run(SUITE,tmp_path,model='offline-test-double',limit=1,workers=1)
    assert result['counts']['clean_none']['utility']==1
    assert result['counts']['attack_none']['success']==1
    assert result['counts']['attack_scope']['success']==1
    assert result['counts']['attack_none']['exposed']==1
    root=tmp_path/result['run_id']
    assert recompute(root)==result
    index=root/'index.json'
    index.write_text('{}')
    with pytest.raises(ValueError,match='index changed'):
        recompute(root)


def test_explicit_contract_version_has_no_target_answer_in_instruction():
    root=SUITE.parent/'v11_memory_contract_v2'
    validate(root)
    m=json.loads((root/'manifest.json').read_text())
    assert m['tool_contract_version']=='v2'
    for row in m['tasks']:
        if row['role']!='target':
            continue
        task=json.loads((root/row['task_ref']).read_text())
        assert 'patient_id' in task['instruction'] and 'project_id' in task['instruction']
        assert task['required_outcome']['args']['answer'] not in task['instruction']
