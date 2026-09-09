"""Reproduce a read-only audit of a recorded BYMA snapshot. No network calls."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from byma_data import normalize_byma
from volatility_index import assess, liquidity_summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--rate', type=float, default=0., help='Illustrative continuous rate as a decimal')
    parser.add_argument('--output', type=Path, default=ROOT / 'research/galicia_audit.json')
    args = parser.parse_args()
    snap = json.loads(args.snapshot.read_text(encoding='utf-8'))
    asof = datetime.fromisoformat(snap['retrieved_at'])
    frame = normalize_byma(snap['options'], now=asof)
    rates = {e: args.rate for e in frame.expiration.unique()}
    summary = liquidity_summary(frame)
    result = dict(retrieved_at=asof.isoformat(), rate_source='Illustrative scenarios; not observed',
                  liquidity=json.loads(summary.to_json(orient='records')),
                  complete=assess(frame, asof, rates), partial=assess(frame, asof, rates, True))
    result['rate_scenarios'] = []
    for rate in (0., .2, .4, .6, 1.):
        audit = assess(frame, asof, {e: rate for e in rates}, True)
        result['rate_scenarios'].extend(dict(expiration=t['expiration'], rate=rate, value=t['value']) for t in audit['terms'])
    args.output.write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(summary.to_string(index=False))
    for t in result['partial']['terms']:
        print({k: v for k, v in t.items() if k not in ('contributions', 'warnings', 'publication_blockers')})
    print('30d:', result['partial']['constant_30d'])
    print('Rates:',result['rate_scenarios'])


if __name__ == '__main__':
    main()
