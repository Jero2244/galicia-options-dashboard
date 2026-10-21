"""Option-analytics dashboard page. app.py calls run() on every Streamlit rerun."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from alpaca_data import DataError, GREEKS, NY, demo_data, normalize, quality_mask, quote_statuses
from byma_data import BA, normalize_byma
from analytics_ui import model_controls, payoff_builder
from volatility_ui import volatility_panel
from adr_volatility_ui import adr_workspace
from funding_ui import clear_funding_cache
from dashboard_data import credential, fetch_byma, fetch_data

BYMA_NOTES = """
**Instrument:** BYMA options on GGAL local shares, quoted in ARS. The public feed uses
settlement code 2 (displayed as 24hs); BYMA's current rules settle option premiums T+0
and exercises T+1. Do not infer current legal settlement terms from the feed code.
Source: [BYMADATA Open](https://open.bymadata.com.ar/). No account is required.
The public website's underlying interface can change without notice.

**Prices:** Zero last trades remain blank; previous close is a separate column.
Midpoints require positive, non-crossed bid and ask prices. Volume and open interest
are displayed as reported, including zeros; a zero does not establish data completeness.
No full quote timestamps are supplied, so all quotes fail the optional age filter.
Last-trade hours are preserved without inventing a date. IV and Greeks remain blank.

**Strikes:** Explicit strikePrice takes precedence when supplied. Otherwise only
unambiguous short or decimal GFG codes are parsed. Five-digit codes are left unresolved
because adjusted strikes can omit their decimal separator. Expirations come from maturityDate.
Contracts with missing strikes remain visible and are excluded from strike-based charts.
"""

ALPACA_NOTES = """
**Instrument:** Standard GGAL-root US options on the Nasdaq-listed Galicia ADR, quoted in USD.
Alpaca option feeds cover the US options market; the display is not limited to a single Nasdaq options venue.
Adjusted contract roots are excluded to avoid mixing different deliverables.

**Volatility and Greeks:** Live values come directly from Alpaca. IV is converted from a decimal to a percentage.
Greeks retain Alpaca's native units and are not scaled to a 100-share contract.
Delta measures underlying-price sensitivity; Gamma measures change in Delta; Theta measures time sensitivity;
Vega measures volatility sensitivity; Rho measures interest-rate sensitivity.

Alpaca uses a Black–Scholes model. Treat these as model estimates: early exercise and dividends can matter for
American options. Missing analytics stay blank, including many illiquid or same-day expiration contracts.
No values are backfilled from last trades. Midpoints require positive, non-crossed bid and ask quotes.

The underlying last trade and individual option quotes may have different timestamps.
Quote quality uses the current wall-clock age, including nights and weekends.
Refresh retrieves a snapshot; this app does not stream ticks.

[Alpaca option chain documentation](https://docs.alpaca.markets/us/reference/optionchain) ·
[Alpaca analytics methodology](https://docs.alpaca.markets/us/docs/market-data-faq)
"""


def chart(frame, y, label, x, spot, demo, key, currency):
    plotted = frame.dropna(subset=[x, y]).copy()
    if plotted.empty:
        st.info(f"No {label.lower()} values available for these filters.")
        return
    plotted = plotted.sort_values(["expiration", "type", x])
    figure = px.line(
        plotted, x=x, y=y, color="type", line_dash="expiration",
        line_group="expiration", markers=True,
        color_discrete_map={"Call": "#60A5FA", "Put": "#FBBF24"},
        labels={"strike": f"Strike ({currency})", "moneyness": "Strike / underlying price",
                y: label, "type": "Option", "expiration": "Expiration"},
        hover_data={"symbol": True, "bid": ":.2f", "ask": ":.2f", "quote_age_min": ":.1f", "quote_status": True},
    )
    if spot is not None:
        figure.add_vline(x=spot if x == "strike" else 1, line_dash="dot", line_color="#94A3B8",
                         annotation_text="Underlying" if x == "strike" else "ATM")
    figure.update_layout(height=400, margin=dict(l=12, r=12, t=40, b=12),
                         legend_title_text="Type / expiration",
                         title="Synthetic demo" if demo else None)
    figure.update_traces(connectgaps=False)
    st.plotly_chart(figure, key=key, config={"displaylogo": False})


def market_header():
    """Market selector and page title. Returns (byma, currency, local_zone)."""
    market = st.sidebar.selectbox("Market", ["BYMA · GGAL shares · ARS", "US · GGAL ADR · USD"], key="market")
    byma = market.startswith("BYMA")
    currency = "ARS" if byma else "USD"
    if st.session_state.get("previous_market") != market:
        for widget_key in ("expirations", "sides", "quality_filter_enabled"):
            st.session_state.pop(widget_key, None)
        st.session_state["previous_market"] = market
    st.caption(f"GRUPO FINANCIERO GALICIA  /  {'BYMA GGAL' if byma else 'GGAL ADR'}  /  {currency}")
    st.title("Galicia options")
    st.write("Explore Galicia calls and puts across strikes and expirations." if byma else
             "Explore implied volatility and option sensitivities across strikes and expirations.")
    return byma, currency, BA if byma else NY


def connection_sidebar(byma):
    """Data-connection sidebar. Returns a dict of the chosen connection settings."""
    with st.sidebar:
        st.header("Data connection")
        demo = st.toggle("Preview with sample data", value=False, key="demo", disabled=byma) and not byma
        key = credential("APCA_API_KEY_ID", "ALPACA_API_KEY")
        secret = credential("APCA_API_SECRET_KEY", "ALPACA_SECRET_KEY")
        if byma:
            st.caption("BYMADATA Open · free · no API key required.")
        if not demo and not byma:
            if key and secret:
                st.caption("Using locally configured credentials.")
            else:
                with st.form("credentials"):
                    st.text_input("Alpaca API key", type="password", key="api_key")
                    st.text_input("Alpaca secret key", type="password", key="secret_key")
                    st.form_submit_button("Connect", type="primary")
                key = st.session_state.get("api_key", "").strip()
                secret = st.session_state.get("secret_key", "").strip()
                st.caption("Entered keys stay in this browser session and are sent only to Alpaca.")
        option_feed = "bymadata open"
        stock_feed = "bymadata"
        if not byma:
            option_feed = st.selectbox("Options feed", ["indicative", "opra"],
                                       format_func=lambda f: "Indicative · free" if f == "indicative" else "OPRA · subscription")
            stock_feed = st.selectbox("Underlying feed", ["iex", "sip"],
                                      format_func=lambda f: "IEX" if f == "iex" else "SIP · subscription")
        horizon = st.selectbox("Expiration search window", [90, 180, 365, 730], index=2,
                               format_func=lambda d: f"Next {d} days")
        refresh = st.button("Refresh data", icon=":material/refresh:", width="stretch")
        st.caption("Requests are cached for 60 seconds. Refresh fetches a new snapshot.")
    return dict(demo=demo, key=key, secret=secret, option_feed=option_feed,
                stock_feed=stock_feed, horizon=horizon, refresh=refresh)


def load_snapshot(byma, conn, today):
    """Fetch the option chain. Returns (frame, spot, fetched_at, spot_warning, byma_items)."""
    demo, refresh, horizon = conn["demo"], conn["refresh"], conn["horizon"]
    if byma:
        st.info("BYMADATA Open: delayed market data (the public service advertises 20 minutes). "
                "Quote timestamps, IV and Greeks are not supplied. Last-trade hours have no date, so quote age is unknown.")
        if refresh:
            fetch_byma.clear()
            clear_funding_cache()
        try:
            with st.spinner("Loading Galicia's BYMA option chain…"):
                items, spot, fetched_at, spot_warning = fetch_byma()
            frame = normalize_byma(items, today, today + timedelta(days=horizon))
        except DataError as exc:
            st.error(str(exc))
            st.stop()
        return frame, spot, fetched_at, spot_warning, items
    if demo:
        st.warning("SAMPLE DATA — All prices, volatility and Greeks below are synthetic examples, not market data.")
        frame, spot = demo_data()
        return frame, spot, datetime.now(timezone.utc), None, None
    if not conn["key"] or not conn["secret"]:
        st.info("Enter your Alpaca API key and secret in the sidebar to load GGAL options, or enable the sample preview.")
        st.caption("An Alpaca connection in another app does not automatically provide API credentials to this local program.")
        st.stop()
    if conn["option_feed"] == "indicative":
        st.info("Indicative feed: quotes are modified and trades are delayed. These are not executable OPRA quotes.")
    if refresh:
        fetch_data.clear()
    try:
        with st.spinner("Loading the GGAL option chain from Alpaca…"):
            snapshots, spot, fetched_at, spot_warning = fetch_data(
                conn["key"], conn["secret"], conn["option_feed"], conn["stock_feed"],
                today, today + timedelta(days=horizon))
        frame = normalize(snapshots)
    except DataError as exc:
        st.error(str(exc))
        st.stop()
    return frame, spot, fetched_at, spot_warning, None


def snapshot_captions(spot, fetched_at, local_zone, byma, demo, option_feed):
    st.caption(f"Snapshot fetched {fetched_at.astimezone(local_zone):%Y-%m-%d %H:%M:%S %Z} · "
               f"Options: {'synthetic' if demo else option_feed.upper()} · Underlying: {spot['feed'].upper()}")
    spot_time = pd.to_datetime(spot.get("timestamp"), utc=True, errors="coerce")
    if pd.notna(spot_time):
        st.caption(f"Underlying last trade: {spot_time.tz_convert(local_zone):%Y-%m-%d %H:%M:%S %Z}")
        if (pd.Timestamp.now(tz="UTC") - spot_time).total_seconds() > 900:
            st.warning("The underlying trade is over 15 minutes old. Moneyness uses that last reported price.")
    elif byma:
        st.caption(f"Underlying last-trade hour: {spot.get('trade_hour') or 'unavailable'} (Buenos Aires; date not supplied). "
                   "Snapshot retrieval time is not the market timestamp.")


def filter_sidebar(frame, currency):
    """Chain-filter sidebar. Returns the filter settings."""
    with st.sidebar:
        st.divider()
        st.header("Chain filters")
        expirations = sorted(frame["expiration"].unique())
        selected_expirations = st.multiselect("Expirations", expirations, default=expirations[:1], key="expirations")
        sides = st.multiselect("Option types", ["Call", "Put"], default=["Call", "Put"], key="sides")
        strikes = frame.strike.dropna()
        low, high = (float(strikes.min()), float(strikes.max())) if not strikes.empty else (0., 0.)
        strike_range = st.slider(f"Strike range ({currency})", low, high, (low, high)) if low < high else (low, high)
        quality_only = st.checkbox("Filter stale or poor quotes", value=False, key="quality_filter_enabled")
        max_age = st.number_input("Maximum quote age (minutes)", min_value=1, max_value=10080, value=60)
        max_spread = st.number_input("Maximum bid–ask spread (% of mid)", min_value=1, max_value=200, value=50)
        st.caption("All available contracts are shown by default. Enable this filter to hide quotes that fail the age, spread or bid/ask checks.")
    return dict(expirations=selected_expirations, sides=sides, strike_range=strike_range,
                quality_only=quality_only, max_age=max_age, max_spread=max_spread)


def apply_filters(frame, flt, price):
    """Returns (selected, matching_count, excluded)."""
    selected = frame[frame.expiration.isin(flt["expirations"]) & frame.type.isin(flt["sides"])
                     & (frame.strike.between(*flt["strike_range"]) | frame.strike.isna())].copy()
    selected["quality_pass"] = quality_mask(selected, flt["max_age"], flt["max_spread"])
    selected["quote_status"] = quote_statuses(selected, flt["max_age"], flt["max_spread"])
    matching_count = len(selected)
    excluded = int((~selected.quality_pass).sum())
    if flt["quality_only"]:
        selected = selected[selected.quality_pass].copy()
    if price:
        selected["moneyness"] = selected.strike / price
    return selected, matching_count, excluded


def summary_metrics(selected, price, currency, byma):
    with st.container(horizontal=True):
        st.metric("GGAL last trade", f"{currency} {price:,.2f}" if price else "Unavailable", border=True)
        st.metric("Contracts shown", str(len(selected)), border=True)
        if byma:
            st.metric("With two-sided prices", str(selected.quote_valid.sum()), border=True)
            st.metric("With last trade", str(selected["last"].notna().sum()), border=True)
        else:
            st.metric("With implied volatility", str(selected.iv_pct.notna().sum()), border=True)
            st.metric("With all five Greeks", str(selected[list(GREEKS)].notna().all(axis=1).sum()), border=True)


def show_available_contracts():
    st.session_state["quality_filter_enabled"] = False


def smile_tab(selected, x, price, demo, calculated, currency):
    st.subheader("Implied volatility by strike")
    st.caption("Calls and puts are separate curves for each expiration. Lines connect available observations; no fitted smile is implied.")
    if not selected.iv_pct.notna().any() and not calculated:
        st.info("Contracts are available in the Option chain tab, but the source supplied no implied volatility for this selection. "
                "Try another expiration. Showing more quotes cannot restore analytics absent from the feed.")
    chart(selected, "iv_pct", "Implied volatility (%)", x, price, demo, "smile", currency)
    missing_iv = int(selected.iv_pct.isna().sum())
    if missing_iv:
        st.caption(f"{missing_iv} contracts have no available implied volatility and are omitted from this chart.")


def greeks_tab(selected, x, price, demo, calculated, byma, currency):
    greek = st.selectbox("Sensitivity", list(GREEKS), format_func=str.capitalize, key="greek")
    st.caption("Calculated BSM values per unit: Theta/day, Vega/volatility point, Rho/rate point." if calculated else
               "BYMADATA Open does not supply Greeks; enable calculated analytics in the sidebar." if byma else
               "Alpaca values as reported, without rescaling or multiplying by contract size.")
    chart(selected, greek, greek.capitalize(), x, price, demo, "greek_chart", currency)
    contract = st.selectbox("Inspect a contract", selected.symbol.tolist())
    row = selected.loc[selected.symbol == contract].iloc[0]
    with st.container(horizontal=True):
        for name in GREEKS:
            st.metric(name.capitalize(), f"{row[name]:.4f}" if pd.notna(row[name]) else "Unavailable", border=True)


def chain_tab(selected, fetched_at, demo, option_feed, currency):
    display = selected.drop(columns=["quote_valid", "moneyness"], errors="ignore").copy()
    display["options_feed"] = "synthetic" if demo else option_feed
    display["fetched_at_utc"] = fetched_at.isoformat()
    columns = {name: st.column_config.NumberColumn(name.capitalize(), format="%.4f") for name in GREEKS}
    display["currency"] = currency
    columns.update({name: st.column_config.NumberColumn(f"{name.capitalize()} ({currency})", format="%.2f")
                    for name in ["strike", "bid", "ask", "mid", "last"]})
    columns.update({"iv_pct": st.column_config.NumberColumn("IV (%)", format="%.2f%%"),
                    "spread_pct": st.column_config.NumberColumn("Spread (%)", format="%.1f%%"),
                    "quote_age_min": st.column_config.NumberColumn("Quote age (min)", format="%.1f"),
                    "quote_time": st.column_config.DatetimeColumn("Quote time (UTC)", format="YYYY-MM-DD HH:mm:ss")})
    st.dataframe(display, hide_index=True, column_config=columns)
    st.download_button("Download filtered chain (CSV)", display.to_csv(index=False).encode("utf-8"),
                       file_name=f"GGAL_{currency}_{'SAMPLE_' if demo else ''}{fetched_at:%Y%m%d_%H%M%S}.csv", mime="text/csv")


def methodology(byma):
    with st.expander("Data and methodology"):
        st.caption("When calculated analytics are enabled, charts use your BSM assumptions. The provider descriptions below apply to reported values.")
        st.markdown(BYMA_NOTES if byma else ALPACA_NOTES)


def run():
    byma, currency, local_zone = market_header()
    today = datetime.now(local_zone).date()
    conn = connection_sidebar(byma)
    demo, option_feed = conn["demo"], conn["option_feed"]

    workspace = st.segmented_control("Workspace", ["Option analytics", "Volatility index"],
                                     default="Option analytics", key="workspace_view")
    if not byma and workspace == "Volatility index":
        adr_workspace(conn["key"], conn["secret"], option_feed, conn["refresh"], demo, conn["horizon"])
        st.stop()

    frame, spot, fetched_at, spot_warning, byma_items = load_snapshot(byma, conn, today)
    if spot_warning:
        st.warning(f"Underlying price unavailable: {spot_warning} Option analytics are still shown.")
    if frame.empty:
        st.info("The source returned no GGAL option contracts in this window. Try a longer window or check the connection.")
        st.stop()

    price = spot["price"]
    if byma and workspace == "Volatility index":
        st.caption(f"Retrieved {fetched_at.astimezone(local_zone):%Y-%m-%d %H:%M:%S %Z}; quote dates unavailable.")
        volatility_panel(normalize_byma(byma_items, now=fetched_at), fetched_at)
        st.stop()
    frame = model_controls(frame, price, today, currency, asof=fetched_at)
    calculated = "analytics_source" in frame.columns
    snapshot_captions(spot, fetched_at, local_zone, byma, demo, option_feed)

    flt = filter_sidebar(frame, currency)
    selected, matching_count, excluded = apply_filters(frame, flt, price)
    summary_metrics(selected, price, currency, byma)
    if excluded:
        st.warning(f"{excluded} contracts {'hidden because their quotes fail' if flt['quality_only'] else 'shown with quotes that fail'} "
                   "the quality checks. Quote status in the table and chart tooltips explains why. "
                   "Stale quotes may be from an earlier trading session.")
    if selected.empty:
        if flt["quality_only"] and matching_count:
            st.info(f"The source returned {matching_count} matching contracts, but all failed the quote quality checks.")
            st.button("Show available contracts", on_click=show_available_contracts, type="primary", key="show_available")
        else:
            st.info("No contracts match these filters. Select an expiration and option type, or widen the strike range.")
        st.stop()

    if byma and selected.strike.isna().any():
        st.warning(f"{selected.strike.isna().sum()} contracts have ambiguous strike codes. They remain in the table "
                   "regardless of the strike filter, with strike blank. Five-digit codes can hide adjusted decimals; "
                   "a verified instrument reference is needed to resolve them.")
    x_options = ["strike", "moneyness"] if price else ["strike"]
    x = st.selectbox("Chart horizontal axis", x_options,
                     format_func=lambda value: f"Strike ({currency})" if value == "strike" else "Moneyness (strike / price)")
    if byma:
        tab_chain, tab_smile, tab_greeks, tab_payoff = st.tabs(["Option chain", "Volatility smile", "Greeks", "Payoff builder"])
    else:
        tab_smile, tab_greeks, tab_chain, tab_payoff = st.tabs(["Volatility smile", "Greeks", "Option chain", "Payoff builder"])
    with tab_smile:
        smile_tab(selected, x, price, demo, calculated, currency)
    with tab_greeks:
        greeks_tab(selected, x, price, demo, calculated, byma, currency)
    with tab_chain:
        chain_tab(selected, fetched_at, demo, option_feed, currency)
    with tab_payoff:
        payoff_builder(frame, price, currency)
    methodology(byma)
