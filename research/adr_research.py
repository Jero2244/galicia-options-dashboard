"""Capture Alpaca data or reproduce the GGAL ADR research audit offline.

Only market-data GETs are used. Bars are stored separately from variance inputs.
"""
import argparse
from datetime import date, datetime, time, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import pandas as pd

from adr_volatility import assess_adr, prepare_snapshot
from alpaca_data import AlpacaData, DataError, NY, OCC
from volatility_index import liquidity_summary


def write_json(path, payload):
    # JSON has no NaN/Infinity; missing observations are null in exported audits.
    clean = json.loads(json.dumps(payload, default=str), parse_constant=lambda _: None)
    path.write_text(json.dumps(clean, indent=2, allow_nan=False), encoding='utf-8')


def client_from_environment():
    load_dotenv(ROOT/'.env')
    key = os.getenv('APCA_API_KEY_ID') or os.getenv('ALPACA_API_KEY')
    secret = os.getenv('APCA_API_SECRET_KEY') or os.getenv('ALPACA_SECRET_KEY')
    if not key or not secret:
        raise DataError('Configure Alpaca credentials in the project .env or environment.')
    return AlpacaData(key, secret)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    capture = sub.add_parser('capture', help='Save the latest available quotes, including prior-session timestamps')
    capture.add_argument('--feed', choices=['indicative', 'opra'], default='indicative')
    capture.add_argument('--start', type=date.fromisoformat, required=True, help='First expiration, not quote date')
    capture.add_argument('--end', type=date.fromisoformat, required=True, help='Last expiration, not quote date')
    capture.add_argument('--output', type=Path)
    audit = sub.add_parser('audit', help='Reproduce an archive without network access')
    audit.add_argument('snapshot', type=Path)
    audit.add_argument('--rate', type=float, default=0., help='Continuous annual USD rate as a decimal scenario')
    audit.add_argument('--max-age', type=float, default=30., help='Minutes before the quote valuation time')
    audit.add_argument('--output', type=Path, default=ROOT/'research/adr_audit.json')
    bars = sub.add_parser('bars', help='Download historical daily trade bars for symbols from an archive')
    bars.add_argument('snapshot', type=Path)
    bars.add_argument('--date', type=date.fromisoformat, required=True)
    bars.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            snap = json.loads(args.snapshot.read_text(encoding='utf-8'))
            frame, asof, retrieved = prepare_snapshot(snap)
            rates = {e: args.rate for e in frame.expiration.unique()}
            result = assess_adr(frame, asof, rates, snap['feed'], args.max_age)
            result.update(retrieved_at=retrieved.isoformat(), input_archive=args.snapshot.name,
                          liquidity=json.loads(liquidity_summary(frame).to_json(orient='records')))
            result['rate_scenarios'] = []
            for rate in sorted({0., .03, .04, .05, args.rate}):
                trial = assess_adr(frame, asof, {e: rate for e in rates}, snap['feed'], args.max_age)
                result['rate_scenarios'].append(dict(continuous_rate=rate,
                                                    value=trial['constant_30d']['value']))
            write_json(args.output, result)
            print('Quote valuation:', asof.isoformat(), '| Feed:', snap['feed'])
            print('30-day research arithmetic:', result['constant_30d'])
            for term in result['terms']:
                print(term['expiration'], 'volatility:', term['value'], '|', '; '.join(term['publication_blockers']))
                if term['contributions']:
                    pd.DataFrame(term['contributions']).to_csv(
                        args.output.with_name(args.output.stem+'_'+term['expiration']+'_constituents.csv'), index=False)
            frame.to_csv(args.output.with_name(args.output.stem+'_quotes.csv'), index=False)
            print('Audit saved:', args.output)
            return
        client = client_from_environment()
        try:
            if args.command == 'capture':
                snapshots = client.chain(args.feed, args.start, args.end)
                now = datetime.now(timezone.utc)
                payload = dict(source='Alpaca latest chain', feed=args.feed, retrieved_at=now.isoformat(),
                               expiration_start=args.start.isoformat(), expiration_end=args.end.isoformat(),
                               snapshots=snapshots)
                # Empty/undated responses never become selectable research archives.
                prepare_snapshot(payload)
                output = args.output or ROOT/'research'/f'adr_snapshot_{now:%Y%m%d_%H%M%S}_{args.feed}.json'
                write_json(output, payload)
                print('Saved', len(snapshots), 'contracts:', output)
            else:
                snap = json.loads(args.snapshot.read_text(encoding='utf-8'))
                prepare_snapshot(snap)
                symbols = [s for s in snap['snapshots'] if OCC.fullmatch(s)]
                data = client.option_bars(symbols, datetime.combine(args.date, time.min, NY),
                                          datetime.combine(args.date, time.max, NY))
                payload = dict(source='Alpaca historical daily option bars', feed='Endpoint default; no feed parameter',
                               retrieved_at=datetime.now(timezone.utc).isoformat(), date=args.date.isoformat(),
                               symbol_source=args.snapshot.name,
                               limitation='Symbols from a later snapshot, not a point-in-time complete universe; '
                                          'trade bars are not used in the volatility strip.', bars=data)
                output = args.output or ROOT/'research'/f'adr_bars_{args.date:%Y%m%d}.json'
                write_json(output, payload)
                print('Historical bars:', sum(len(v) for v in data.values()),
                      '| Contracts with bars:', sum(bool(v) for v in data.values()), '| Saved:', output)
        finally:
            client.close()
    except (DataError, ValueError, OSError) as exc:
        parser.exit(1, str(exc)+'\n')


if __name__ == '__main__':
    main()
