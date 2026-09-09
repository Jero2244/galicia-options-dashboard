"""Alpaca snapshot acquisition and offline ADR research workspace."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import streamlit as st

from adr_volatility import prepare_snapshot
from alpaca_data import AlpacaData, DataError, NY, demo_data
from volatility_ui import volatility_panel

ROOT = Path(__file__).resolve().parent


@st.cache_data(ttl=60, max_entries=4, scope='session', show_spinner=False)
def fetch_adr_snapshot(key, secret, feed, start, end):
    client = AlpacaData(key, secret)
    try:
        snapshots = client.chain(feed, start, end)
        return dict(snapshots=snapshots, feed=feed, retrieved_at=datetime.now(timezone.utc).isoformat(),
                    source='Alpaca latest chain', expiration_start=start.isoformat(),
                    expiration_end=end.isoformat())
    finally:
        client.close()


def adr_workspace(key, secret, feed, refresh, demo, horizon):
    if demo:
        now = datetime.now(timezone.utc)
        frame, _ = demo_data(now)
        st.warning('SAMPLE DATA — Synthetic prices; this is not a historical GGAL observation.')
        volatility_panel(frame, now, market='adr', asof=now, feed='synthetic')
        return
    archives = sorted((ROOT/'research').glob('adr_snapshot_*.json'), reverse=True)
    choices = ['Saved research snapshot', 'Latest Alpaca quotes'] if archives else ['Latest Alpaca quotes']
    source = st.selectbox('Volatility data source', choices, key='adr_source')
    st.caption('Saved snapshots replay without a network request. Latest quotes can come from a prior session; '
               'their actual timestamps determine valuation. Historical trade bars cannot replace bid/ask prices.')
    try:
        if source == 'Saved research snapshot':
            path = st.selectbox('Saved snapshot', archives, format_func=lambda p: p.name, key='adr_archive')
            snapshot = json.loads(path.read_text(encoding='utf-8'))
        else:
            if not key or not secret:
                st.info('Enter the project’s Alpaca credentials in the sidebar to fetch a snapshot.')
                return
            if refresh:
                fetch_adr_snapshot.clear()
            today = datetime.now(NY).date()
            with st.spinner('Loading GGAL ADR option quotes…'):
                snapshot = fetch_adr_snapshot(key, secret, feed, today, today + timedelta(days=horizon))
        frame, asof, retrieved = prepare_snapshot(snapshot)
    except (DataError, ValueError, OSError) as exc:
        st.error(str(exc))
        return
    st.caption(f"Quote valuation: {asof.tz_convert(NY):%Y-%m-%d %H:%M:%S %Z} · "
               f"Retrieved: {retrieved.tz_convert(NY):%Y-%m-%d %H:%M:%S %Z} · "
               f"Actual archive feed: {snapshot['feed'].upper()}")
    if asof.tz_convert(NY).date() < datetime.now(NY).date():
        st.info(f"Historical observation from {asof.tz_convert(NY):%B %d, %Y}; this is not today's index.")
    if snapshot['feed'] == 'indicative':
        st.warning('INDICATIVE RESEARCH — Alpaca modifies these quotes. They are not observed OPRA BBO prices.')
    meta = {k: v for k, v in snapshot.items() if k != 'snapshots'}
    volatility_panel(frame, retrieved, market='adr', asof=asof, feed=snapshot['feed'], metadata=meta)
    with st.expander('Source quotes and replay'):
        st.dataframe(frame[['symbol', 'expiration', 'type', 'strike', 'bid', 'ask', 'bid_size',
                           'ask_size', 'quote_time', 'quote_age_min']], hide_index=True)
        st.download_button('Download source snapshot (JSON)', json.dumps(snapshot, indent=2),
                           file_name=f'adr_snapshot_{retrieved:%Y%m%d_%H%M%S}_{snapshot["feed"]}.json',
                           mime='application/json')
        st.caption('Place this file in research/ to replay it here. The feed selection in the sidebar applies '
                   'to new requests; saved files always retain their original feed and valuation time.')
