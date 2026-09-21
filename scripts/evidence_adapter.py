#!/usr/bin/env python3
# Adapter: converts per-rule evidence JSON files (NS-XX.json) into platform-aggregated bundle format expected by gate_decision.py
# Usage: python evidence_adapter.py --evidence-dir results/evidence/ --platform android --output results/evidence/android.json
import argparse, os, json
parser = argparse.ArgumentParser()
parser.add_argument('--evidence-dir', default='results/evidence')
parser.add_argument('--platform', choices=['android','ios'], required=True)
parser.add_argument('--output')
args = parser.parse_args()
bundle = {"platform": args.platform, "rules": {}, "bundle_valid": True, "missing": [], "invalid": []}
for f in os.listdir(args.evidence_dir):
    if f.endswith('.json') and f.startswith('NS-'):
        with open(os.path.join(args.evidence_dir, f)) as fh:
            d = json.load(fh)
        bundle["rules"][d.get("test_case", f.replace('.json',''))] = d.get("status","UNKNOWN")
if args.output:
    with open(args.output,'w') as out:
        json.dump(bundle, out, indent=2)
print(f"Adapter wrote {args.output}")
