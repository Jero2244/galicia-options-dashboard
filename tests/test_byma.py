from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pandas as pd
import requests
import streamlit as st
from streamlit.testing.v1 import AppTest

from alpaca_data import DataError, quality_mask
from byma_data import BymaData, normalize_byma

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 4, 21, tzinfo=timezone.utc)


def sample(**changes):
    return dict(symbol="GFGC7000OC", underlyingSymbol="GGAL", securityType="OPT",
                denominationCcy="ARS", settlementType="2", maturityDate="2026-10-16",
                optionType="CALL", bidPrice=100, offerPrice=120, trade=110,
                tradeHour="16:59:30", volume=12, openInterest=0, **changes)


class BymaTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()

    def test_actual_response_no_invented_timestamps_or_analytics(self):
        items = json.loads((ROOT / "tests/fixtures/byma_ggal_20260904.json").read_text())
        frame = normalize_byma(items, now=NOW)
        self.assertEqual(len(frame), 73)
        self.assertEqual(set(frame.type), {"Call", "Put"})
        self.assertEqual(frame.strike.isna().sum(), 4)
        self.assertTrue(frame.quote_time.isna().all())
        self.assertTrue(frame.iv_pct.isna().all())
        self.assertFalse(quality_mask(frame, 10080, 200).any())

    def test_filter_other_underlyings_currencies_settlement_expiries(self):
        base = sample()
        items = [base] + [dict(base, **change) for change in (
            {"underlyingSymbol": "YPFD"}, {"denominationCcy": "USD"},
            {"settlementType": "1"}, {"maturityDate": "2025-01-01"},
            {"maturityDate": "invalid"}, {"optionType": "UNKNOWN"})]
        frame = normalize_byma(items, now=NOW)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0].strike, 7000)
        self.assertEqual(frame.iloc[0].mid, 110)
        self.assertTrue(normalize_byma(items, end=NOW.date(), now=NOW).empty)

    def test_adjusted_strike_not_guessed_and_explicit_strike_wins(self):
        row = dict(sample(), symbol="GFGC40283F")
        self.assertTrue(pd.isna(normalize_byma([row], now=NOW).iloc[0].strike))
        row["strikePrice"] = 4028.3
        self.assertEqual(normalize_byma([row], now=NOW).iloc[0].strike, 4028.3)

    def test_zero_trade_and_crossed_quote(self):
        row = dict(sample(), trade=0, bidPrice=120, offerPrice=100, previousClosingPrice=95)
        result = normalize_byma([row], now=NOW).iloc[0]
        self.assertTrue(pd.isna(result.mid))
        self.assertTrue(pd.isna(result["last"]))
        self.assertEqual(result.previous_close, 95)

    def test_transport_formats_errors_and_tls(self):
        client = BymaData()
        with patch.object(client.session, "post") as post, patch("byma_data.time.sleep"):
            response = Mock()
            post.return_value = response
            for payload in ([sample()], {"data": [sample()]}):
                response.json.return_value = payload
                self.assertEqual(len(client.chain()), 1)
                self.assertNotIn("verify", post.call_args.kwargs)
            response.json.return_value = {"data": [], "content": {"total_elements_count": 20}}
            with self.assertRaises(DataError):
                client.chain()
            response.json.return_value = {"error": "changed API"}
            with self.assertRaises(DataError):
                client.chain()
            post.side_effect = requests.exceptions.SSLError()
            with self.assertRaisesRegex(DataError, "certificate"):
                client.chain()
            post.side_effect = requests.Timeout()
            with self.assertRaises(DataError):
                client.chain()
        client.close()

    def test_byma_default_ui_and_market_switch(self):
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
        rows = [dict(sample(), maturityDate=expiry),
                dict(sample(), maturityDate=expiry, symbol="GFGV10300O", optionType="PUT")]
        with patch.object(BymaData, "chain", return_value=rows), \
             patch.object(BymaData, "spot", return_value={"price": 7030, "timestamp": None, "feed": "BYMADATA"}):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertFalse(at.exception)
            self.assertEqual(len(at.dataframe[0].value), 2)
            self.assertTrue((at.dataframe[0].value.currency == "ARS").all())
            self.assertFalse(at.text_input)
            at.checkbox(key="quality_filter_enabled").set_value(True).run()
            self.assertFalse(at.exception)
            self.assertTrue(any("all failed" in i.value for i in at.info))
            at.button(key="show_available").click().run()
            self.assertEqual(len(at.dataframe[0].value), 2)
            at.selectbox(key="market").select("US · GGAL ADR · USD").run()
            at.toggle(key="demo").set_value(True).run()
            self.assertFalse(at.exception)
            self.assertTrue((at.dataframe[0].value.currency == "USD").all())
            at.selectbox(key="market").select("BYMA · GGAL shares · ARS").run()
            self.assertFalse(at.exception)
            self.assertTrue((at.dataframe[0].value.currency == "ARS").all())

    def test_service_failure_does_not_show_sample_data(self):
        with patch.object(BymaData, "chain", side_effect=DataError("Service unavailable")):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.error[0].value, "Service unavailable")
            self.assertFalse(at.dataframe)
