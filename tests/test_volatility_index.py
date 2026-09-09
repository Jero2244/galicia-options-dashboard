from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from byma_data import BymaData, normalize_byma
from volatility_index import assess, constant_maturity, expiry_minutes, single_term

ROOT = Path(__file__).resolve().parents[1]


class VolatilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT/'tests/fixtures/cboe_vix_example.json').read_text())
        cls.near = pd.DataFrame(fixture['near'])
        cls.next = pd.DataFrame(fixture['next'])

    def test_pdf_full_worked_example(self):
        n = single_term(self.near, 34484, .00031664)
        t = single_term(self.next, 44954, .00028797)
        self.assertAlmostEqual(n['variance'], .019233906, places=9)
        self.assertAlmostEqual(t['variance'], .019423884, places=9)
        self.assertEqual(n['k0'], 1960)
        self.assertEqual(n['atm'], 1965)
        self.assertAlmostEqual(constant_maturity([n, t])['value'], 13.927842, places=5)
        self.assertEqual(len(n['contributions']), 146)
        self.assertEqual(len(t['contributions']), 122)

    def test_two_zero_stop_and_irregular_delta_k(self):
        n = single_term(self.near, 34484, 0)
        selected = {r['strike']: r for r in n['contributions']}
        self.assertNotIn(1355, selected)  # positive quote beyond two zero bids
        self.assertIn(2125, selected)     # one isolated zero at 2120 is skipped
        self.assertNotIn(2225, selected)
        self.assertEqual(selected[2125]['delta_k'], 25)
        self.assertEqual(selected[1960]['mid'], 22.775)

    def test_scale_and_order_invariance_no_last_trade_dependency(self):
        base = single_term(self.near, 34484, .3)
        f = self.near.sample(frac=1, random_state=1).copy()
        f[['strike','bid','ask']] *= 100
        f['last'] = 99999999
        result = single_term(f, 34484, .3)
        self.assertAlmostEqual(result['value'], base['value'], places=10)

    def test_missing_and_crossed_k0_must_not_shift_to_another_strike(self):
        for change in (float('nan'), 99.):
            f = self.near.copy()
            f.loc[(f.strike == 1960) & (f.type == 'Put'), 'bid'] = change
            self.assertIsNone(single_term(f, 34484, 0)['value'])

    def test_null_and_zero_are_distinct(self):
        f = self.near.copy()
        # Restore the two zero quotes that ended the put wing to null; eligible
        # lower positive-bid strikes are now reachable under null-removal rules.
        f.loc[(f.strike.isin([1360,1365])) & (f.type == 'Put'), 'bid'] = float('nan')
        result = single_term(f, 34484, 0)
        self.assertIn(1355, [r['strike'] for r in result['contributions']])

    def test_unresolved_and_duplicate_strikes(self):
        unknown = dict(self.near.iloc[0], symbol='unknown', strike=float('nan'))
        f = pd.concat([self.near, pd.DataFrame([unknown])], ignore_index=True)
        self.assertIsNone(single_term(f, 34484, 0)['value'])
        result = single_term(f, 34484, 0, True)
        self.assertTrue(result['partial'])
        self.assertIsNotNone(result['value'])
        self.assertIsNone(single_term(pd.concat([self.near,self.near.iloc[:1]]),34484,0)['value'])

    def test_failed_near_term_not_replaced_and_no_extrapolation(self):
        terms = [dict(minutes=d*1440, variance=v, expiration=str(d)) for d,v in [(11,None),(39,.25),(102,.36)]]
        result = constant_maturity(terms)
        self.assertIsNone(result['value'])
        self.assertEqual(result['expirations'], ['11','39'])
        self.assertIsNone(constant_maturity(terms[1:])['value'])

    def test_total_variance_interpolation_and_exact_target(self):
        terms = [dict(minutes=20*1440, variance=.04),dict(minutes=40*1440,variance=.09)]
        self.assertAlmostEqual(constant_maturity(terms)['variance'],(.5*20*.04+.5*40*.09)/30)
        self.assertEqual(constant_maturity([dict(minutes=30*1440,variance=.04)])['value'],20.)

    def test_calendar_minutes_timezone_and_expired(self):
        # 15:30 BA = 18:30 UTC; seconds are floored, leap years keep 365 basis.
        self.assertEqual(expiry_minutes('2026-09-18',datetime(2026,9,17,18,30,1,tzinfo=timezone.utc)),1439)
        self.assertIsNone(single_term(self.near,0,0)['value'])
        with self.assertRaises(ValueError):
            expiry_minutes('2026-09-18',datetime(2026,9,17))

    def test_recorded_byma_snapshot_and_view(self):
        snap = json.loads((ROOT/'research/byma_snapshot_20260907.json').read_text())
        asof = datetime.fromisoformat(snap['retrieved_at'])
        f = normalize_byma(snap['options'], now=asof)
        result = assess(f, asof, {e:0. for e in f.expiration.unique()}, True)
        self.assertFalse(result['publishable'])
        self.assertIsNone(result['constant_30d']['value'])
        oct_term = next(t for t in result['terms'] if t['expiration']=='2026-10-16')
        self.assertAlmostEqual(oct_term['value'],43.8492868,places=5)
        self.assertEqual((oct_term['put_count'],oct_term['call_count']),(14,11))
        st.cache_data.clear()
        with patch.object(BymaData,'chain',return_value=snap['options']), patch.object(BymaData,'spot',return_value=snap['spot']):
            at = AppTest.from_file(str(ROOT/'app.py'),default_timeout=30)
            at.session_state['workspace_view'] = 'Volatility index'
            at.session_state['vol_funding_source'] = 'Manual continuous rates'
            at.run()
            self.assertFalse(at.exception)
            self.assertTrue(any('validated' in w.value for w in at.warning))
            at.checkbox(key='vol_partial').set_value(True).run()
            self.assertFalse(at.exception)
            self.assertTrue(any('research_vol_pct' in d.value.columns for d in at.dataframe))
            at.number_input(key='vol_flat_rate').set_value(40.).run()
            self.assertFalse(at.exception)
            at.checkbox(key='vol_separate_rates').set_value(True).run()
            self.assertFalse(at.exception)


if __name__ == '__main__':
    unittest.main()
