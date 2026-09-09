"""Dashboard controls for calculated analytics and expiration strategies."""
from datetime import date
import math

import pandas as pd
import plotly.express as px
import streamlit as st

from option_analytics import implied_volatility, calculate_greeks, build_payoff
from funding_ui import ars_rate_controls


def model_controls(frame, spot, today, currency, asof=None):
    funding_audit = None
    with st.sidebar.expander("Calculate IV and Greeks", expanded=True):
        enabled = st.checkbox("Use calculated analytics", key=f"calculate_{currency}")
        st.caption("European Black–Scholes–Merton estimates; early exercise is not modeled.")
        rate = None
        if currency != 'ARS' or not enabled:
            rate = st.number_input("Annual continuous rate (%)", value=0., min_value=-99., max_value=500., key=f"rate_{currency}") / 100
        dividend = st.number_input("Annual dividend yield (%)", value=0., min_value=0., max_value=100., key=f"yield_{currency}") / 100
        basis = st.selectbox("Premium used for IV", ["mid", "last", "bid", "ask"], key=f"basis_{currency}")
        model_spot = st.number_input(f"Model underlying price ({currency})", min_value=0.01,
                                     value=float(spot) if spot and math.isfinite(spot) and spot > 0 else 100., key=f"spot_{currency}")
        st.caption("Review rate, yield and underlying price. Defaults are assumptions. Time uses calendar days / 365; same-day expiries are excluded. Last trades may be stale.")
    if not enabled:
        return frame
    if currency == 'ARS':
        if asof is None:
            raise ValueError('ARS funding requires the option snapshot valuation time')
        with st.expander('ARS funding rates for IV and Greeks', expanded=True):
            tenors = {e:(date.fromisoformat(str(e))-today).days for e in sorted(frame.expiration.unique())}
            rates, funding_audit = ars_rate_controls(tenors, asof, key='model_funding')
    else:
        rates = {e:rate for e in frame.expiration.unique()}
    result = frame.copy()
    names = ["iv_pct", "delta", "gamma", "theta", "vega", "rho"]
    for name in names:
        result[f"reported_{name}"] = result[name]
        result[name] = float("nan")
    result["analytics_source"] = "Calculated European BSM"
    result["model_spot"] = model_spot
    result["model_rate"] = result.expiration.map(rates)
    result["model_rate_source"] = result.expiration.map(
        {e:m['source'] for e,m in funding_audit['matches'].items()}) if funding_audit else 'User-entered continuous USD scenario'
    result["model_rate_fallback"] = result.expiration.map(
        {e:m['fallback'] for e,m in funding_audit['matches'].items()}) if funding_audit else False
    result["model_rate_status"] = result.expiration.map(
        {e:m['reason'] for e,m in funding_audit['matches'].items()}) if funding_audit else 'Manual scenario'
    result["model_yield"] = dividend
    result["model_valuation_date"] = today.isoformat()
    result["model_premium_basis"] = basis
    result["model_status"] = ""
    for index, row in result.iterrows():
        try:
            rate = rates.get(row.expiration)
            if rate is None:
                raise ValueError('Funding rate unavailable: '+funding_audit['matches'][row.expiration]['reason'])
            time = (date.fromisoformat(str(row.expiration))-today).days/365
            iv = implied_volatility(float(row[basis]), model_spot, float(row.strike), time, rate, row.type, dividend)
            result.at[index, "iv_pct"] = 100*iv
            if iv == 0:
                result.at[index, "model_status"] = "Zero IV boundary; Greeks undefined"
                continue
            greeks = calculate_greeks(model_spot, float(row.strike), time, rate, iv, row.type, dividend)
            for name, value in greeks.items():
                result.at[index, name] = value
            result.at[index, "model_status"] = "Calculated"
        except (ValueError, TypeError, OverflowError) as exc:
            result.at[index, "model_status"] = str(exc)
    st.caption("Calculated European BSM analytics · Theta/day · Vega/1 volatility point · Rho/1 rate point. "
               "Original provider values are preserved in reported_* CSV columns. See model_status for missing estimates.")
    return result


