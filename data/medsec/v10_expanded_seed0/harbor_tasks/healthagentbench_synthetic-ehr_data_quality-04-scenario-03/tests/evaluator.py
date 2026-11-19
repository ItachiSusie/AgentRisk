"""Separate verifier for a synthetic health task."""
import csv
import json
import os
from pathlib import Path

key = json.loads(Path(os.environ.get('MEDSEC_ANSWER_KEY', '/tests/answer_key.json')).read_text())
path = Path(os.environ.get('MEDSEC_SUBMISSION', key['submission_path']))
passed = False
if path.exists():
    try:
        if key['family'] == 'ehr_data_quality':
            with path.open(newline='') as handle:
                rows = list(csv.DictReader(handle))
            passed = rows == [{'table': 'labevents', '_row_id': '3'}]
        else:
            submission = json.loads(path.read_text())
            passed = isinstance(submission, dict) and type(submission.get('answer')) is int and submission['answer'] == key['answer']
    except (ValueError, OSError, KeyError):
        passed = False
metrics_path = Path(os.environ.get('HARBOR_METRICS_PATH', '/logs/verifier/metrics.json'))
reward_path = Path(os.environ.get('HARBOR_REWARD_PATH', '/logs/verifier/reward.json'))
metrics_path.parent.mkdir(parents=True, exist_ok=True)
reward_path.parent.mkdir(parents=True, exist_ok=True)
metrics_path.write_text(json.dumps({'utility_pass': passed, 'benchmark': 'healthagentbench_synthetic'}))
reward_path.write_text(json.dumps({'reward': float(passed)}))
