"""ARS research funding curves. No silent extrapolation, smoothing or zero fallback.

Caución trade/vwap fields are annual decimal TNA; settlementPrice uses different
units and is never used. ACT/365 simple interest is an explicit curve convention.
Nodes use calendar-day settlement tenors, mapped to valuation-relative days.
Bonistas is an optional reported-yield proxy, not verified contractual cash flows.
"""
from bisect import bisect_left
from datetime import date, datetime, timezone
from math import exp, isfinite, log1p

import requests

from alpaca_data import DataError, number
from byma_data import BA

BONISTAS_URL = "https://bonistas.com/api/bonds"


def fetch_lecaps():
    try:
        response = requests.get(BONISTAS_URL, timeout=(8, 25))
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError):
        raise DataError("Bonistas LECAP data unavailable or unreadable.") from None
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise DataError("Bonistas returned an unexpected bond-data format.")
    return rows


def _instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _estimate_date(value):
    # Bonistas supplies e.g. "September 7th, 2026". Do not depend on OS locale.
    import re
    match = re.fullmatch(r'([A-Za-z]+) (\d{1,2})(?:st|nd|rd|th)?, (\d{4})', str(value))
    months = 'January February March April May June July August September October November December'.split()
    if match and match[1] in months:
        try:
            return date(int(match[3]), months.index(match[1])+1, int(match[2]))
        except ValueError:
            pass
    return _date(value)


def _snapshot_errors(asof, retrieved_at, now, max_snapshot_age):
    if any(v.tzinfo is None for v in (asof, retrieved_at, now)):
        raise ValueError('Funding timestamps must include timezones')
    errors = []
    age = (now - retrieved_at).total_seconds()
    if age < -5 or age > max_snapshot_age:
        errors.append('Funding snapshot expired or retrieved in the future; refresh data')
    if abs((asof - retrieved_at).total_seconds()) > 300:
        errors.append('Funding and option snapshots are more than 5 minutes apart; refresh both')
    if retrieved_at.astimezone(BA).date() != asof.astimezone(BA).date():
        errors.append('Funding and valuation dates differ')
    return errors


