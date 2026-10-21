"""Credential lookup and cached market-data fetches for the dashboard."""
from datetime import datetime, timezone
import os

import streamlit as st

from alpaca_data import AlpacaData, DataError
from byma_data import BymaData


def credential(name, alias):
    value = os.getenv(name) or os.getenv(alias)
    if value:
        return value
    try:
        return st.secrets.get(name, "")
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return ""


@st.cache_data(ttl=60, max_entries=4, scope="session", show_spinner=False)
def fetch_data(key, secret, option_feed, stock_feed, start, end):
    client = AlpacaData(key, secret)
    try:
        snapshots = client.chain(option_feed, start, end)
        warning = None
        try:
            spot = client.spot(stock_feed)
        except DataError as exc:
            spot = {"price": None, "timestamp": None, "feed": stock_feed}
            warning = str(exc)
        return snapshots, spot, datetime.now(timezone.utc), warning
    finally:
        client.close()


@st.cache_data(ttl=60, max_entries=4, scope="session", show_spinner=False)
def fetch_byma():
    client = BymaData()
    try:
        items = client.chain()
        warning = None
        try:
            spot = client.spot()
        except DataError as exc:
            spot = {"price": None, "timestamp": None, "feed": "BYMADATA"}
            warning = str(exc)
        return items, spot, datetime.now(timezone.utc), warning
    finally:
        client.close()
