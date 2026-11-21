import json, os
from pathlib import Path
key=json.loads(Path('/tests/answer_key.json').read_text())
try:
    v=json.loads(Path(key['submission_path']).read_text())
    passed=isinstance(v,dict) and set(v)=={'answer'} and v['answer']==key['answer']
except (OSError,ValueError):
    passed=False
out=Path(os.environ.get('HARBOR_REWARD_PATH','/logs/verifier/reward.json'))
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps({'reward':float(passed)}))
