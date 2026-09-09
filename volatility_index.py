"""Auditable VIX-style research arithmetic; never an official Cboe/BYMA index.

Prices and strikes must use the same per-share currency units. BYMA American
premiums are used as-is: no claim of European variance-swap replication.
"""
from datetime import datetime, time, timezone
from math import exp, floor, isfinite, sqrt
from zoneinfo import ZoneInfo

import pandas as pd

YEAR_MINUTES = 525600
BA = ZoneInfo("America/Argentina/Buenos_Aires")


def expiry_minutes(expiration, asof, expiry_time=time(15, 30), expiry_zone=BA):
    """Local last-trading cutoff convention, not an asserted settlement time."""
    if asof.tzinfo is None:
        raise ValueError("Valuation time must include a timezone")
    end = datetime.combine(datetime.fromisoformat(expiration).date(), expiry_time, expiry_zone)
    # Subtract absolute instants, including when a tenor crosses a DST transition.
    return floor((end.astimezone(timezone.utc) - asof.astimezone(timezone.utc)).total_seconds() / 60)


def constant_maturity(terms, target_days=30):
    """Interpolate total variance; refuse extrapolation or skipping a failed term.

    Terms include ALL listed expiries with minutes and variance (possibly None).
    The refusal to extrapolate is an explicit local policy, not a Cboe rule.
    """
    target = target_days * 1440
    available = sorted((t for t in terms if t['minutes'] > 0), key=lambda t: t['minutes'])
    near = [t for t in available if t['minutes'] <= target]
    after = [t for t in available if t['minutes'] > target]
    chosen = [near[-1]] if near and near[-1]['minutes'] == target else (
        [near[-1], after[0]] if near and after else [])
    result = dict(value=None, expirations=[t.get('expiration') for t in chosen], weights=[])
    if not chosen:
        return dict(result, reason="No listed expirations bracket the target; no extrapolation.")
    if any(t.get('variance') is None or not isfinite(t['variance']) or t['variance'] <= 0 for t in chosen):
        return dict(result, reason="A required expiry cannot be calculated; later liquid expiries cannot replace it.")
    weights = [1.] if len(chosen) == 1 else [
        (chosen[1]['minutes'] - target) / (chosen[1]['minutes'] - chosen[0]['minutes']),
        (target - chosen[0]['minutes']) / (chosen[1]['minutes'] - chosen[0]['minutes'])]
    variance = sum(w * t['minutes'] * t['variance'] for w, t in zip(weights, chosen)) / target
    return dict(result, value=100 * sqrt(variance), variance=variance, weights=weights, reason="Research interpolation")


