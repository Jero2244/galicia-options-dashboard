"""Read-only, unauthenticated BYMADATA snapshots for local GGAL options."""
from datetime import datetime, timezone
import re
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from alpaca_data import DataError, GREEKS, number

BA = ZoneInfo("America/Argentina/Buenos_Aires")
BASE_URL = "https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free"


class BymaData:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._last_request = 0.0

    def close(self):
        self.session.close()

    def panel(self, name):
        if name not in ("options", "leading-equity", "cauciones"):
            raise ValueError("Unsupported BYMA panel")
        time.sleep(max(0, 1 - (time.monotonic() - self._last_request)))
        self._last_request = time.monotonic()
        try:
            response = self.session.post(BASE_URL + "/" + name,
                                         json={"page_size": 5000}, timeout=(8, 25))
            response.raise_for_status()
        except requests.exceptions.SSLError:
            raise DataError("BYMA's certificate could not be verified. Update the trusted CA certificates; TLS verification remains enabled.") from None
        except requests.RequestException:
            raise DataError("Could not load BYMADATA. The public service may be unavailable or rate-limited; retry later.") from None
        try:
            payload = response.json()
        except ValueError:
            raise DataError("BYMADATA returned an unreadable response.") from None
        rows = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DataError("BYMADATA returned an unexpected panel format.")
        if isinstance(payload, dict):
            content = payload.get("content") or {}
            total = number(content.get("total_elements_count"))
            if total is not None and total > len(rows):
                raise DataError("BYMADATA returned a truncated panel. Retry later for a complete chain.")
        return rows

    def chain(self):
        return self.panel("options")

    def cauciones(self):
        return self.panel("cauciones")

    def spot(self):
        rows = [r for r in self.panel("leading-equity")
                if r.get("symbol") == "GGAL" and r.get("denominationCcy") == "ARS"
                and str(r.get("settlementType")) == "2"]
        row = rows[0] if rows else {}
        return {"price": positive(row.get("trade")), "timestamp": None,
                "trade_hour": row.get("tradeHour"), "feed": "BYMADATA · 24hs · ARS"}


def positive(value):
    value = number(value)
    return value if value is not None and value > 0 else None


def normalize_byma(items, start=None, end=None, now=None):
    """Keep undated quotes undated; never infer adjusted decimal strikes."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(BA).date()
    start = start or today
    rows = []
    for item in items:
        if (item.get("underlyingSymbol") != "GGAL" or item.get("securityType") != "OPT"
                or item.get("denominationCcy") != "ARS"
                or str(item.get("settlementType")) != "2"):
            continue
        expiry = pd.to_datetime(item.get("maturityDate"), errors="coerce")
        side = {"CALL": "Call", "PUT": "Put"}.get(item.get("optionType"))
        if pd.isna(expiry) or not side or expiry.date() < start or (end and expiry.date() > end):
            continue
        symbol = item.get("symbol", "")
        strike = positive(item.get("strikePrice"))
        strike_source = "Provider field" if strike else "Unavailable: ambiguous symbol"
        match = re.fullmatch(r"GFG([CV])(\d+(?:\.\d*)?)[A-Z]{1,2}", symbol)
        if strike is None and match and ((match[1] == "C") == (side == "Call")):
            encoded = match[2]
            # Five-digit codes can omit an adjusted strike's decimal separator.
            # Retain those contracts, but do not invent a scale from the spot.
            if "." in encoded or len(encoded) <= 4:
                strike = positive(encoded)
                strike_source = "Symbol"
        bid, ask = number(item.get("bidPrice")), number(item.get("offerPrice"))
        valid = bid is not None and ask is not None and 0 < bid <= ask
        mid = (bid + ask) / 2 if valid else None
        rows.append({"symbol": symbol, "expiration": expiry.date().isoformat(),
                     "dte": (expiry.date() - today).days, "type": side,
                     "strike": strike, "strike_source": strike_source,
                     "bid": bid, "ask": ask, "mid": mid,
                     "last": positive(item.get("trade")),
                     "previous_close": positive(item.get("previousClosingPrice")),
                     "volume": number(item.get("volume")),
                     "open_interest": number(item.get("openInterest")),
                     "bid_size": number(item.get("quantityBid")),
                     "ask_size": number(item.get("quantityOffer")),
                     "last_trade_hour": item.get("tradeHour"),
                     "quote_time": pd.NaT, "quote_age_min": float("nan"),
                     "quote_valid": valid,
                     "spread_pct": (ask - bid) / mid * 100 if valid else None,
                     "iv_pct": float("nan"), "source": "BYMADATA Open (delayed)",
                     "currency": "ARS", "settlement": "24hs",
                     **{g: float("nan") for g in GREEKS}})
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    for col in ("strike", "bid", "ask", "mid", "last", "spread_pct"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.sort_values(["expiration", "type", "strike"]).reset_index(drop=True)
