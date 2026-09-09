"""GGAL ADR/USD research index using the shared Cboe strip mathematics.

Latest snapshots can contain quotes from a prior session. Valuation is anchored
to their latest observed timestamp, never relabeled as today's observation.
"""
from datetime import time
from math import isfinite

import pandas as pd

from alpaca_data import DataError, NY, normalize
from volatility_index import constant_maturity, expiry_minutes, single_term


def prepare_snapshot(snapshot):
    """Validate an archive and normalize at quote time (also for expired archives)."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('snapshots'), dict):
        raise DataError('Expected an Alpaca archive containing snapshots, feed and retrieved_at.')
    if snapshot.get('feed') not in ('opra', 'indicative', 'synthetic'):
        raise DataError('Snapshot must identify its opra, indicative or synthetic feed.')
    retrieved = pd.to_datetime(snapshot.get('retrieved_at'), errors='coerce')
    if pd.isna(retrieved) or retrieved.tzinfo is None:
        raise DataError('Snapshot retrieval time must include a timezone.')
    retrieved = retrieved.tz_convert('UTC')
    # Parse the OCC universe before finding the timestamp anchor. Adjusted roots
    # and malformed records must never move the valuation time.
    try:
        frame = normalize(snapshot['snapshots'], pd.Timestamp('2000-01-01', tz='UTC').to_pydatetime())
    except (TypeError, ValueError, AttributeError):
        raise DataError('Snapshot contains malformed option records.') from None
    if frame.empty:
        raise DataError('Snapshot contains no standard GGAL contracts.')
    qt = pd.to_datetime(frame.quote_time, utc=True, errors='coerce')
    possible = qt[qt.le(retrieved)]
    asof = possible.max()
    if pd.isna(asof):
        raise DataError('No dated option quotes at or before retrieval; an index cannot be valued.')
    # Retain nanosecond precision so the newest quote never becomes a future quote.
    frame = normalize(snapshot['snapshots'], asof)
    frame = frame[frame.expiration.map(lambda e: expiry_minutes(e, asof, time(16), NY) > 0)].copy()
    if frame.empty:
        raise DataError('No unexpired standard GGAL contracts at the quote valuation time.')
    return frame, asof, retrieved


def assess_adr(frame, asof, rates, feed, max_age_minutes=30):
    """Exclude stale/undated/future prices before the forward and strip selection.

    All expiries and strikes remain in the universe, even when their prices fail
    the timestamp policy. Missing prices never turn into zero-bid wing stops.
    """
    if asof.tzinfo is None or not isfinite(max_age_minutes) or max_age_minutes <= 0:
        raise ValueError('Use a timezone-aware valuation and a positive finite quote-age limit.')
    if feed not in ('opra', 'indicative', 'synthetic'):
        raise ValueError('Unknown options feed.')
    terms = []
    for expiry, original in frame.groupby('expiration', sort=True):
        f = original.copy()
        qt = pd.to_datetime(f.quote_time, utc=True, errors='coerce')
        ages = (pd.Timestamp(asof) - qt).dt.total_seconds() / 60
        eligible = ages.between(0, max_age_minutes) & qt.notna()
        f.loc[~eligible, ['bid', 'ask']] = float('nan')
        result = single_term(f, expiry_minutes(expiry, asof, time(16), NY), rates[expiry])
        result.update(expiration=expiry, quotes_supplied=len(f),
                      quotes_within_age_limit=int(eligible.sum()),
                      excluded_quote_timestamps=int((~eligible).sum()),
                      earliest_quote=qt.min().isoformat() if qt.notna().any() else None,
                      latest_quote=qt.max().isoformat() if qt.notna().any() else None)
        blockers = []
        if (~eligible).any():
            blockers.append(f'{int((~eligible).sum())} stale, undated or future quotes excluded before calculation')
        if result['variance'] is None:
            blockers.append(result['reason'])
        else:
            if min(result['put_count'], result['call_count']) < 5:
                blockers.append('Fewer than five OTM strikes on a wing')
            if result['weighted_spread_pct'] > 20:
                blockers.append('Contribution-weighted spread exceeds 20%')
            if result['max_weight_pct'] > 25:
                blockers.append('One strike exceeds 25% of gross variance')
            if result['max_gap_pct'] > 10:
                blockers.append('Strike gap exceeds 10% of forward')
        if feed != 'opra':
            blockers.append('Modified indicative prices, not OPRA BBO' if feed == 'indicative'
                            else 'Synthetic demonstration; not market observations')
        blockers.extend(result['warnings'])
        blockers.extend(['American exercise and dividends have not been adjusted',
                         'USD rates are user assumptions, not a verified Treasury curve',
                         'Snapshot contract universe and deliverables are not independently verified'])
        result['publication_blockers'] = blockers
        terms.append(result)
    return dict(terms=terms, constant_30d=constant_maturity(terms), publishable=False,
                status='Research only; no validated index is published', market='GGAL ADR', currency='USD',
                asof=pd.Timestamp(asof).isoformat(), feed=feed, max_quote_age_minutes=max_age_minutes,
                expiry_convention='16:00 America/New_York on OCC expiration; calendar minutes / 525600',
                rate_source='User-entered continuous annual USD rate scenarios',
                methodology='Cboe option-strip arithmetic adapted to standard GGAL ADR options')
