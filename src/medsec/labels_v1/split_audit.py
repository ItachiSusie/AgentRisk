"""Conservative release audit. Missing reviews prevent release."""
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

GROUP_KEYS = ('scenario_group_id', 'patient_graph_sha256', 'snapshot_sha256', 'template_family_id',
              'generator_family_id', 'shared_document_sha256', 'skill_sha256', 'memory_chain_id', 'attack_family_id')


def audit(rows, threshold=None):
    errors, candidates = [], []
    index = {key: defaultdict(set) for key in GROUP_KEYS}
    for row in rows:
        for key in GROUP_KEYS:
            if row.get(key):
                index[key][row[key]].add(row['split'])
        if row.get('split') == 'hidden_test' and (row.get('previously_public') is not False or row.get('review_status') != 'approved'):
            errors.append({'reason': 'UNREVIEWED_OR_PUBLIC_HIDDEN_TEST', 'task_id': row.get('task_id')})
        if row.get('answer_key_in_workspace') is not False:
            errors.append({'reason': 'ANSWER_KEY_ISOLATION_UNCONFIRMED', 'task_id': row.get('task_id')})
        if any(row.get(key) != 'approved' for key in ('license_review', 'clinical_review', 'review_status')):
            errors.append({'reason': 'MISSING_RELEASE_REVIEW', 'task_id': row.get('task_id')})
        if any(not row.get(key) for key in ('scenario_group_id', 'template_family_id', 'generator_family_id', 'snapshot_sha256')):
            errors.append({'reason': 'MISSING_GROUP_PROVENANCE', 'task_id': row.get('task_id')})
    for key, values in index.items():
        for value, splits in values.items():
            if len(splits) > 1:
                errors.append({'reason': 'CROSS_SPLIT_OVERLAP', 'key': key, 'value': value, 'splits': sorted(splits)})
    if threshold is None or not 0 < threshold <= 1:
        errors.append({'reason': 'SIMILARITY_THRESHOLD_NOT_FROZEN'})
    else:
        for a, b in combinations(rows, 2):
            if a['split'] != b['split']:
                if not a.get('similarity_text') or not b.get('similarity_text'):
                    errors.append({'reason': 'MISSING_SIMILARITY_INPUT', 'task_ids': [a.get('task_id'), b.get('task_id')]})
                    continue
                ratio = SequenceMatcher(None, a['similarity_text'], b['similarity_text']).ratio()
                if ratio >= threshold:
                    candidates.append({'task_ids': [a.get('task_id'), b.get('task_id')], 'similarity': ratio})
    coverage = defaultdict(int)
    for row in rows:
        key = '|'.join(str(row.get(k, 'unknown')) for k in ('benchmark_id', 'task_family', 'surface', 'goal_id'))
        coverage[key] += 1
    return {'coverage_counts': dict(coverage), 'release_allowed': not errors and not candidates and bool(rows), 'errors': errors,
            'near_duplicate_candidates': candidates, 'threshold': threshold,
            'algorithm': 'difflib.SequenceMatcher-v1', 'row_count': len(rows)}
