from copy import deepcopy
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from adr_volatility import assess_adr, prepare_snapshot
from alpaca_data import AlpacaData, DataError, NY
from volatility_index import expiry_minutes, liquidity_summary

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT/'research/adr_snapshot_20260907_indicative.json'


class AdrTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(ARCHIVE.read_text())
        self.frame, self.asof, self.retrieved = prepare_snapshot(self.snapshot)
        self.rates = {e: 0. for e in self.frame.expiration.unique()}

    def test_recorded_friday_observation_not_monday_retrieval(self):
        self.assertEqual(len(self.frame), 92)
        self.assertEqual(str(self.asof.date()), '2026-09-04')
        self.assertEqual(str(self.retrieved.date()), '2026-09-07')
        r = assess_adr(self.frame, self.asof, self.rates, 'indicative')
        self.assertAlmostEqual(r['constant_30d']['value'], 46.1217715678299, places=10)
        self.assertEqual(r['constant_30d']['expirations'], ['2026-09-18', '2026-10-16'])
        self.assertEqual([t['minutes'] for t in r['terms']], [20160, 60480])
        self.assertEqual([(t['put_count'], t['call_count']) for t in r['terms']], [(1, 1), (8, 8)])
        self.assertEqual(sum(t['excluded_quote_timestamps'] for t in r['terms']), 0)
        self.assertFalse(r['publishable'])
        self.assertTrue(all('Modified indicative prices, not OPRA BBO' in t['publication_blockers'] for t in r['terms']))
        self.assertEqual(int(liquidity_summary(self.frame).two_sided.sum()), 69)
        self.assertTrue(liquidity_summary(self.frame).reported_volume.isna().all())

    def test_invalid_timestamps_fail_before_forward_and_cannot_skip_failed_expiry(self):
        for timestamp in (pd.NaT, self.asof + timedelta(seconds=1), self.asof - timedelta(days=3)):
            f = self.frame.copy()
            f.loc[f.expiration == '2026-09-18', 'quote_time'] = timestamp
            f['last'] = 1000.  # trades cannot rescue missing quotes
            r = assess_adr(f, self.asof, self.rates, 'opra')
            self.assertIsNone(r['constant_30d']['value'])
            self.assertEqual(r['terms'][0]['excluded_quote_timestamps'], 44)
            self.assertIsNone(r['terms'][0]['forward'])
            self.assertIsNotNone(r['terms'][1]['value'])

    def test_invalid_archives_and_adjusted_roots_cannot_set_anchor(self):
        snap = deepcopy(self.snapshot)
        symbol = next(iter(snap['snapshots']))
        snap['snapshots']['GGAL1' + symbol[4:]] = {'latestQuote': {'t': snap['retrieved_at']}}
        self.assertEqual(prepare_snapshot(snap)[1], self.asof)
        for retrieved in ('bad', '2026-09-07', '2026-09-01T00:00:00Z'):
            bad = dict(self.snapshot, retrieved_at=retrieved)
            with self.assertRaises(DataError):
                prepare_snapshot(bad)
        with self.assertRaises(DataError):
            prepare_snapshot(dict(self.snapshot, feed='unknown'))

    def test_archive_replays_after_contracts_expire(self):
        # The archive normalization is tied to quotes, never the wall-clock date.
        later = dict(self.snapshot, retrieved_at='2030-01-01T00:00:00Z')
        f, asof, _ = prepare_snapshot(later)
        self.assertEqual(len(f), 92)
        self.assertEqual(asof, self.asof)

    def test_new_york_expiry_time_crosses_dst_in_absolute_minutes(self):
        asof = datetime(2026, 10, 30, 16, tzinfo=NY)
        self.assertEqual(expiry_minutes('2026-11-06', asof, time(16), NY), 7*1440+60)
        self.assertEqual(expiry_minutes('2026-09-18', datetime(2026, 9, 18, 20, tzinfo=timezone.utc), time(16), NY), 0)

    def test_quote_age_policy_is_validated(self):
        for age in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                assess_adr(self.frame, self.asof, self.rates, 'opra', age)

    def test_offline_workspace_and_rate_scenarios_preserve_feed(self):
        st.cache_data.clear()
        with patch.object(AlpacaData, 'chain', side_effect=AssertionError('Offline replay attempted network')), \
             patch.object(AlpacaData, 'spot', side_effect=AssertionError('Index requires no spot request')):
            at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30)
            at.session_state['market'] = 'US · GGAL ADR · USD'
            at.session_state['workspace_view'] = 'Volatility index'
            at.run()
            self.assertFalse(at.exception)
            self.assertTrue(any(m.value == '46.12' for m in at.metric))
            self.assertTrue(any('INDICATIVE RESEARCH' in w.value for w in at.warning))
            self.assertTrue(any('September 04, 2026' in m.value for m in at.info))
            at.number_input(key='adr_flat_rate').set_value(4.).run()
            self.assertFalse(at.exception)
            value = assess_adr(self.frame, self.asof, {e: .04 for e in self.rates}, 'indicative')['constant_30d']['value']
            self.assertTrue(any(m.value == f'{value:.2f}' for m in at.metric))
            at.checkbox(key='adr_separate_rates').set_value(True).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.number_input(key='adr_rate_2026-09-18').value, 4.)
            at.number_input(key='adr_max_age').set_value(1).run()
            self.assertFalse(at.exception)

    def test_latest_workspace_uses_quote_time_and_no_underlying_request(self):
        st.cache_data.clear()
        with patch.dict('os.environ', {'APCA_API_KEY_ID': 'test-adr', 'APCA_API_SECRET_KEY': 'test-adr'}), \
             patch.object(AlpacaData, 'chain', return_value=self.snapshot['snapshots']) as chain, \
             patch.object(AlpacaData, 'spot', side_effect=AssertionError('No spot needed')):
            at = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30)
            at.session_state['market'] = 'US · GGAL ADR · USD'
            at.session_state['workspace_view'] = 'Volatility index'
            at.session_state['adr_source'] = 'Latest Alpaca quotes'
            at.run()
            self.assertFalse(at.exception)
            self.assertTrue(chain.called)
            self.assertTrue(any(m.value == '46.12' for m in at.metric))


