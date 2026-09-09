"""Read-only Alpaca market data and conservative option snapshot normalization."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import re
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://data.alpaca.markets"
NY = ZoneInfo("America/New_York")
GREEKS = ("delta", "gamma", "theta", "vega", "rho")
OCC = re.compile(r"^(GGAL)(\d{6})([CP])(\d{8})$")


class DataError(Exception):
    """An error safe to display without exposing request headers or credentials."""


class AlpacaData:
    def __init__(self, api_key: str, secret_key: str):
        self.session = requests.Session()
        self.session.headers.update({"APCA-API-KEY-ID": api_key,
                                     "APCA-API-SECRET-KEY": secret_key})
        retries = Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504],
                        allowed_methods=["GET"], respect_retry_after_header=False)
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def close(self):
        self.session.close()

    def _get(self, path: str, params: dict):
        try:
            response = self.session.get(BASE_URL + path, params=params, timeout=(8, 25))
        except requests.RequestException:
            raise DataError("Could not reach Alpaca. Check your internet connection and retry.") from None
        errors = {
            401: "Alpaca rejected these credentials. Check the API key and secret belong to the same account.",
            403: "Alpaca denied access. Check credentials and data permissions; try Indicative options and IEX stock feeds.",
            429: "Alpaca's request limit was reached. Wait a minute before refreshing.",
        }
        if response.status_code == 400:
            try:
                message = response.json().get('message', '')
            except (ValueError, AttributeError):
                message = ''
            if isinstance(message, str):
                for name in ('APCA-API-KEY-ID', 'APCA-API-SECRET-KEY'):
                    value = self.session.headers.get(name)
                    if value:
                        message = message.replace(value, '[redacted]')
                errors[400] = 'Alpaca rejected the request parameters: ' + message[:300]
        if response.status_code != 200:
            raise DataError(errors.get(response.status_code,
                            f"Alpaca returned HTTP {response.status_code}. Please retry later."))
        try:
            payload = response.json()
        except ValueError:
            raise DataError("Alpaca returned an unreadable response.") from None
        if not isinstance(payload, dict):
            raise DataError("Alpaca returned an unexpected response format.")
        return payload

    def chain(self, feed: str, start: date, end: date) -> dict:
        if feed not in ("indicative", "opra") or end < start:
            raise ValueError("Invalid feed or expiration date range.")
        params = {"feed": feed, "limit": 1000, "root_symbol": "GGAL",
                  "expiration_date_gte": start.isoformat(), "expiration_date_lte": end.isoformat()}
        snapshots, seen = {}, set()
        for _ in range(100):
            payload = self._get("/v1beta1/options/snapshots/GGAL", params)
            page = payload.get("snapshots") or {}
            if not isinstance(page, dict):
                raise DataError("Alpaca returned an invalid option chain.")
            snapshots.update(page)
            token = payload.get("next_page_token")
            if not token:
                return snapshots
            if token in seen:
                raise DataError("Alpaca repeated a page token. Refresh to load a complete chain.")
            seen.add(token)
            params["page_token"] = token
        raise DataError("The option chain exceeded the page limit; narrow the expiration range.")

    def spot(self, feed: str) -> dict:
        if feed not in ("iex", "sip"):
            raise ValueError("Invalid stock feed.")
        payload = self._get("/v2/stocks/GGAL/trades/latest", {"feed": feed})
        trade = payload.get("trade") or {}
        price = number(trade.get("p"))
        return {"price": price if price is not None and price > 0 else None,
                "timestamp": trade.get("t"), "feed": feed}

    def option_bars(self, symbols, start: datetime, end: datetime) -> dict:
        """Historical daily trades/volume for research; NEVER a bid/ask substitute.

        Alpaca documents historical option bars and trades, but only latest quotes.
        Symbol discovery is supplied by the caller; a current chain is not a
        point-in-time historical contract universe.
        """
        symbols = sorted(set(symbols))
        if (start.tzinfo is None
                or end.tzinfo is None or end < start
                or any(not OCC.fullmatch(s) for s in symbols)):
            raise ValueError("Invalid GGAL symbols or timezone-aware date interval.")
        bars = {s: [] for s in symbols}
        for offset in range(0, len(symbols), 100):
            batch = symbols[offset:offset + 100]
            # This endpoint rejects a feed parameter (unlike latest snapshots).
            params = dict(symbols=','.join(batch), timeframe="1Day", limit=10000,
                          start=start.isoformat(), end=end.isoformat(), sort="asc")
            seen = set()
            for _ in range(100):
                payload = self._get("/v1beta1/options/bars", params)
                page = payload.get("bars") or {}
                if not isinstance(page, dict):
                    raise DataError("Alpaca returned invalid historical option bars.")
                for symbol, rows in page.items():
                    if symbol not in batch or not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                        raise DataError("Alpaca returned invalid historical option bars.")
                    bars[symbol].extend(rows)
                token = payload.get("next_page_token")
                if not token:
                    break
                if token in seen:
                    raise DataError("Alpaca repeated a historical-bars page token.")
                seen.add(token)
                params["page_token"] = token
            else:
                raise DataError("Historical option bars exceeded the page limit; shorten the interval.")
        return bars


def number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize(snapshots: dict, now: datetime | None = None) -> pd.DataFrame:
    """Exclude adjusted roots; retain missing values, never substitute zero Greeks."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(NY).date()
    rows = []
    for symbol, snapshot in snapshots.items():
        match = OCC.fullmatch(symbol)
        if not match or not isinstance(snapshot, dict):
            continue
        try:
            expiry = datetime.strptime(match[2], "%y%m%d").date()
        except ValueError:
            continue
        if expiry < today:
            continue
        quote = snapshot.get("latestQuote") or {}
        trade = snapshot.get("latestTrade") or {}
        greeks = snapshot.get("greeks") or {}
        bid, ask = number(quote.get("bp")), number(quote.get("ap"))
        valid_quote = bid is not None and ask is not None and 0 < bid <= ask
        mid = (bid + ask) / 2 if valid_quote else None
        timestamp = pd.to_datetime(quote.get("t"), utc=True, errors="coerce")
        age = (pd.Timestamp(now) - timestamp).total_seconds() / 60 if pd.notna(timestamp) else None
        iv = number(snapshot.get("impliedVolatility"))
        iv = iv if iv is not None and iv > 0 else None
        rows.append({"symbol": symbol, "expiration": expiry.isoformat(),
                     "dte": (expiry - today).days, "type": "Call" if match[3] == "C" else "Put",
                     "strike": int(match[4]) / 1000, "bid": bid, "ask": ask,
                     "bid_size": number(quote.get("bs")), "ask_size": number(quote.get("as")),
                     "mid": mid, "last": number(trade.get("p")),
                     "iv_pct": iv * 100 if iv is not None else None,
                     "spread_pct": (ask - bid) / mid * 100 if valid_quote else None,
                     "quote_time": timestamp, "quote_age_min": age,
                     "quote_valid": valid_quote, "source": "Alpaca",
                     **{g: number(greeks.get(g)) for g in GREEKS}})
    return pd.DataFrame(rows).sort_values(["expiration", "type", "strike"]).reset_index(drop=True) if rows else pd.DataFrame()


