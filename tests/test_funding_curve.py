from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from alpaca_data import DataError
from byma_data import BA, BymaData
from funding_curve import caucion_curve, curve_rate, fetch_lecaps, lecap_curve, match_expiries
from volatility_index import assess

ROOT = Path(__file__).resolve().parents[1]
ASOF = datetime(2026, 9, 7, 18, tzinfo=timezone.utc)


def row(days, rate=.3, asof=ASOF, **changes):
    maturity = (asof.astimezone(BA).date()+timedelta(days=days)).isoformat()
    return dict(dict(symbol=f'PESOS-{days}', maturityDate=maturity, daysToMaturity=days,
        denominationCcy='ARS', securityType='QS', market='BYMA', settlementType='1',
        trade=rate, vwap=.29, volume=100_000_000, numberOfOrders=20,
        tradeTimestamp=(asof-timedelta(minutes=2)).isoformat(), tradeHour='14:58:00'), **changes)


def curve(rows, **kwargs):
    return caucion_curve(rows, ASOF, ASOF, now=ASOF, **kwargs)


class FundingMathTests(unittest.TestCase):
    def test_simple_tna_and_log_discount_interpolation(self):
        c = curve([row(1, 1.), row(7, .4), row(30, .3)])
        self.assertAlmostEqual(curve_rate(c, 1)['discount'], 1/(1+1/365))
        self.assertAlmostEqual(curve_rate(c, 30)['rate'], math.log1p(.3*30/365)/(30/365))
        point = curve_rate(c, 4)
        expected = math.sqrt((1/(1+1/365))*(1/(1+.4*7/365)))
        self.assertAlmostEqual(point['discount'], expected)
        self.assertEqual(point['nodes'], ['PESOS-1', 'PESOS-7'])
        self.assertAlmostEqual(curve_rate(c, .5)['discount'], (1+1/365)**(-.5))
        # An overnight spike never overwrites the observed 30-day node.
        base = curve([row(1, .3), row(7, .4), row(30, .3)])
        self.assertEqual(curve_rate(c, 30), curve_rate(base, 30))
        self.assertIsNone(curve_rate(c, 20)['rate'])  # 23-day interpolation gap
        self.assertIsNotNone(curve_rate(c, 20, max_gap_days=30)['rate'])
        self.assertIsNone(curve_rate(c, 31)['rate'])
        self.assertIsNone(curve_rate(c, 0)['rate'])
        self.assertAlmostEqual(curve_rate(curve([row(30)], day_basis=360), 30)['discount'], 1/(1+.3*30/360))

    def test_filters_and_no_closing_price_or_vwap_substitution(self):
        cases = [dict(denominationCcy='USD'), dict(securityType='OPT'), dict(settlementType='2'),
                 dict(market='SENEBI'), dict(trade=0), dict(trade=float('nan')), dict(trade=-.1),
                 dict(volume=0), dict(volume=500), dict(numberOfOrders=1), dict(daysToMaturity=29),
                 dict(maturityDate='bad'), dict(tradeTimestamp='2026-09-06T18:00:00+00:00'),
                 dict(tradeTimestamp='2026-09-07T18:01:00+00:00')]
        for change in cases:
            with self.subTest(change=change):
                self.assertFalse(curve([row(30, **change)])['points'])
        self.assertFalse(curve([row(30, trade=0, closingPrice=.3, settlementPrice=30)])['points'])
        self.assertTrue(curve([row(30, trade=0)], basis='vwap')['points'])
        # Duplicate tenors cannot be selected arbitrarily.
        self.assertFalse(curve([row(7), row(7, symbol='duplicate')])['points'])

    def test_undated_opt_in_never_relaxes_explicit_staleness(self):
        undated = row(7, tradeTimestamp=None)
        self.assertFalse(curve([undated])['points'])
        accepted = curve([undated], allow_undated=True)
        self.assertTrue(accepted['points'])
        self.assertIsNone(accepted['points'][0]['observed_at'])
        self.assertIn('unknown', accepted['points'][0]['warnings'][0])
        stale = row(7, tradeTimestamp=(ASOF-timedelta(hours=2)).isoformat())
        self.assertFalse(curve([stale], allow_undated=True)['points'])
        for bad in ['bad', '2026-09-07T18:00:00']:
            self.assertFalse(curve([row(7, tradeTimestamp=bad)], allow_undated=True)['points'])
        for now, retrieved in [(ASOF+timedelta(seconds=121), ASOF), (ASOF, ASOF+timedelta(seconds=6))]:
            self.assertFalse(caucion_curve([undated], ASOF, retrieved, now=now, allow_undated=True)['points'])
        later = ASOF+timedelta(minutes=6)
        self.assertFalse(caucion_curve([undated], ASOF, later, now=later, allow_undated=True)['points'])
        with self.assertRaises(ValueError):
            caucion_curve([undated], ASOF.replace(tzinfo=None), ASOF, now=ASOF)

    def test_real_feed_units_and_missing_dates(self):
        snap = json.loads((ROOT/'tests/fixtures/byma_cauciones_20260907.json').read_text(encoding='utf-8-sig'))
        asof = datetime.fromisoformat(snap['retrieved_at'])
        self.assertFalse(caucion_curve(snap['rows'], asof, asof, now=asof)['points'])
        c = caucion_curve(snap['rows'], asof, asof, now=asof, allow_undated=True)
        points = {p['days']:p for p in c['points']}
        self.assertTrue({1,7,30}.issubset(points))
        self.assertAlmostEqual(points[30]['tna'], .24)  # NOT .0024 or 24
        self.assertNotIn(39, points)  # insufficient nominal volume/order activity
        self.assertTrue(all(p['source'].startswith('BYMA') for p in c['points']))

    def test_negative_implied_forward_is_flagged_without_clipping(self):
        c = curve([row(1, 10.), row(7, .01)])
        self.assertTrue(c['warnings'])
        self.assertEqual(len(c['points']), 2)
        self.assertAlmostEqual(curve_rate(c, 7)['discount'], 1/(1+.01*7/365))

    def test_treasury_is_separate_explicit_and_never_extrapolated(self):
        def bond(days):
            return dict(ticker=f'S{days}', bond_family='LETRAS-FIJO', settlement='CI',
                end_date=(ASOF.date()+timedelta(days=days)).isoformat(), days_to_finish=days,
                tir=.4, mtir=1.4**(1/12)-1, performing=True, last_price=120., volume=100,
                estimation_date='September 7th, 2026')
        raw = [bond(40),bond(50)]
        self.assertFalse(lecap_curve(raw, ASOF, ASOF, now=ASOF)['points'])
        treasury = lecap_curve(raw, ASOF, ASOF, now=ASOF, allow_date_only=True)
        primary = curve([row(1), row(7), row(30)])
        disabled = match_expiries({'near':7, 'far':45, 'outside':70}, primary, treasury)
        self.assertIsNone(disabled['far']['rate'])
        enabled = match_expiries({'near':7, 'far':45, 'outside':70}, primary, treasury, allow_treasury_fallback=True)
        self.assertFalse(enabled['near']['fallback'])
        self.assertTrue(enabled['far']['fallback'])
        self.assertAlmostEqual(enabled['far']['rate'], math.log1p(.4))
        self.assertEqual(enabled['far']['nodes'], ['S40','S50'])
        self.assertIsNone(enabled['outside']['rate'])
        for changes in [dict(settlement='24hs'),dict(bond_family='LETRAS-CER'),
                        dict(estimation_date='September 6th, 2026'),dict(mtir=.9),dict(performing=False)]:
            self.assertFalse(lecap_curve([dict(bond(40),**changes)],ASOF,ASOF,now=ASOF,allow_date_only=True)['points'])

    def test_missing_rate_fails_term_without_losing_required_expiry(self):
        fixture = json.loads((ROOT/'tests/fixtures/cboe_vix_example.json').read_text())
        near = pd.DataFrame(fixture['near']).assign(expiration='2026-09-27', quote_time=ASOF.isoformat())
        far = pd.DataFrame(fixture['next']).assign(expiration='2026-10-17', quote_time=ASOF.isoformat())
        result = assess(pd.concat([near,far]), ASOF, {'2026-09-27':.3, '2026-10-17':None})
        self.assertIsNotNone(result['terms'][0]['value'])
        self.assertIsNone(result['terms'][1]['value'])
        self.assertIn('Funding rate unavailable',result['terms'][1]['reason'])
        self.assertEqual(result['constant_30d']['expirations'],['2026-09-27','2026-10-17'])
        self.assertIsNone(result['constant_30d']['value'])

    def test_transport_errors_are_safe_and_caucion_panel_uses_tls(self):
        with patch('funding_curve.requests.get', side_effect=requests.Timeout('secret')):
            with self.assertRaisesRegex(DataError, 'unavailable'):
                fetch_lecaps()
        with patch('funding_curve.requests.get', return_value=Mock(json=lambda:{'wrong':[]})):
            with self.assertRaisesRegex(DataError, 'format'):
                fetch_lecaps()
        client = BymaData()
        with patch.object(client.session, 'post', return_value=Mock(json=lambda:[row(7)])) as post:
            self.assertEqual(len(client.cauciones()), 1)
            self.assertTrue(post.call_args.args[0].endswith('/cauciones'))
            self.assertNotIn('verify', post.call_args.kwargs)
        client.close()