def single_term(frame, minutes, rate, allow_unresolved=False):
    """Midpoint strip with the two-consecutive-zero bid/ask stop on each wing.

    Local safeguards: positive uncrossed ATM/K0 pairs, crossed wing quotes fail,
    unknown strikes fail unless the caller explicitly asks for a partial strip.
    Null quotes are excluded, never treated as zero quotes. No last-price fallback.
    """
    result = dict(variance=None, value=None, minutes=minutes, rate=rate,
                  forward=None, k0=None, atm=None, contributions=[], warnings=[],
                  put_count=0, call_count=0, reason="", partial=False)
    def fail(reason):
        return dict(result, reason=reason)
    if minutes <= 0 or not isfinite(rate) or abs(rate * minutes / YEAR_MINUTES) > 50:
        return fail("Invalid time or rate")
    f = frame.copy()
    unknown = f.strike.isna() | ~f.strike.map(lambda x: isfinite(x) if pd.notna(x) else False) | (f.strike <= 0)
    if unknown.any():
        result['partial'] = True
        result['warnings'].append(f"{int(unknown.sum())} unresolved strikes; full strike ordering cannot be verified")
        if not allow_unresolved:
            return fail("Unresolved strikes prevent a complete strip")
        f = f[~unknown].copy()
    if f.duplicated(['strike', 'type']).any():
        return fail("Duplicate strike/type: verify settlement and deliverables")
    quotes = {(float(r.strike), r.type): r for _, r in f.iterrows()}
    def good(r):
        return r is not None and pd.notna(r.bid) and pd.notna(r.ask) and isfinite(r.bid) and isfinite(r.ask) and 0 < r.bid <= r.ask
    pairs = []
    for k in sorted(f.strike.unique()):
        c, p = quotes.get((k, 'Call')), quotes.get((k, 'Put'))
        if good(c) and good(p):
            cm, pm = (c.bid + c.ask) / 2, (p.bid + p.ask) / 2
            pairs.append((abs(cm - pm), k, cm, pm))
    if not pairs:
        return fail("No valid same-strike call/put pair for the forward")
    _, atm, cm, pm = min(pairs)
    t = minutes / YEAR_MINUTES
    growth = exp(rate * t)
    forward = atm + growth * (cm - pm)
    result.update(forward=forward, atm=atm)
    below = sorted(k for k in f.strike.unique() if k <= forward)
    if not below or forward <= 0:
        return fail("No strike at or below the forward")
    k0 = below[-1]
    result['k0'] = k0
    c, p = quotes.get((k0, 'Call')), quotes.get((k0, 'Put'))
    if not good(c) or not good(p):
        return fail("The K0 call and put must both have positive uncrossed quotes")
    def entry(k, side, rows):
        bid = sum(r.bid for r in rows) / len(rows)
        ask = sum(r.ask for r in rows) / len(rows)
        return dict(strike=k, type=side, symbols=' + '.join(r.symbol for r in rows),
                    bid=bid, ask=ask, mid=(bid + ask) / 2,
                    spread_pct=100 * (ask - bid) / ((bid + ask) / 2),
                    min_size=min([r.get(col, float('nan')) for r in rows for col in ('bid_size', 'ask_size')]),
                    volume=sum(r.get('volume', float('nan')) for r in rows))
    selected = [entry(k0, 'Put/Call', [c, p])]
    for side in ('Put', 'Call'):
        wing = f[(f.type == side) & ((f.strike < k0) if side == 'Put' else (f.strike > k0))]
        wing = wing.sort_values('strike', ascending=(side == 'Call'))
        zeros, count, stopped = 0, 0, False
        for _, row in wing.iterrows():
            if pd.isna(row.bid) or pd.isna(row.ask):
                continue
            if not isfinite(row.bid) or not isfinite(row.ask) or row.bid < 0 or row.ask < 0:
                return fail(f"Invalid {side.lower()} wing quote")
            if row.bid == 0 or row.ask == 0:
                zeros += 1
                if zeros == 2:
                    stopped = True
                    break
                continue
            zeros = 0
            if row.bid > row.ask:
                return fail(f"Crossed {side.lower()} wing quote")
            selected.append(entry(row.strike, side, [row]))
            count += 1
        result[side.lower() + '_count'] = count
        if not stopped:
            result['warnings'].append(f"{side} wing reaches the supplied universe edge without a two-zero stop")
        if count == 0:
            return fail(f"No usable out-of-the-money {side.lower()} wing")
    selected.sort(key=lambda r: r['strike'])
    for i, row in enumerate(selected):
        delta = (selected[1]['strike'] - row['strike'] if i == 0 else
                 row['strike'] - selected[i-1]['strike'] if i == len(selected)-1 else
                 (selected[i+1]['strike'] - selected[i-1]['strike']) / 2)
        row['delta_k'] = delta
        for q in ('bid', 'mid', 'ask'):
            row['variance_' + q] = 2 / t * delta / row['strike'] ** 2 * growth * row[q]
    correction = (forward / k0 - 1) ** 2 / t
    variance = sum(r['variance_mid'] for r in selected) - correction
    if not isfinite(variance) or variance <= 0:
        return fail("Nonpositive or nonfinite variance")
    gross = variance + correction
    for r in selected:
        r['weight_pct'] = r['variance_mid'] / gross * 100
    result.update(variance=variance, value=100*sqrt(variance), contributions=selected,
                  correction=correction, reason="Partial-strip diagnostic" if result['partial'] else "Research estimate",
                  weighted_spread_pct=sum(r['spread_pct']*r['weight_pct']/100 for r in selected),
                  max_weight_pct=max(r['weight_pct'] for r in selected),
                  max_gap_pct=100*max(selected[i+1]['strike']-selected[i]['strike'] for i in range(len(selected)-1))/forward)
    # Fixed mid-derived forward and fixed basket: quote sensitivity, not tradable bounds.
    for q in ('bid', 'ask'):
        v = sum(r['variance_' + q] for r in selected) - correction
        result[q + '_sensitivity'] = 100*sqrt(v) if v > 0 else None
    return result


