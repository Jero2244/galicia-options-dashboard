import math
from pathlib import Path
import unittest

from option_analytics import bs_price, implied_volatility, calculate_greeks, build_payoff


class AnalyticsTests(unittest.TestCase):
    def test_reference_and_parity(self):
        self.assertAlmostEqual(bs_price(100, 100, 1, .05, .2), 10.450583572, places=8)
        for q in (0, .03):
            call = bs_price(100, 105, .6, -.01, .4, "call", q)
            put = bs_price(100, 105, .6, -.01, .4, "put", q)
            self.assertAlmostEqual(call-put, 100*math.exp(-q*.6)-105*math.exp(.01*.6))

    def test_iv_roundtrip_and_bounds(self):
        for kind in ("call", "put"):
            for vol in (.05, .2, 1.5, 4.):
                premium = bs_price(100, 105, .6, .03, vol, kind, .02)
                self.assertAlmostEqual(implied_volatility(premium, 100, 105, .6, .03, kind, .02), vol, places=7)
        for premium in (-1, 100, float("nan")):
            with self.assertRaises(ValueError):
                implied_volatility(premium, 100, 100, 1, 0)
        with self.assertRaises(ValueError):
            implied_volatility(2, 100, 100, 0, 0)
        self.assertEqual(implied_volatility(0, 100, 100, 1, 0), 0)

    def test_greeks_against_price_derivatives(self):
        h = .0001
        for kind in ("call", "put"):
            g = calculate_greeks(100, 105, .6, .03, .4, kind, .02)
            def p(s=100, t=.6, r=.03, v=.4):
                return bs_price(s, 105, t, r, v, kind, .02)
            self.assertAlmostEqual(g["delta"], (p(s=100+h)-p(s=100-h))/(2*h), places=6)
            self.assertAlmostEqual(g["gamma"], (p(s=100+.01)-2*p()+p(s=100-.01))/.01**2, places=6)
            self.assertAlmostEqual(g["theta"], -(p(t=.6+h)-p(t=.6-h))/(2*h*365), places=6)
            self.assertAlmostEqual(g["vega"], (p(v=.4+h)-p(v=.4-h))/(2*h*100), places=6)
            self.assertAlmostEqual(g["rho"], (p(r=.03+h)-p(r=.03-h))/(2*h*100), places=6)

    def test_spread_and_covered_call(self):
        long = dict(type="call", strike=100, premium=7, quantity=1, multiplier=100)
        short = dict(type="call", strike=110, premium=3, quantity=-1, multiplier=100)
        self.assertEqual(build_payoff([0, 100, 104, 110, 200], [long, short]), [-400, -400, 0, 600, 600])
        stock = dict(type="stock", strike=0, premium=100, quantity=100, multiplier=1)
        self.assertEqual(build_payoff([0, 100, 200], [stock, short]), [-9700, 300, 1300])
        with self.assertRaises(ValueError):
            build_payoff([100], [dict(long, expiration="2026-10-16"), dict(short, expiration="2026-11-20")])

    def test_dashboard_calculation_and_payoff(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"), default_timeout=30)
        at.session_state["market"] = "US · GGAL ADR · USD"
        at.session_state["demo"] = True
        at.run()
        at.checkbox(key="calculate_USD").set_value(True).run()
        self.assertFalse(at.exception)
        chain = at.dataframe[0].value
        self.assertTrue(chain.iv_pct.notna().any())
        self.assertIn("reported_iv_pct", chain.columns)
        next(b for b in at.button if b.label == "Add leg").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any(d.label == "Download payoff (CSV)" for d in at.get("download_button")))


if __name__ == "__main__":
    unittest.main()
