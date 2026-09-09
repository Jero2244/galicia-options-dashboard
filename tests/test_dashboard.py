from datetime import date, datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch, Mock

import pandas as pd
import requests
from streamlit.testing.v1 import AppTest

from alpaca_data import AlpacaData, DataError, normalize, quality_mask

NOW = datetime(2026, 9, 3, 17, tzinfo=timezone.utc)
SYMBOL = "GGAL261016C00045000"


class DataTests(unittest.TestCase):
    def test_occ_missing_analytics_and_zero_greek(self):
        frame = normalize({SYMBOL: {"greeks": {"delta": 0, "vega": "NaN"}},
                           "GGAL1261016C00045000": {}, "invalid": {}}, NOW)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0].strike, 45)
        self.assertEqual(frame.iloc[0].expiration, "2026-10-16")
        self.assertEqual(frame.iloc[0].delta, 0)
        self.assertTrue(pd.isna(frame.iloc[0].iv_pct))
        self.assertTrue(pd.isna(frame.iloc[0].vega))

    def test_quote_quality_and_iv_percent(self):
        sample = {"latestQuote": {"bp": 2, "ap": 2.2, "t": NOW.isoformat()},
                  "impliedVolatility": .55}
        frame = normalize({SYMBOL: sample}, NOW)
        self.assertAlmostEqual(frame.iloc[0].iv_pct, 55)
        self.assertTrue(quality_mask(frame, 60, 50).iloc[0])
        for bid, ask in [(0, 1), (3, 2), (-1, 2)]:
            sample["latestQuote"].update(bp=bid, ap=ask)
            result = normalize({SYMBOL: sample}, NOW)
            self.assertTrue(pd.isna(result.iloc[0].mid))
            self.assertFalse(quality_mask(result, 60, 50).iloc[0])
        sample["latestQuote"].update(bp=2, ap=2.2, t="2026-09-01T17:00:00Z")
        self.assertFalse(quality_mask(normalize({SYMBOL: sample}, NOW), 60, 50).iloc[0])

    def test_pagination_and_expiration_window(self):
        client = AlpacaData("test", "test")
        with patch.object(client, "_get", side_effect=[
            {"snapshots": {"one": {}}, "next_page_token": "page2"},
            {"snapshots": {"two": {}}},
        ]) as get:
            self.assertEqual(set(client.chain("indicative", date(2026, 9, 3), date(2027, 9, 3))), {"one", "two"})
            self.assertEqual(get.call_args.args[1]["page_token"], "page2")
            self.assertEqual(get.call_args.args[1]["expiration_date_lte"], "2027-09-03")
        client.close()

    def test_repeated_page_is_error(self):
        client = AlpacaData("test", "test")
        with patch.object(client, "_get", return_value={"snapshots": {}, "next_page_token": "same"}):
            with self.assertRaises(DataError):
                client.chain("opra", date(2026, 9, 3), date(2027, 9, 3))
        client.close()

    def test_safe_http_and_network_errors(self):
        client = AlpacaData("private-key", "private-secret")
        for status in (401, 403, 429, 500):
            with patch.object(client.session, "get", return_value=Mock(status_code=status)):
                with self.assertRaises(DataError) as caught:
                    client.spot("iex")
                self.assertNotIn("private", str(caught.exception))
        with patch.object(client.session, "get", side_effect=requests.Timeout("private-secret")):
            with self.assertRaises(DataError) as caught:
                client.spot("iex")
            self.assertNotIn("private-secret", str(caught.exception))
        client.close()


class DashboardTests(unittest.TestCase):
    def test_stale_contracts_visible_and_filter_recovery(self):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(days=30)).strftime("%y%m%d")
        response = {f"GGAL{expiry}C{strike * 1000:08d}": {
            "latestQuote": {"bp": 2, "ap": 2.2, "t": (now - timedelta(days=2)).isoformat()},
            "impliedVolatility": .5, "greeks": {"delta": .5},
        } for strike in (40, 45)}
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict("os.environ", {"APCA_API_KEY_ID": "stale-test", "APCA_API_SECRET_KEY": "stale-test"}), \
             patch.object(AlpacaData, "chain", return_value=response), \
             patch.object(AlpacaData, "spot", return_value={"price": 45, "timestamp": now.isoformat(), "feed": "iex"}):
            at = AppTest.from_file(str(app), default_timeout=20)
            at.session_state["market"] = "US · GGAL ADR · USD"
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.dataframe[0].value), 2)
            self.assertTrue((at.dataframe[0].value.quote_status == "Stale quote").all())
            at.checkbox(key="quality_filter_enabled").set_value(True).run()
            self.assertFalse(at.exception)
            self.assertTrue(any("all failed" in item.value for item in at.info))
            at.button(key="show_available").click().run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.dataframe[0].value), 2)
            self.assertFalse(at.checkbox(key="quality_filter_enabled").value)

    def test_live_response_and_missing_greeks(self):
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        expiry = (now + timedelta(days=30)).strftime("%y%m%d")
        symbol = f"GGAL{expiry}C00045000"
        response = {symbol: {"latestQuote": {"bp": 2, "ap": 2.2, "t": now.isoformat()}}}
        app = Path(__file__).resolve().parents[1] / "app.py"
        with patch.dict("os.environ", {"APCA_API_KEY_ID": "test-only", "APCA_API_SECRET_KEY": "test-only"}), \
             patch.object(AlpacaData, "chain", return_value=response), \
             patch.object(AlpacaData, "spot", return_value={"price": 45, "timestamp": now.isoformat(), "feed": "iex"}):
            at = AppTest.from_file(str(app), default_timeout=20)
            at.session_state["market"] = "US · GGAL ADR · USD"
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(at.dataframe[0].value.iloc[0]["symbol"], symbol)
            self.assertTrue(pd.isna(at.dataframe[0].value.iloc[0]["iv_pct"]))
            self.assertTrue(any("No implied volatility" in item.value for item in at.info))

    def test_connection_screen_and_sample_filters(self):
        app = Path(__file__).resolve().parents[1] / "app.py"
        at = AppTest.from_file(str(app), default_timeout=20)
        at.session_state["market"] = "US · GGAL ADR · USD"
        at.run()
        self.assertFalse(at.exception)
        self.assertTrue(at.info)
        at.toggle(key="demo").set_value(True).run()
        self.assertFalse(at.exception)
        self.assertIn("SAMPLE DATA", at.warning[0].value)
        self.assertEqual(len(at.dataframe[0].value), 18)
        at.multiselect(key="sides").set_value(["Put"]).run()
        self.assertFalse(at.exception)
        self.assertTrue((at.dataframe[0].value["type"] == "Put").all())
        at.selectbox(key="greek").select("rho").run()
        self.assertFalse(at.exception)
        at.multiselect(key="expirations").set_value([]).run()
        self.assertFalse(at.exception)
        self.assertTrue(any("No contracts match" in item.value for item in at.info))


if __name__ == "__main__":
    unittest.main()
