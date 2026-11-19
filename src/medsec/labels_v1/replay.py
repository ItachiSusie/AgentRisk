"""Offline scoring of a frozen bundle. Never edits source evidence."""
import argparse
import json
from pathlib import Path

from . import VERSION
from .schema import digest, validate
from .normalize import normalize
from .static_rules import evaluate as static
from .outcome_rules import evaluate as dynamic
from .aggregate import aggregate
from .split_audit import audit

PACKAGE = Path(__file__).parent
ROOT = PACKAGE.parents[2]


def implementation_hashes():
    return {p.name: digest(p.read_bytes()) for p in sorted(PACKAGE.glob('*.py'))}


def score_case(case):
    task, attack, run = case['task'], case.get('attack'), case['run']
    validate('task', task)
    validate('run', run)
    if attack:
        validate('attack', attack)
        if attack['task_id'] != task['task_id']:
            raise ValueError('attack/task mismatch')
    if run['task_id'] != task['task_id'] or run['benchmark_id'] != task['benchmark_id'] or run['snapshot_sha256'] != task['snapshot_sha256']:
        raise ValueError('run/task mismatch')
    if bool(attack) != run['condition'].startswith('attack'):
        raise ValueError('condition/attack mismatch')
    if (run['defense_id'] == 'none') != run['condition'].endswith('none'):
        raise ValueError('condition/defense mismatch')
    if digest(case['events']) != run['events_sha256'] or digest(case['outcome']) != run['outcome_sha256']:
        raise ValueError('event or outcome fingerprint changed')
    events = normalize(case['events'], run['run_id'])
    controls = case['controls']
    labels = static(task, attack, run, controls) + dynamic(task, attack, run, events, controls, case['outcome'])
    return {**{k: run[k] for k in ('run_id', 'task_id', 'benchmark_id', 'condition', 'pair_id', 'snapshot_sha256', 'model_version', 'agent_version', 'defense_id')},
            **{k: task[k] for k in ('split', 'task_family', 'scenario_group_id', 'review_status')},
            **{k: attack[k] if attack else 'not_applicable' for k in ('surface', 'goal_id', 'threat_model')},
            'attack_id': attack['attack_id'] if attack else None, 'rule_version': '1.0.0', 'labels': labels}


def recompute(run_dir, output_dir=None):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text())
    if manifest.get('format') != VERSION:
        raise ValueError('unsupported label bundle format')
    if manifest.get('code_sha256') != implementation_hashes():
        raise ValueError('scoring implementation fingerprint changed')
    registry_path = ROOT / 'data/medsec/labels_v1/rule_registry.json'
    if manifest.get('rule_registry_sha256') != digest(registry_path.read_bytes()):
        raise ValueError('rule registry fingerprint changed')
    bundle_path = run_dir / 'bundle.json'
    if manifest.get('bundle_sha256') != digest(bundle_path.read_bytes()):
        raise ValueError('bundle fingerprint changed')
    registry = json.loads(registry_path.read_text())
    bundle = json.loads(bundle_path.read_text())
    rows = [score_case(c) for c in bundle['cases']]
    if len({r['run_id'] for r in rows}) != len(rows):
        raise ValueError('duplicate run_id')
    report = aggregate(rows)
    report.update(format=VERSION, run_id=manifest['run_id'], code_sha256=manifest['code_sha256'], rule_registry_sha256=manifest['rule_registry_sha256'])
    report['split_audit'] = audit(bundle.get('split_manifest', []), bundle.get('similarity_threshold'))
    registry = json.loads(registry_path.read_text())
    split_rows = {r.get('task_id'): r for r in bundle.get('split_manifest', [])}
    covered = all(c['task']['task_id'] in split_rows and all(
        split_rows[c['task']['task_id']].get(k) == c['task'].get(k)
        for k in ('split', 'scenario_group_id', 'snapshot_sha256')) for c in bundle['cases'])
    report['formal_report_allowed'] = (covered and bool(rows) and report['split_audit']['release_allowed']
        and registry.get('status') == 'approved'
        and all(rule.get('review_status') == 'approved' for rule in registry['rules'])
        and all(r['review_status'] == 'approved' for r in rows)
        and all(c.get('attack', {}).get('review_status') == 'approved' for c in bundle['cases'] if c.get('attack')))
    dest = Path(output_dir) if output_dir else run_dir / 'labels_v1'
    # Existing reports may be verified, but never overwritten with changed output.
    outputs = {'report.json': report, 'split_audit.json': report['split_audit']}
    jsonl = {'run_labels.jsonl': rows, 'case_labels.jsonl': [{'run_id': r['run_id'], 'labels': r['labels'][:2] if r['condition'].startswith('attack') else r['labels'][:1]} for r in rows],
             'pair_metrics.jsonl': report['pairs']}
    rendered = {name: json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n' for name, value in outputs.items()}
    rendered.update({name: ''.join(json.dumps(x, ensure_ascii=False, sort_keys=True) + '\n' for x in value) for name, value in jsonl.items()})
    for name, body in rendered.items():
        p = dest / name
        if p.exists() and p.read_text() != body:
            raise ValueError(f'refusing to overwrite changed report: {p}')
    dest.mkdir(parents=True, exist_ok=True)
    for name, body in rendered.items():
        if not (dest / name).exists():
            with (dest / name).open('x') as stream:
                stream.write(body)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir')
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    print(json.dumps(recompute(args.run_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