def quality_mask(frame: pd.DataFrame, max_age: float, max_spread: float):
    return (frame["quote_valid"] & frame["quote_age_min"].between(0, max_age)
            & frame["spread_pct"].le(max_spread))


def quote_status(row, max_age: float, max_spread: float) -> str:
    reasons = []
    if not row["quote_valid"]:
        reasons.append("Missing, zero or crossed bid/ask")
    age = row["quote_age_min"]
    if pd.isna(age):
        reasons.append("Missing quote timestamp")
    elif age < 0:
        reasons.append("Future quote timestamp")
    elif age > max_age:
        reasons.append("Stale quote")
    if pd.notna(row["spread_pct"]) and row["spread_pct"] > max_spread:
        reasons.append("Wide bid–ask spread")
    return "; ".join(reasons) if reasons else "Passes quality checks"


def demo_data(now: datetime | None = None):
    """Synthetic UI fixtures only; these are not market observations or valuations."""
    now = now or datetime.now(timezone.utc)
    snapshots = {}
    for days in (15, 43, 78):
        expiry = now.astimezone(NY).date() + timedelta(days=days)
        for strike in range(25, 66, 5):
            x = (strike - 45) / 45
            for cp in "CP":
                symbol = f"GGAL{expiry:%y%m%d}{cp}{strike * 1000:08d}"
                delta = 1 / (1 + math.exp(x * 9))
                premium = max(45 - strike if cp == "C" else strike - 45, 0) + 2.1
                snapshots[symbol] = {
                    "latestQuote": {"bp": premium - .15, "ap": premium + .15, "t": now.isoformat()},
                    "latestTrade": {"p": premium},
                    "impliedVolatility": .48 + .65 * x*x - .12*x + days / 1600 + (.015 if cp == "P" else 0),
                    "greeks": {"delta": delta if cp == "C" else delta - 1,
                               "gamma": .038 * math.exp(-x*x*12),
                               "theta": -.03 * math.exp(-x*x*8),
                               "vega": .09 * math.exp(-x*x*8),
                               "rho": .025 if cp == "C" else -.022}}
    frame = normalize(snapshots, now)
    frame["source"] = "Synthetic demo"
    return frame, {"price": 45.0, "timestamp": now.isoformat(), "feed": "synthetic"}
