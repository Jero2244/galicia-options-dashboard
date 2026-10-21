from datetime import datetime, timezone
import math
from pathlib import Path
import unittest

from analytics_ui import years_to_expiry
from option_analytics import binomial_price, bs_price, implied_volatility, calculate_greeks, build_payoff, solve_iv


class AnalyticsTests(unittest.TestCase):
    def test_reference_and_parity(self):
        self.assertAlmostEqual(bs_price(100, 100, 1, .05, .2), 10.450583572, places=8)
        for q in (0, .03):
            call = bs_price(100, 105, .6, -.01, .4, "call", q)
            put = bs_price(100, 105, .6, -.01, .4, "put", q)
            self.assertAlmostEqual(call-put, 100*math.exp(-q*.6)-105*math.exp(.01*.6))

    def test_european_lattice_matches_black_scholes(self):
        for spot, strike, time, rate, vol, kind, q in [(100, 100, 1, .05, .2, "call", 0), (100, 105, .6, .03, .4, "put", .02),
                                                       (100, 90, .25, .08, .5, "call", .03), (100, 110, 2, -.01, .15, "put", 0),
                                                       (100, 100, 1/365, .2, .6, "call", 0)]:
            self.assertAlmostEqual(binomial_price(spot, strike, time, rate, vol, kind, q, american=False),
                                   bs_price(spot, strike, time, rate, vol, kind, q), delta=2e-4)

    def test_american_exercise_premium(self):
        european = binomial_price(100, 110, 1, .08, .3, "put", american=False)
        american = binomial_price(100, 110, 1, .08, .3, "put")
        self.assertGreater(american, european + .1)
        self.assertGreaterEqual(american, 10)  # at least intrinsic value
        # No dividends: early exercise of a call is never optimal.
        self.assertAlmostEqual(binomial_price(100, 90, .5, .05, .3, "call"),
                               binomial_price(100, 90, .5, .05, .3, "call", american=False), places=9)
        # A large dividend yield makes early exercise of a deep ITM call valuable.
        self.assertGreater(binomial_price(100, 70, 1, .02, .3, "call", .10),
                           binomial_price(100, 70, 1, .02, .3, "call", .10, american=False) + .05)

    def test_zero_vol_and_expiry(self):
        self.assertEqual(binomial_price(100, 90, 0, .05, .3), 10)
        self.assertAlmostEqual(binomial_price(100, 90, 1, .05, 0, american=False), 100 - 90*math.exp(-.05))
        self.assertGreaterEqual(binomial_price(100, 110, 1, .05, 0, "put"), 10)

    def test_iv_roundtrip_and_bounds(self):
        for american in (True, False):
            for kind in ("call", "put"):
                for vol in (.05, .2, 1.5, 4.):
                    premium = binomial_price(100, 100, .6, .03, vol, kind, .02, american=american)
                    self.assertAlmostEqual(implied_volatility(premium, 100, 100, .6, .03, kind, .02, american=american),
                                           vol, places=6)
        for premium in (-1, 100, float("nan")):
            with self.assertRaises(ValueError):
                implied_volatility(premium, 100, 100, 1, 0)
        with self.assertRaises(ValueError):
            implied_volatility(2, 100, 100, 0, 0)
        self.assertEqual(implied_volatility(0, 100, 100, 1, 0), 0)

    def test_american_put_below_intrinsic_is_rejected(self):
        # Fine for a European put (forward lower bound is lower), impossible for an American one.
        with self.assertRaises(ValueError):
            implied_volatility(9, 100, 110, 1, .08, "put")
        self.assertGreater(implied_volatility(9, 100, 110, 1, .08, "put", american=False), 0)

    def test_iv_tolerates_float_noise_at_intrinsic_boundary(self):
        intrinsic = 100 - 100*math.exp(-.03)
        for noise in (-1e-12, 0, 1e-12):
            self.assertEqual(implied_volatility(intrinsic + noise, 100, 100, 1, .03, "call"), 0)

    def test_batch_solver_reports_each_error(self):
        sign = [1, 1, -1, 1]
        iv, errors = solve_iv([5, 5, 1e-3, float("nan")], 100, [100, 100, 100, 100], [.25, 0, .25, .25], .05, sign, 0)
        self.assertGreater(iv[0], 0)
        self.assertIn("time remaining", errors[1])
        self.assertTrue(errors[2] is None or "bounds" in errors[2])
        self.assertIn("finite", errors[3])

    def test_greeks_against_european_closed_form(self):
        h = .0001
        for kind in ("call", "put"):
            g = calculate_greeks(100, 105, .6, .03, .4, kind, .02, american=False)
            def p(s=100, t=.6, r=.03, v=.4):
                return bs_price(s, 105, t, r, v, kind, .02)
            self.assertAlmostEqual(g["delta"], (p(s=100+h)-p(s=100-h))/(2*h), delta=2e-4)
            self.assertAlmostEqual(g["gamma"], (p(s=100+.01)-2*p()+p(s=100-.01))/.01**2, delta=3e-4)
            self.assertAlmostEqual(g["theta"], -(p(t=.6+h)-p(t=.6-h))/(2*h*365), delta=1e-4)
            self.assertAlmostEqual(g["vega"], (p(v=.4+h)-p(v=.4-h))/(2*h*100), delta=2e-4)
            self.assertAlmostEqual(g["rho"], (p(r=.03+h)-p(r=.03-h))/(2*h*100), delta=2e-4)

    def test_american_deep_itm_put_delta_is_minus_one(self):
        self.assertAlmostEqual(calculate_greeks(50, 100, .5, .08, .3, "put")["delta"], -1, places=6)

    def test_year_fraction_uses_expiry_cutoff_and_dst(self):
        # 2026-10-30 16:00 EDT -> 2026-11-06 16:00 EST crosses the DST change: 7 days + 1 hour.
        asof = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
        years = years_to_expiry(["2026-11-06"], asof, "USD")
        self.assertAlmostEqual(years["2026-11-06"], (7*1440+60)/525600)
        # Same-day expiry is live until the 16:00 New York cutoff, then not.
        morning = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)  # 10:00 EST
        self.assertAlmostEqual(years_to_expiry(["2026-11-06"], morning, "USD")["2026-11-06"], 6*60/525600)
        self.assertLessEqual(years_to_expiry(["2026-11-06"], datetime(2026, 11, 6, 21, 1, tzinfo=timezone.utc), "USD")["2026-11-06"], 0)
        self.assertAlmostEqual(years_to_expiry(["2026-11-06"], morning, "ARS")["2026-11-06"], 3.5*60/525600)

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
