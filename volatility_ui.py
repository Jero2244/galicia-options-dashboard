"""Galicia volatility research view, separate from chain display filters."""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from volatility_index import assess, expiry_minutes, liquidity_summary
from adr_volatility import assess_adr
from funding_ui import ars_rate_controls


def volatility_panel(frame, fetched_at, *, market='byma', asof=None, feed=None, metadata=None):
    adr = market == 'adr'
    currency = 'USD' if adr else 'ARS'
    prefix = 'adr_' if adr else 'vol_'
    asof = asof if asof is not None else fetched_at
    st.subheader("Galicia ADR volatility index · research" if adr else "Galicia volatility index · research")
    st.write(f"A VIX-style option-strip calculation for GGAL {'ADR' if adr else 'shares'} in {currency}. "
             "The 30-day measure needs usable expirations on both sides of 30 days.")
    st.caption("Uses the full retrieved chain, independently of option-chain filters and calculated IV. "
               "No last trades, previous closes or fitted prices enter the variance strip.")
    summary = liquidity_summary(frame)
    with st.container(horizontal=True):
        st.metric("Contracts supplied", len(frame), border=True)
        st.metric("Two-sided prices", int(summary.two_sided.sum()), border=True)
        st.metric("Expirations", frame.expiration.nunique(), border=True)
        st.metric("Validated 30-day index", "Unavailable", border=True)
    if adr:
        st.warning("Research only. GGAL ADR options allow early exercise. USD rates are explicit scenarios; "
                   "the Treasury curve and American-exercise adjustments are not connected. "
                   "Indicative prices are modified by Alpaca. No validated index is published.")
    else:
        st.warning("Research only. BYMA options allow early exercise, quote timestamps are missing, "
               "and ARS funding uses explicitly labeled research inputs. These limits prevent publication "
               "of a validated index, even when the arithmetic returns a value.")
    st.dataframe(summary, hide_index=True)
    chart = summary.melt(id_vars=['expiration', 'type'], value_vars=['contracts', 'two_sided', 'traded'],
                         var_name='Measure', value_name='Contracts')
    chart['Series'] = chart['expiration'] + ' · ' + chart['type']
    fig = px.bar(chart, x='Series', y='Contracts', color='Measure', barmode='group',
                 labels={'contracts': 'Listed', 'two_sided': 'Two-sided', 'traded': 'With a trade'})
    st.plotly_chart(fig, key='vol_liquidity', config={'displaylogo': False})
    funding_audit = None
    with st.expander("Calculation assumptions", expanded=True):
        if not adr:
            tenors = {e:expiry_minutes(e, asof)/1440 for e in sorted(frame.expiration.unique())}
            rates, funding_audit = ars_rate_controls(tenors, asof, key='vol_funding', manual_key='vol_flat_rate')
        else:
            flat_rate = st.number_input(f"Illustrative continuous {currency} annual rate (%)", min_value=-20.,
                                    max_value=500., value=0., step=0.5 if adr else 5., key=prefix+'flat_rate')
            st.caption("Zero is a scenario, not today's risk-free rate. Enter a continuous annual rate; "
                   "a TNA quote cannot be substituted without its day-count and compounding conversion.")
            rates = {e: flat_rate/100 for e in sorted(frame.expiration.unique())}
            if st.checkbox("Use separate rates for each expiration", key=prefix+'separate_rates'):
                for e in rates:
                    rates[e] = st.number_input(f"{e} continuous rate (%)", min_value=-20., max_value=500.,
                                           value=float(flat_rate), key=f'{prefix}rate_{e}')/100
        partial = False
        if adr:
            max_age = st.number_input("Maximum quote age at valuation (minutes)", min_value=1,
                                      max_value=120, value=30, key='adr_max_age')
            st.caption("Stale, undated and future quotes are excluded before computing the forward. "
                       "Failed expirations remain in maturity selection. Time runs from the recorded quote "
                       "valuation to 16:00 New York on the OCC expiry date, using 525,600 minutes/year. "
                       "This research cutoff does not model early-close expirations or an exercise deadline.")
        else:
            partial = st.checkbox("Calculate diagnostics using resolved strikes only", value=False, key='vol_partial')
            st.caption("This optional diagnostic omits unknown strikes and cannot validate the complete wing order "
                   "or tail coverage. A complete-strip calculation remains unavailable for those expiries.")
            st.caption("Time convention: minutes from retrieval to 15:30 Buenos Aires on maturityDate, divided by "
                   "525,600. The cutoff is a research convention based on the last trading time. "
                   "Retrieval time is not the quote timestamp; the advertised delay is not subtracted as an exact age.")
    result = (assess_adr(frame, asof, rates, feed, max_age) if adr
              else assess(frame, asof, rates, partial, funding_audit['matches']))
    cm = result['constant_30d']
    if cm['value'] is None:
        st.info("30-day research calculation unavailable: " + cm['reason'])
    else:
        st.metric("30-day research arithmetic (unvalidated)", f"{cm['value']:.2f}")
    if cm['expirations']:
        st.caption("Required expirations: " + ' and '.join(cm['expirations']) +
                   ". Failed terms are retained; the calculator never skips them to use a later liquid expiry.")
    st.subheader("Results by expiration")
    table = pd.DataFrame([dict(expiration=t['expiration'], days=t['minutes']/1440,
                              research_vol_pct=t['value'], status=t['reason'],
                              continuous_rate_pct=100*t['rate'] if t['rate'] is not None else None,
                              rate_source=t.get('funding', {}).get('source', 'User-entered USD scenario'),
                              forward=t['forward'], k0=t['k0'], puts=t['put_count'], calls=t['call_count'],
                              fixed_forward_bid_sensitivity=t.get('bid_sensitivity'),
                              fixed_forward_ask_sensitivity=t.get('ask_sensitivity')) for t in result['terms']])
    st.dataframe(table, hide_index=True)
    if adr:
        valid_terms = table.dropna(subset=['research_vol_pct'])
        if not valid_terms.empty:
            fig = px.line(valid_terms, x='days', y='research_vol_pct', markers=True,
                          hover_data=['expiration'], labels={'days': 'Days to expiration',
                          'research_vol_pct': 'Annualized research volatility (%)'})
            st.plotly_chart(fig, key='adr_term_structure', config={'displaylogo': False})
    st.caption("Values are annualized volatility points for each expiry's own remaining tenor. "
               "Bid/ask sensitivities use a fixed midpoint forward and basket; they are not executable bounds "
               "or statistical confidence intervals. A 39-day result is not a 30-day index.")
    sensitivity_rows = []
    if not adr:
        with st.expander('Funding-rate sensitivity', expanded=True):
            shock = st.number_input('Continuous-rate shock (percentage points)', min_value=0., max_value=100.,
                                    value=5., key='vol_funding_shock')/100
            scenarios = {'Selected rates': rates,
                         'Rates lower': {e:r-shock if r is not None else None for e,r in rates.items()},
                         'Rates higher': {e:r+shock if r is not None else None for e,r in rates.items()},
                         **funding_audit['scenarios']}
            for name, scenario_rates in scenarios.items():
                scenario = result if name == 'Selected rates' else assess(frame, asof, scenario_rates, partial)
                for term in scenario['terms']:
                    baseline = next(t['value'] for t in result['terms'] if t['expiration']==term['expiration'])
                    sensitivity_rows.append(dict(scenario=name, expiration=term['expiration'],
                        continuous_rate_pct=100*term['rate'] if term['rate'] is not None else None,
                        research_vol_pct=term['value'], change_vol_points=(term['value']-baseline)
                        if term['value'] is not None and baseline is not None else None, status=term['reason']))
                value = scenario['constant_30d']['value']
                sensitivity_rows.append(dict(scenario=name, expiration='30-day', continuous_rate_pct=None,
                    research_vol_pct=value, change_vol_points=value-cm['value']
                    if value is not None and cm['value'] is not None else None, status=scenario['constant_30d']['reason']))
            st.dataframe(pd.DataFrame(sensitivity_rows), hide_index=True)
            st.caption('Option quotes are held fixed; the forward and selected strikes are recalculated for each rate '
                       'scenario. These are sensitivity comparisons, not confidence intervals. Missing rates stay missing.')
    for t in result['terms']:
        with st.expander(f"{t['expiration']} · constituents and quality checks"):
            for reason in t['publication_blockers'] + t['warnings']:
                st.write('• ' + reason)
            if t['contributions']:
                contributions = pd.DataFrame(t['contributions'])
                st.dataframe(contributions, hide_index=True)
                fig = px.bar(contributions, x='strike', y='weight_pct', color='type',
                             labels={'strike': f'Strike ({currency})', 'weight_pct': 'Share of gross variance (%)'},
                             hover_data=['symbols', 'spread_pct', 'min_size'])
                st.plotly_chart(fig, key='weights_'+t['expiration'], config={'displaylogo': False})
                st.download_button("Download constituents (CSV)", contributions.to_csv(index=False),
                                   file_name=f'GGAL_{currency}_{t["expiration"]}_constituents.csv',
                                   mime='text/csv', key=prefix+'csv_'+t['expiration'])
    with st.expander("Method and differences from VIX"):
        st.latex(r"F=K_*+e^{rT}(C(K_*)-P(K_*))")
        st.latex(r"\sigma^2(T)=\frac{2e^{rT}}{T}\sum_i\frac{\Delta K_i}{K_i^2}Q(K_i)-\frac{1}{T}\left(\frac{F}{K_0}-1\right)^2")
        st.write("Select the valid call/put pair with the smallest midpoint difference (lowest strike breaks ties). "
                 "K0 is the listed strike at or immediately below F. Use puts below K0, calls above, and the "
                 "average call/put midpoint at K0. Stop each wing after two consecutive zero bid/ask quotes. "
                 "Interpolate total variance between expirations, then annualize and take the square root.")
        st.write("Local safeguards differ from Cboe: positive ATM/K0 quotes, rejection of crossed wing quotes, "
                 "no maturity extrapolation, explicit unresolved-strike failures, and no republishing stale values. "
                 "Five strikes per wing, 20% weighted spread, 25% concentration and 10% strike-gap checks are "
                 "provisional research thresholds, not Cboe rules or proof of tradability. Cboe's real-time "
                 "filtering and settlement auction are not reproduced by this delayed snapshot tool.")
        st.markdown(("[Alpaca options data](https://docs.alpaca.markets/us/docs/historical-option-data) · " if adr else
                    "[BYMA option rules](https://www.byma.com.ar/productos/productos-financieros/opciones) · ") +
                    "[Cboe mathematics](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Volatility_Index_Mathematics_Methodology.pdf)")
        st.caption(f"This measures one Argentine company's {currency} option prices; it is not an Argentine equity-market fear gauge. "
                   "American exercise, dividends, currency exposure and incomplete tails affect interpretation.")
    payload = dict(result, retrieved_at=fetched_at.isoformat(), rate_source=funding_audit['source'] if funding_audit else 'User-entered scenarios',
                   funding_audit=funding_audit, funding_sensitivity=sensitivity_rows,
                   liquidity=json.loads(summary.to_json(orient='records')), source_metadata=metadata or {})
    payload = json.loads(json.dumps(payload, default=str), parse_constant=lambda _: None)
    st.download_button("Download research audit (JSON)", json.dumps(payload, indent=2, allow_nan=False),
                       file_name=f'GGAL_{currency}_volatility_audit_{asof:%Y%m%d_%H%M%S}.json', mime='application/json')
    report = Path(__file__).with_name('GALICIA_ADR_VOLATILITY_RESEARCH.md' if adr else 'GALICIA_VOLATILITY_RESEARCH.md')
    if report.exists():
        st.download_button("Download methodology and feasibility report", report.read_text(encoding='utf-8'),
                           file_name=report.name, mime='text/markdown')