def caucion_curve(rows, asof, retrieved_at, *, now=None, allow_undated=False,
                  basis='trade', min_volume=1_000_000., min_orders=5,
                  max_age_minutes=30, max_snapshot_age=120, day_basis=365):
    """Keep every ARS observation and its rejection reasons for audit.

    A date cannot be inferred from tradeHour. The undated research option still
    rejects stale snapshots, inconsistent maturity tenors and explicitly stale
    or future dated observations. Daily vwap is an explicit alternative, never
    substituted for last trade. numberOfOrders is activity, NOT trade count.
    """
    if basis not in ('trade', 'vwap') or day_basis not in (360, 365):
        raise ValueError('Unsupported rate basis')
    now = now or datetime.now(timezone.utc)
    errors = _snapshot_errors(asof, retrieved_at, now, max_snapshot_age)
    local_date = asof.astimezone(BA).date()
    observations = []
    for raw in rows:
        if raw.get('denominationCcy') != 'ARS' or raw.get('securityType') != 'QS':
            continue
        reasons, warnings = list(errors), []
        maturity = _date(raw.get('maturityDate'))
        days = (maturity-local_date).days if maturity else None
        rate = number(raw.get(basis))
        volume = number(raw.get('volume'))
        orders = number(raw.get('numberOfOrders'))
        if str(raw.get('settlementType')) != '1' or raw.get('market') != 'BYMA':
            reasons.append('Requires BYMA ARS same-day settlement')
        if days is None or days <= 0 or number(raw.get('daysToMaturity')) != days:
            reasons.append('Missing, expired or inconsistent calendar maturity')
        if rate is None or rate <= 0:
            reasons.append('Missing or nonpositive observed TNA')
        if volume is None or volume <= 0 or volume < min_volume:
            reasons.append('Insufficient reported nominal volume')
        if orders is None or orders < max(1, min_orders):
            reasons.append('Insufficient reported order activity')
        stamp = _instant(raw.get('tradeTimestamp'))
        if raw.get('tradeTimestamp') and stamp is None:
            reasons.append('Malformed or timezone-free trade timestamp')
        if raw.get('tradeDate') and not _date(raw.get('tradeDate')):
            reasons.append('Malformed trade date')
        if stamp is None and _date(raw.get('tradeDate')) and raw.get('tradeHour'):
            try:
                stamp = datetime.fromisoformat(raw['tradeDate']+'T'+raw['tradeHour']).replace(tzinfo=BA)
            except ValueError:
                pass
        if stamp is None:
            if allow_undated:
                warnings.append('Undated research observation; age and synchronization unknown')
            else:
                reasons.append('Trade date unavailable; enable undated research explicitly')
        else:
            age = (asof-stamp).total_seconds()/60
            if age < 0 or age > max_age_minutes or stamp.astimezone(BA).date() != local_date:
                reasons.append('Stale or future trade timestamp')
        if basis == 'vwap':
            warnings.append('Daily VWAP; not a contemporaneous or short-window funding rate')
        last, vwap = number(raw.get('trade')), number(raw.get('vwap'))
        if last is not None and vwap is not None and abs(last-vwap) >= .05:
            warnings.append('Last TNA differs from daily VWAP by at least 5 percentage points; retained')
        observation = dict(symbol=raw.get('symbol'), maturity=raw.get('maturityDate'), days=days,
                           tna=rate, last_tna=last, daily_vwap_tna=vwap, volume=volume,
                           orders=orders, trade_hour=raw.get('tradeHour'),
                           observed_at=stamp.isoformat() if stamp else None,
                           source='BYMA caución '+('last trade' if basis == 'trade' else 'daily VWAP'),
                           warnings=warnings, reasons=reasons, eligible=not reasons)
        if not reasons:
            value = -log1p(rate*days/day_basis)
            if not isfinite(value):
                observation['eligible'] = False
                observation['reasons'].append('Nonfinite discount factor')
            else:
                observation['log_discount'] = value
        observations.append(observation)
    # Never choose an arbitrary duplicate or average instruments silently.
    return _finish(observations, retrieved_at, dict(basis=basis, day_basis=day_basis,
        min_volume=min_volume, min_orders=min_orders, max_age_minutes=max_age_minutes,
        max_snapshot_age=max_snapshot_age, allow_undated=allow_undated))


def _finish(observations, retrieved_at, policy):
    seen = {}
    for row in observations:
        if row['eligible']:
            seen.setdefault(row['days'], []).append(row)
    for same in seen.values():
        if len(same) > 1:
            for row in same:
                row['eligible'] = False
                row['reasons'].append('Duplicate eligible maturity; ambiguous curve node')
    points = sorted((dict(r) for r in observations if r['eligible']), key=lambda r:r['days'])
    warnings = []
    for left, right in zip(points, points[1:]):
        if right['log_discount'] > left['log_discount']:
            warnings.append(f"Negative implied forward between {left['days']} and {right['days']} days; observations retained")
    return dict(points=points, observations=observations, warnings=warnings,
                retrieved_at=retrieved_at.isoformat(), policy=policy)