def liquidity_summary(frame):
    frame = frame.copy()
    for col in ('last', 'volume', 'bid_size', 'ask_size', 'open_interest'):
        if col not in frame:
            frame[col] = float('nan')
    rows = []
    for (expiry, side), f in frame.groupby(['expiration', 'type'], sort=True):
        valid = f.bid.gt(0) & f.ask.ge(f.bid)
        spread = 200 * (f.ask-f.bid)/(f.ask+f.bid)
        rows.append(dict(expiration=expiry, type=side, contracts=len(f),
                         two_sided=int(valid.sum()), traded=int(f['last'].notna().sum()),
                         reported_volume=float(f.volume.sum(min_count=1)), unknown_strikes=int(f.strike.isna().sum()),
                         median_spread_pct=float(spread[valid].median()),
                         quoted_with_size_ge_5=int((valid & f.bid_size.ge(5) & f.ask_size.ge(5)).sum()),
                         positive_oi=int(f.open_interest.gt(0).sum())))
    return pd.DataFrame(rows)


def assess(frame, asof, rates, allow_unresolved=False, rate_metadata=None):
    """All expiries retained for maturity selection, including failed expiries."""
    terms = []
    for expiry, f in frame.groupby('expiration', sort=True):
        rate = rates.get(expiry)
        r = single_term(f, expiry_minutes(expiry, asof), rate if rate is not None else float('nan'), allow_unresolved)
        funding = (rate_metadata or {}).get(expiry)
        if rate is None:
            r['rate'] = None
            r['reason'] = 'Funding rate unavailable: '+(funding['reason'] if funding else 'missing expiry rate')
        if funding:
            r['funding'] = funding
            r['warnings'].extend(funding.get('warnings', []))
        r['expiration'] = expiry
        reasons = []
        if r['partial']:
            reasons.append('Unresolved instrument strikes')
        if r['variance'] is None:
            reasons.append(r['reason'])
        else:
            if min(r['put_count'], r['call_count']) < 5:
                reasons.append('Fewer than five OTM strikes on a wing')
            if r['weighted_spread_pct'] > 20:
                reasons.append('Contribution-weighted spread exceeds 20%')
            if r['max_weight_pct'] > 25:
                reasons.append('One strike exceeds 25% of gross variance')
            if r['max_gap_pct'] > 10:
                reasons.append('Strike gap exceeds 10% of forward')
        qt = pd.to_datetime(f.quote_time, utc=True, errors='coerce')
        if qt.isna().any():
            reasons.append('Quote timestamps unavailable; synchronization unverified')
        elif ((pd.Timestamp(asof)-qt).dt.total_seconds().abs() > 30*60).any():
            reasons.append('Quotes outside a 30-minute age tolerance')
        reasons.append('American exercise and dividends have not been adjusted')
        reasons.append('ARS funding is a research proxy; conventions and synchronization remain unverified' if funding
                       else 'ARS rates are user assumptions, not a verified discount curve')
        r['publication_blockers'] = reasons
        terms.append(r)
    cm = constant_maturity(terms)
    return dict(terms=terms, constant_30d=cm, publishable=False,
                status='Research only; no validated index is published')
