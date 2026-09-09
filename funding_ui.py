"""Shared ARS funding inputs for IV/Greeks and the volatility research view."""
from datetime import datetime, timezone
import json

import pandas as pd
import streamlit as st

from alpaca_data import DataError
from byma_data import BymaData
from funding_curve import caucion_curve, fetch_lecaps, lecap_curve, match_expiries


@st.cache_data(ttl=60, max_entries=2, scope='session', show_spinner=False)
def fetch_cauciones():
    client = BymaData()
    try:
        return client.cauciones(), datetime.now(timezone.utc)
    finally:
        client.close()


@st.cache_data(ttl=60, max_entries=2, scope='session', show_spinner=False)
def fetch_treasury():
    return fetch_lecaps(), datetime.now(timezone.utc)


def clear_funding_cache():
    fetch_cauciones.clear()
    fetch_treasury.clear()


def ars_rate_controls(tenors, asof, *, key, manual_key=None):
    """Return per-expiry continuous rates plus a reproducible source audit."""
    source = st.selectbox('ARS rate source', ['Caución curve', 'Manual continuous rates'], key=key+'_source')
    if source == 'Manual continuous rates':
        flat = st.number_input('Illustrative continuous ARS annual rate (%)', min_value=-20.,
            max_value=500., value=0., step=5., key=manual_key or key+'_flat')
        rates = {e:flat/100 for e in tenors}
        separate_key = 'vol_separate_rates' if manual_key == 'vol_flat_rate' else key+'_separate'
        if st.checkbox('Use separate rates for each expiration', key=separate_key):
            for e in rates:
                widget_key = 'vol_rate_'+e if manual_key == 'vol_flat_rate' else key+'_rate_'+e
                rates[e] = st.number_input(f'{e} continuous rate (%)', min_value=-20., max_value=500.,
                                           value=float(flat), key=widget_key)/100
        st.caption('Manual rates are scenarios, not observed funding rates. Zero is never a data fallback.')
        matches = {e:dict(rate=r, source='User-entered continuous scenario', reason='Manual scenario',
                          days=tenors[e], fallback=False, nodes=[], warnings=[]) for e,r in rates.items()}
        return rates, dict(source=source, matches=matches, scenarios={}, asof=asof.isoformat())

    st.caption('Caución TNA → simple-interest discount factors → log-discount interpolation. '
               'Each option expiry uses its own rate. No extrapolation or automatic averaging across tenors.')
    if st.button('Refresh funding data', key=key+'_refresh'):
        clear_funding_cache()
    with st.expander('Funding quality and conventions'):
        allow_undated = st.checkbox('Allow undated caución observations for research', key=key+'_undated')
        st.caption('The public feed currently has trade hours without dates. Strict mode rejects them. '
                   'Opting in does not establish quote age or synchronization with options.')
        basis_label = st.selectbox('Caución observation', ['Last trade', 'Daily volume-weighted average'], key=key+'_basis')
        basis = 'trade' if basis_label == 'Last trade' else 'vwap'
        min_volume = st.number_input('Minimum reported nominal volume (ARS)', min_value=0., value=1_000_000.,
                                      step=1_000_000., key=key+'_volume')
        min_orders = st.number_input('Minimum reported order activity', min_value=1, value=5, key=key+'_orders')
        max_age = st.number_input('Maximum dated trade age (minutes)', min_value=1, max_value=1440,
                                 value=30, key=key+'_age')
        max_gap = st.number_input('Maximum interpolation gap (calendar days)', min_value=1,
                                 max_value=120, value=14, key=key+'_gap')
        day_basis = 365
        st.caption('Simple TNA uses actual calendar days / 365, consistent with the published caución rules. '
                   'Nodes use calendar-day settlement tenors relative to valuation. Intraday cash-settlement '
                   'times are not supplied. Volume and order thresholds are provisional; orders are not trades.')
        use_treasury = st.checkbox('Compare with Bonistas LECAP yields', key=key+'_treasury')
        allow_date_only = fallback = False
        if use_treasury:
            allow_date_only = st.checkbox('Allow date-only LECAP marks and the reported-TEA assumption', key=key+'_treasury_dates')
            fallback = st.checkbox('Use LECAP proxy when caución does not cover an expiry', key=key+'_fallback')
            st.caption('Optional sovereign proxy: CI fixed-rate capitalizing letters only. TIR is assumed to be '
                       'effective annual ACT/365, checked against reported monthly yield. Cash flows are not '
                       'independently verified. Curves stay separate; fallback replaces a whole expiry.')
    errors = []
    raw, retrieved = [], datetime.now(timezone.utc)
    try:
        with st.spinner('Loading ARS funding rates…'):
            raw, retrieved = fetch_cauciones()
    except DataError as exc:
        errors.append(str(exc))
    now = datetime.now(timezone.utc)
    settings = dict(allow_undated=allow_undated, min_volume=min_volume, min_orders=min_orders,
                    max_age_minutes=max_age, day_basis=day_basis, now=now)
    primary = caucion_curve(raw, asof, retrieved, basis=basis, **settings)
    other_basis = 'vwap' if basis == 'trade' else 'trade'
    other = caucion_curve(raw, asof, retrieved, basis=other_basis, **settings)
    treasury, treasury_raw = None, []
    if use_treasury:
        try:
            treasury_raw, treasury_retrieved = fetch_treasury()
            treasury = lecap_curve(treasury_raw, asof, treasury_retrieved,
                                   allow_date_only=allow_date_only, now=datetime.now(timezone.utc))
        except DataError as exc:
            errors.append(str(exc))
    matches = match_expiries(tenors, primary, treasury, allow_treasury_fallback=fallback, max_gap_days=max_gap)
    rates = {e:m['rate'] for e,m in matches.items()}
    other_matches = match_expiries(tenors, other, max_gap_days=max_gap)
    scenarios = {('Daily VWAP' if other_basis == 'vwap' else 'Last trade'): {e:m['rate'] for e,m in other_matches.items()}}
    if treasury:
        scenarios['LECAP reported-TEA proxy'] = {e:m['treasury']['rate'] for e,m in matches.items()}
    for error in errors:
        st.error(error)
    if allow_undated:
        st.warning('Funding research uses undated observations. Their age is unknown; refresh time is not trade time.')
    if basis == 'vwap':
        st.warning('Daily average funding can lag a market move. It is not a contemporaneous quote.')
    if any(m['fallback'] for m in matches.values()):
        st.warning('Some expiries use the explicitly enabled sovereign LECAP proxy fallback.')
    missing = [e for e,m in matches.items() if m['rate'] is None]
    if missing:
        st.info('Funding unavailable for: '+', '.join(missing)+'. Those option estimates remain unavailable.')
    table = pd.DataFrame([dict(Expiration=e, Days=m['days'],
        **{'Continuous rate (%)':100*m['rate'] if m['rate'] is not None else None,
           'Discount factor':m['discount'], 'Source':m['source'], 'Fallback':m['fallback'], 'Status':m['reason']})
        for e,m in matches.items()])
    st.dataframe(table, hide_index=True)
    with st.expander('Curve points and rejected observations'):
        st.caption(f"Funding snapshot retrieved {retrieved.isoformat()}. Cached for 60 seconds; "
                   'snapshots older than 120 seconds or over 5 minutes from options are rejected. '
                   'Use Refresh data to refresh options and funding together.')
        if primary['points']:
            plotted = pd.DataFrame([{'Days':p['days'], 'Last TNA (%)':100*p['last_tna'] if p['last_tna'] is not None else None,
                                    'Daily VWAP TNA (%)':100*p['daily_vwap_tna'] if p['daily_vwap_tna'] is not None else None}
                                   for p in primary['points']])
            st.line_chart(plotted, x='Days', y=['Last TNA (%)', 'Daily VWAP TNA (%)'])
        for curve in [primary] + ([treasury] if treasury else []):
            for warning in curve['warnings']:
                st.warning(warning)
            if curve['observations']:
                observations = pd.DataFrame(curve['observations'])
                observations['reasons'] = observations.reasons.map('; '.join)
                observations['warnings'] = observations.warnings.map('; '.join)
                st.dataframe(observations, hide_index=True)
    audit = dict(source=source, asof=asof.isoformat(), matches=matches, caucion=primary, treasury=treasury,
                 comparison_caucion=other,
                 scenarios=scenarios, errors=errors, max_gap_days=max_gap, treasury_fallback_enabled=fallback,
                 raw_cauciones=raw, raw_lecaps=treasury_raw)
    audit = json.loads(json.dumps(audit, default=str), parse_constant=lambda _:None)
    st.download_button('Download funding audit (JSON)', json.dumps(audit, indent=2, allow_nan=False),
                       file_name='GGAL_ARS_funding_audit.json', mime='application/json', key=key+'_audit')
    return rates, audit
