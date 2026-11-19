"""Conservative migration of saved v08 events; never invent missing provenance."""
import json
from pathlib import Path
from .normalize import normalize
from .schema import digest


def read_saved(run_dir):
    root = Path(run_dir)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('format') != 'medsec-v08':
        raise ValueError('expected v08 run')
    result = {'manifest': manifest, 'review_status': 'needs_review', 'derived_from': str(root.resolve()),
              'missing_contract_fields': ['scenario_group_id', 'attack_family_id', 'authorization_scope_ref', 'trigger_ref', 'evidence_complete']}
    for filename, key in [('events.jsonl', 'events'), ('outcome.json', 'outcome')]:
        raw = (root / filename).read_bytes()
        if digest(raw) != manifest[key + '_sha256']:
            raise ValueError(f'{filename} fingerprint changed')
        result[key] = [json.loads(line) for line in raw.splitlines() if line] if key == 'events' else json.loads(raw)
    result['events'] = normalize(result['events'], manifest.get('source_event_run_id', manifest['run_id']))
    # attack_triggered and attack_presented_to_model remain native claims only.
    return result