def payoff_builder(frame, spot, currency):
    st.subheader("Payoff builder")
    st.caption("Expiration P/L including entry premiums. Positive quantity = long; negative = short. "
               "Choose the units per contract explicitly. All option legs share the selected expiry; fees, financing and dividends are excluded.")
    expiry = st.selectbox("Payoff expiration", sorted(frame.expiration.unique()), key=f"pay_expiry_{currency}")
    contracts = frame[(frame.expiration == expiry) & frame.strike.notna()]
    if contracts.empty:
        st.info("No resolved strikes for this expiration.")
        return
    state_key = f"legs_{currency}_{expiry}"
    if state_key not in st.session_state:
        st.session_state[state_key] = []
    with st.form(f"add_leg_{currency}_{expiry}"):
        symbol = st.selectbox("Add contract or shares", contracts.symbol.tolist()+["Underlying shares"])
        quantity = st.number_input("Signed quantity", value=1, step=1)
        multiplier = st.number_input("Units per contract (shares: use 1)", min_value=1., value=1.)
        premium = st.number_input(f"Entry premium / share price ({currency} per unit)", min_value=0., value=0.)
        st.caption("Enter your actual entry premium above; chain prices are available in the Option chain tab.")
        add = st.form_submit_button("Add leg")
    if add:
        if quantity == 0:
            st.warning("Quantity must be nonzero.")
        else:
            row = contracts.loc[contracts.symbol == symbol].iloc[0] if symbol != "Underlying shares" else None
            st.session_state[state_key].append(dict(symbol=symbol, type=row.type.lower() if row is not None else "stock",
                strike=float(row.strike) if row is not None else 0., premium=premium, quantity=quantity,
                multiplier=multiplier, expiration=expiry))
    if st.button("Clear legs", key=f"clear_{state_key}"):
        st.session_state[state_key] = []
    legs = st.session_state[state_key]
    if not legs:
        st.info("Add a call, put or shares to start building a strategy.")
        return
    st.dataframe(pd.DataFrame(legs), hide_index=True)
    remove = st.selectbox("Leg to remove", list(range(len(legs))), format_func=lambda i: f"{i+1}: {legs[i]['symbol']}", key=f"remove_select_{state_key}")
    if st.button("Remove leg", key=f"remove_{state_key}"):
        legs.pop(remove)
        st.rerun()
    center = float(spot) if spot and math.isfinite(spot) and spot > 0 else float(contracts.strike.median())
    low = st.number_input(f"Minimum underlying at expiry ({currency})", min_value=0., value=0., key=f"pay_low_{currency}")
    high = st.number_input(f"Maximum underlying at expiry ({currency})", min_value=0.01, value=center*2, key=f"pay_high_{currency}")
    if high <= low:
        st.warning("Maximum price must exceed minimum price.")
        return
    prices = sorted(set([low+(high-low)*i/400 for i in range(401)]+[leg["strike"] for leg in legs if low <= leg["strike"] <= high]))
    values = build_payoff(prices, legs)
    output = pd.DataFrame({"Underlying at expiry": prices, "Total P/L": values})
    figure = px.line(output, x="Underlying at expiry", y="Total P/L", labels={"Underlying at expiry": f"Underlying at expiry ({currency})", "Total P/L": f"Total P/L ({currency})"})
    figure.add_hline(y=0, line_dash="dot")
    st.plotly_chart(figure, key=f"pay_chart_{currency}")
    st.caption(f"Within plotted range: minimum P/L {min(values):,.2f}; maximum P/L {max(values):,.2f} {currency}. These are not global risk limits.")
    st.download_button("Download payoff (CSV)", output.to_csv(index=False), file_name=f"GGAL_{currency}_payoff.csv", mime="text/csv")