def lecap_curve(rows, asof, retrieved_at, *, now=None, allow_date_only=False, max_snapshot_age=120):
    """Optional Bonistas CI LECAP proxy: assume reported tir is TEA ACT/365.

    Restrict to fixed-rate capitalizing letters. No issuer prose, fitted curva,
    duration, coupon or inferred redemption enters this calculation. Date-only
    marks are explicitly opt-in, even when estimation_date is today.
    """
    now = now or datetime.now(timezone.utc)
    errors = _snapshot_errors(asof, retrieved_at, now, max_snapshot_age)
    local_date = asof.astimezone(BA).date()
    observations = []
    for raw in rows:
        if raw.get('bond_family') != 'LETRAS-FIJO' or raw.get('settlement') != 'CI':
            continue
        reasons = list(errors)
        maturity = _date(raw.get('end_date'))
        days = (maturity-local_date).days if maturity else None
        rate, monthly = number(raw.get('tir')), number(raw.get('mtir'))
        if days is None or days <= 0 or number(raw.get('days_to_finish')) != days:
            reasons.append('Invalid or inconsistent LECAP maturity')
        if rate is None or not -1 < rate < 100:
            reasons.append('Missing or invalid reported TEA')
        elif monthly is None or not -1 < monthly < 1 or abs((1+monthly)**12-1-rate) > .002:
            reasons.append('Reported annual/monthly yields are inconsistent')
        if raw.get('performing') is not True or (number(raw.get('last_price')) or 0) <= 0 or (number(raw.get('volume')) or 0) <= 0:
            reasons.append('No performing instrument with positive price and activity')
        if _estimate_date(raw.get('estimation_date')) != local_date:
            reasons.append('LECAP estimation date is stale or missing')
        if not allow_date_only:
            reasons.append('Date-only Treasury marks require explicit research opt-in')
        observation = dict(symbol=raw.get('ticker'), maturity=raw.get('end_date'), days=days,
            tea=rate, source='Bonistas LECAP reported-TEA proxy', observed_at=None,
            estimation_date=raw.get('estimation_date'), warnings=[
                'Assumes reported TIR is effective annual ACT/365; cash flows not independently verified',
                'Date-only mark; intraday quote age unknown; sovereign and funding bases differ'],
            reasons=reasons, eligible=not reasons)
        if not reasons:
            observation['log_discount'] = -log1p(rate)*days/365
        observations.append(observation)
    return _finish(observations, retrieved_at, dict(allow_date_only=allow_date_only,
        max_snapshot_age=max_snapshot_age, convention='Reported TEA assumed ACT/365; CI only'))


def curve_rate(curve, days, *, max_gap_days=14):
    """Interpolate log discounts with D(0)=1; refuse long gaps/extrapolation."""
    missing = dict(rate=None, discount=None, source='Unavailable', nodes=[], warnings=[])
    if not isfinite(days) or days <= 0:
        return dict(missing, reason='Nonpositive or invalid target tenor')
    points = curve['points']
    if not points or days > points[-1]['days']+1e-10:
        return dict(missing, reason='No funding coverage to this expiry; no extrapolation')
    i = bisect_left([p['days'] for p in points], days)
    if i == len(points):
        i -= 1
    right = points[i]
    if abs(right['days']-days) < 1e-10:
        selected, value = [right], right['log_discount']
    else:
        left = points[i-1] if i else dict(days=0., log_discount=0., symbol='D(0)=1', warnings=[])
        if right['days']-left['days'] > max_gap_days:
            return dict(missing, reason=f'Funding maturity gap exceeds {max_gap_days:g} days')
        w = (days-left['days'])/(right['days']-left['days'])
        selected, value = [left, right], (1-w)*left['log_discount']+w*right['log_discount']
    return dict(rate=-value/(days/365), discount=exp(value), source=right['source'],
                nodes=[p['symbol'] for p in selected],
                warnings=sorted(set(curve['warnings']+[w for p in selected for w in p['warnings']])),
                reason='Exact curve node' if len(selected)==1 else 'Log-discount interpolation')


def match_expiries(tenors, caucion, treasury=None, *, allow_treasury_fallback=False, max_gap_days=14):
    """Separate curves; fallback substitutes a whole expiry, never splices nodes."""
    matches = {}
    for expiry, days in tenors.items():
        primary = curve_rate(caucion, days, max_gap_days=max_gap_days)
        alternative = curve_rate(treasury, days, max_gap_days=max_gap_days) if treasury else None
        selected = dict(primary)
        selected['fallback'] = False
        if primary['rate'] is None and allow_treasury_fallback and alternative and alternative['rate'] is not None:
            selected = dict(alternative, fallback=True, reason='Explicit Treasury proxy fallback: '+primary['reason'])
        matches[expiry] = dict(selected, days=days, caucion=primary, treasury=alternative)
    return matches
