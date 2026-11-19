"""Lossless event adapter. Injector claims never become read/exposure evidence."""


def normalize(events, run_id):
    result = []
    previous = 0
    for event in events:
        seq = event.get('seq')
        if not isinstance(seq, int) or seq <= previous or event.get('run_id') != run_id:
            raise ValueError('invalid event identity or order')
        if not event.get('kind'):
            raise ValueError('missing event kind')
        previous = seq
        result.append({**event, 'source_ref': event.get('source_ref', f'events.jsonl#{seq}'),
                       'native_kind': event['kind']})
    return result