class HistoricalBarsTests(unittest.TestCase):
    def test_parameter_errors_are_useful_and_redact_credentials(self):
        client = AlpacaData('private-key', 'private-secret')
        response = Mock(status_code=400)
        response.json.return_value = {'message': 'unexpected feed private-key private-secret'}
        with patch.object(client.session, 'get', return_value=response):
            with self.assertRaises(DataError) as caught:
                client.spot('iex')
        self.assertIn('unexpected feed', str(caught.exception))
        self.assertNotIn('private-key', str(caught.exception))
        self.assertNotIn('private-secret', str(caught.exception))
        client.close()

    def test_all_pages_and_batches_are_preserved(self):
        symbols = [f'GGAL261016C{k*1000:08d}' for k in range(1, 102)]
        client = AlpacaData('test', 'test')
        pages = [dict(bars={symbols[0]: [{'c': 1}]}, next_page_token='p2'),
                 dict(bars={symbols[0]: [{'c': 2}], symbols[99]: [{'c': 3}]}),
                 dict(bars={symbols[100]: [{'c': 4}]})]
        with patch.object(client, '_get', side_effect=pages) as get:
            bars = client.option_bars(symbols, datetime(2026, 9, 4, tzinfo=NY),
                                      datetime(2026, 9, 5, tzinfo=NY))
            self.assertNotIn('feed', get.call_args.args[1])
        self.assertEqual(len(bars), 101)
        self.assertEqual([r['c'] for r in bars[symbols[0]]], [1, 2])
        self.assertEqual(bars[symbols[100]][0]['c'], 4)
        self.assertEqual(bars[symbols[1]], [])
        with patch.object(client, '_get', return_value=dict(bars={}, next_page_token='p')):
            with self.assertRaises(DataError):
                client.option_bars(symbols[:1], datetime(2026, 9, 4, tzinfo=NY),
                                   datetime(2026, 9, 5, tzinfo=NY))
        client.close()


if __name__ == '__main__':
    unittest.main()
