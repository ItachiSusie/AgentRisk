"""Freeze a reviewed input bundle into a new directory; does not execute agents."""
import argparse
import json
from pathlib import Path
from .schema import digest
from .replay import ROOT, implementation_hashes, score_case


def pack(bundle_path, output_dir, run_id):
    raw = Path(bundle_path).read_bytes()
    bundle = json.loads(raw)
    for case in bundle['cases']:
        score_case(case)  # Caller must supply event/outcome hashes; never repair them silently.
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'bundle.json').write_bytes(raw)
    manifest = {'format': 'medsec-labels-v1', 'run_id': run_id, 'bundle_sha256': digest(raw),
                'code_sha256': implementation_hashes(),
                'rule_registry_sha256': digest((ROOT / 'data/medsec/labels_v1/rule_registry.json').read_bytes())}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle')
    parser.add_argument('output_dir')
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    pack(args.bundle, args.output_dir, args.run_id)


if __name__ == '__main__':
    main()
