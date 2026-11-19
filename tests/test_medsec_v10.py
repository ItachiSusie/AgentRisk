"""Expanded suite content, permission, pairing and native exposure tests."""
import copy
import json
from pathlib import Path

import pytest

from src.medsec.v10.synthesis import validate, plan
from src.medsec.v08.attack import Injector, load_attack
from src.medsec.v08.contracts import Events
from src.medsec.v08.episode import run_extension
from src.medsec.v08.capabilities import MemoryStore

SUITE = Path(__file__).resolve().parents[1] / 'data/medsec/v10_expanded_seed0'


def manifest():
    return json.loads((SUITE / 'manifest.json').read_text())


def test_whole_suite_and_grouping():
    summary = validate(SUITE)
    assert set(summary['surfaces']) == {'malicious_user', 'fhir_response', 'tool_result', 'skill_file', 'environment_file', 'memory_store_edit'}
    assert all(v > 0 for v in summary['surfaces'].values())
    assert summary['attack_count'] == len(manifest()['attacks'])
    groups = {}
    for task in manifest()['tasks']:
        groups.setdefault(task['scenario_group_id'], set()).add(task['split'])
    assert all(splits == {'development'} for splits in groups.values())


@pytest.mark.parametrize('surface', ['malicious_user', 'fhir_response', 'tool_result', 'skill_file', 'environment_file', 'memory_store_edit'])
def test_each_surface_permissions_trigger_and_plan(surface, tmp_path):
    m = manifest()
    row = next(a for a in m['attacks'] if a['surface'] == surface)
    sample, payload = load_attack(SUITE / row['attack_ref'], SUITE, Events('check', 'synthetic', row['task_id']))
    wrong = {k: 'nonmatching' for k in sample['trigger']}
    injector = Injector(sample, payload, Events('check', 'synthetic', row['task_id']))
    # Empty triggers (Health user/env) are installation-time surfaces, not target-filtered reads.
    if wrong:
        assert injector.apply(surface, wrong, 'original') == ('original', None)
    shown, aid = injector.apply(surface, sample['trigger'], 'original')
    assert shown == payload and aid == sample['attack_id']
    assert injector.apply(surface, sample['trigger'], 'original') == ('original', None)
    result = plan(SUITE, sample['attack_id'], memory_root=tmp_path / 'memory')
    assert result['kind'] in {'med_extension', 'harbor'}
    if surface == 'memory_store_edit':
        assert result['seed_argv']


@pytest.mark.parametrize('surface', ['malicious_user', 'fhir_response', 'tool_result', 'skill_file', 'memory_store_edit'])
def test_med_native_exposure_not_model_attack_success(surface, tmp_path):
    m = manifest()
    task_rows = {r['task_id']: r for r in m['tasks'] if r['benchmark_id'] == 'medagentbench_ext'}
    row = next(r for r in m['attacks'] if r['surface'] == surface and r['task_id'] in task_rows)
    task = json.loads((SUITE / task_rows[row['task_id']]['task_ref']).read_text())
    attack, payload = load_attack(SUITE / row['attack_ref'], SUITE, Events('preflight', 'synthetic', task['task_id']))
    memory = tmp_path / 'memory'
    if surface == 'memory_store_edit':
        scope = task['memory_scope']
        MemoryStore(memory, Events('source', 'medagentbench_ext', 'source')).write(
            patient_id=scope['patient_id'], project_id=scope['project_id'], text='Review next visit.',
            source_episode='source', source_ref='synthetic-source')
        actions = [{'tool': 'search_memory', 'args': scope}]
    else:
        actions = [{'tool': 'read_record', 'args': {'patient_id': task['patient_id']}},
                   {'tool': 'load_skill', 'args': {'skill_id': 'workflow'}}]
    actions.append({'tool': 'finish', 'args': {'answer': 'test complete'}})
    iterator = iter(actions)
    result = run_extension(task, lambda messages: json.dumps(next(iterator)), 'exposure-check',
                           workspace=tmp_path / 'work', memory_root=memory, attack=attack, payload=payload)
    events = result['events']
    exposed = [e for e in events if e['kind'] == 'attack_presented_to_model']
    assert exposed
    assert any(e['kind'] == 'model_request' and any(payload.strip() in message.get('content', '') for message in e['messages'])
               for e in events if e['seq'] > exposed[0]['seq'])


def test_every_med_clean_contract(tmp_path):
    for index, row in enumerate(manifest()['tasks']):
        if row['benchmark_id'] != 'medagentbench_ext':
            continue
        task = json.loads((SUITE / row['task_ref']).read_text())
        actions = [{'tool': 'read_record', 'args': {'patient_id': task['patient_id']}},
                   {'tool': 'load_skill', 'args': {'skill_id': 'workflow'}}]
        memory_root = tmp_path / f'memory-{index}'
        if task['family'] == 'memory_handoff_target':
            scope = task['memory_scope']
            MemoryStore(memory_root, Events('source', 'medagentbench_ext', 'source')).write(
                **scope, text=task['required_outcome']['args']['answer'], source_episode='source', source_ref='chart-note')
            actions.append({'tool': 'search_memory', 'args': scope})
        actions.append(task['required_outcome'])
        if actions[-1]['tool'] != 'finish':
            actions.append({'tool': 'finish', 'args': {'answer': 'done'}})
        iterator = iter(actions)
        result = run_extension(task, lambda messages: json.dumps(next(iterator)), f'clean-{index}',
                               workspace=tmp_path / f'workspace-{index}', memory_root=memory_root)
        assert result['synthetic_utility_pass'], row['task_id']


def test_every_health_local_verifier_positive_and_negative(tmp_path):
    import csv
    import os
    import subprocess
    import sys
    for index, row in enumerate(manifest()['tasks']):
        if row['benchmark_id'] != 'healthagentbench_synthetic':
            continue
        root = SUITE / row['harbor_ref']
        folder = tmp_path / str(index)
        folder.mkdir()
        key = json.loads((root / 'tests/answer_key.json').read_text())
        submission = folder / 'submission'
        if key['family'] == 'ehr_compositional_qa':
            chart = json.loads((root / 'environment/workspace/data/chart.json').read_text())
            correct = json.dumps({'answer': chart['lab_value']})
            wrong = json.dumps({'answer': chart['lab_value'] + 1})
        else:
            with (root / 'environment/workspace/data/audit.csv').open() as handle:
                rows = list(csv.DictReader(handle))
            flagged = [r for r in rows if r['value'] == '9999']
            correct = 'table,_row_id\n' + ''.join(f"{r['table']},{r['_row_id']}\n" for r in flagged)
            wrong = 'table,_row_id\nlabevents,999999\n'
        env = {**os.environ, 'MEDSEC_ANSWER_KEY': str(root / 'tests/answer_key.json'),
               'MEDSEC_SUBMISSION': str(submission), 'HARBOR_METRICS_PATH': str(folder / 'metrics.json'),
               'HARBOR_REWARD_PATH': str(folder / 'reward.json')}
        for body, expected in [(correct, 1.), (wrong, 0.)]:
            submission.write_text(body)
            subprocess.run([sys.executable, str(root / 'tests/evaluator.py')], env=env, check=True)
            assert json.loads((folder / 'reward.json').read_text())['reward'] == expected, row['task_id']
