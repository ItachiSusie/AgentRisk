import json, os
from pathlib import Path
key=json.loads(Path('/tests/answer_key.json').read_text())
p=Path(key['submission_path'])
try:
    value=json.loads(p.read_text())
    passed=isinstance(value,dict) and set(value)=={'answer'} and value['answer']==key['answer']
except (OSError,ValueError):
    passed=False
out=Path(os.environ.get('HARBOR_REWARD_PATH','/logs/verifier/reward.json'))
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'reward':float(passed)}))