class FundingUITests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def test_strict_undated_opt_in_manual_and_failure_recovery(self):
        now = datetime.now(timezone.utc)
        rows = [row(d, asof=now, tradeTimestamp=None) for d in (1,7,30,40)]
        script = '''
from datetime import datetime, timezone
import streamlit as st
from funding_ui import ars_rate_controls
rates, audit = ars_rate_controls({'one':1., 'month':30., 'far':60.}, datetime.now(timezone.utc), key='test')
st.session_state['answer'] = rates
st.session_state['audit'] = audit
'''
        with patch.object(BymaData, 'cauciones', return_value=rows):
            at = AppTest.from_string(script, default_timeout=30).run()
            self.assertFalse(at.exception)
            self.assertTrue(all(r is None for r in at.session_state['answer'].values()))
            at.checkbox(key='test_undated').set_value(True).run()
            self.assertFalse(at.exception)
            self.assertIsNotNone(at.session_state['answer']['month'])
            self.assertIsNone(at.session_state['answer']['far'])
            self.assertTrue(any('undated' in w.value for w in at.warning))
            with patch.object(BymaData, 'cauciones', side_effect=DataError('Funding unavailable')):
                at.button(key='test_refresh').click().run()
                self.assertFalse(at.exception)
                self.assertTrue(all(r is None for r in at.session_state['answer'].values()))
                self.assertTrue(at.error)
            at.selectbox(key='test_source').select('Manual continuous rates').run()
            at.number_input(key='test_flat').set_value(40.).run()
            self.assertFalse(at.exception)
            self.assertTrue(all(r == .4 for r in at.session_state['answer'].values()))

    def test_ars_iv_uses_expiry_rates_and_exports_provenance(self):
        now = datetime.now(timezone.utc)
        rows = [row(d, r, asof=now) for d,r in [(7,.2),(30,.4)]]
        script = '''
from datetime import datetime, timedelta, timezone
import pandas as pd
import streamlit as st
from byma_data import BA
from analytics_ui import model_controls
now = datetime.now(timezone.utc)
today = now.astimezone(BA).date()
frame = pd.DataFrame([dict(symbol=str(d), expiration=(today+timedelta(days=d)).isoformat(),
    strike=100., type='Call', mid=5., last=5., bid=4., ask=6.,
    iv_pct=float('nan'), delta=float('nan'), gamma=float('nan'), theta=float('nan'),
    vega=float('nan'), rho=float('nan')) for d in (7,30,60)])
result = model_controls(frame,100.,today,'ARS',asof=now)
st.session_state['result'] = result
'''
        with patch.object(BymaData, 'cauciones', return_value=rows):
            at = AppTest.from_string(script, default_timeout=30).run()
            at.checkbox(key='calculate_ARS').set_value(True).run()
            self.assertFalse(at.exception)
            result = at.session_state['result']
            self.assertTrue(result.iloc[:2].iv_pct.notna().all())
            self.assertNotEqual(result.iloc[0].model_rate, result.iloc[1].model_rate)
            self.assertTrue(pd.isna(result.iloc[2].iv_pct))
            self.assertIn('Funding rate unavailable', result.iloc[2].model_status)
            self.assertTrue(result.model_rate_source.str.startswith('BYMA').iloc[:2].all())

    def test_volatility_curve_sensitivity_and_json_audit(self):
        now = datetime.now(timezone.utc)
        rows = [row(d, asof=now) for d in (1,7,14,21,30,40,45)]
        script = '''
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pandas as pd
from byma_data import BA
from volatility_ui import volatility_panel
now = datetime.now(timezone.utc)
today = now.astimezone(BA).date()
fixture = json.loads(Path('tests/fixtures/cboe_vix_example.json').read_text())
frames = [pd.DataFrame(fixture[name]).assign(expiration=(today+timedelta(days=d)).isoformat(),
          quote_time=now.isoformat()) for name,d in [('near',20),('next',40)]]
volatility_panel(pd.concat(frames),now)
'''
        with patch.object(BymaData,'cauciones',return_value=rows), \
             patch.object(st,'download_button',wraps=st.download_button) as downloads:
            at = AppTest.from_string(script, default_timeout=30).run()
            self.assertFalse(at.exception)
            data = next(c.args[1] for c in reversed(downloads.call_args_list)
                        if c.args[0]=='Download research audit (JSON)')
            audit = json.loads(data)
            self.assertTrue(all(t['value'] is not None for t in audit['terms']))
            self.assertIsNotNone(audit['constant_30d']['value'])
            self.assertFalse(audit['publishable'])
            self.assertTrue(audit['funding_audit']['caucion']['points'])
            scenarios = audit['funding_sensitivity']
            self.assertEqual(set(s['scenario'] for s in scenarios),
                             {'Selected rates','Rates lower','Rates higher','Daily VWAP'})
            self.assertTrue(any(abs(s['change_vol_points'] or 0)>0 for s in scenarios))


if __name__ == '__main__':
    unittest.main()
