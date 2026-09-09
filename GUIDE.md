# Galicia options · Setup & usage guide

[← Project overview](README.md)

The complete operating guide: installation, data connections, controls, model
conventions, research limitations and validation.

**On this page** · [Run locally](#run-in-your-py4fi-environment) ·
[BYMA connection](#free-byma-connection) · [Alpaca connection](#connect-to-alpaca-us-adr-market) ·
[Analytics & payoff builder](#features) · [Interpretation](#interpretation) ·
[Volatility research](#galicia-volatility-research) · [ARS funding](#ars-funding-curve) ·
[Validation](#validation)

---

Galicia option chains for BYMA local shares (ARS, free BYMADATA Open, default)
and the US-listed GGAL ADR (USD, Alpaca).

## Galicia volatility research

For the ADR, select **US · GGAL ADR · USD > Volatility index**. The saved Alpaca
snapshot replays offline at its September 4, 2026 quote time, with New York expiry
timing, per-expiry USD rate scenarios, quote-age checks and constituent exports.
The first 30-day calculation is **46.12** using modified indicative quotes and
an illustrative zero rate. OPRA access was denied, and very wide spreads make
this a research diagnostic. Historical trade bars were retrieved separately and
are never substituted for bid/ask quotes.
See [ADR methodology and recorded results](GALICIA_ADR_VOLATILITY_RESEARCH.md).

```powershell
python research/adr_research.py audit research/adr_snapshot_20260907_indicative.json
```

Select BYMA, then **Workspace > Volatility index**. The new view evaluates the full
retrieved chain independently of chain filters, shows liquidity by expiry, and
implements VIX-style forward/strike selection and total-variance interpolation.
It exports the audit and constituent weights. No last-trade fallback is used.

The September 7 snapshot does not support a 30-day index: September has no usable
two-sided prices and December no valid call/put pair. October supports a partial
known-strike diagnostic (43.85% annualized under an illustrative zero continuous
rate), with unresolved tails, undated quotes and American-exercise limitations.
The default complete-strip mode fails on unresolved strikes; partial diagnostics
are explicitly opt-in. ARS rates now default to the caución funding controls;
manual expiry-specific scenarios remain available. No validated index is published.

## ARS funding curve

The BYMA volatility view and calculated IV/Greeks now support a caución curve
with expiry matching, liquidity checks, log-discount interpolation, rate
sensitivity and downloadable source audits. **Funding quality and conventions**
contains the controls. Strict mode rejects the public feed's undated trades;
**Allow undated caución observations for research** enables explicitly labeled
diagnostics. Unsupported expiries stay unavailable, with no zero or stale-data
fallback. Use **Refresh data** to refresh options and funding together.

An optional Bonistas LECAP reported-yield comparison and separately enabled
fallback retain their sovereign-proxy labels. They do not constitute verified
Treasury cash-flow bootstrapping. See [funding methodology and usage](ARS_FUNDING_METHODOLOGY.md).

See [methodology, evidence and feasibility](GALICIA_VOLATILITY_RESEARCH.md).
The implementation reproduces the uploaded Cboe example (13.927842 -> 13.93).
Run `python research/audit_galicia.py research/byma_snapshot_20260907.json`
to reproduce the recorded audit without network requests.

## Free BYMA connection

Select **BYMA · GGAL shares · ARS**. No credentials are needed. The app retrieves the
public options panel and the GGAL 24hs underlying quote directly from BYMADATA Open.
Calls, puts, expirations, bid/ask, last trade, volume, open interest and CSV export
are available. Filters initially show the nearest expiration; select more to view
the rest of the chain. Requests are cached for 60 seconds and spaced by at least
one second within each fetch. Refresh requests a new snapshot.

BYMA describes its open service as delayed by 20 minutes. Actual age cannot be
verified from this response: it supplies trade hours without dates and no quote
timestamps. Retrieval time is shown separately. The optional quote-age filter
therefore excludes these undated quotes; leave it off to see them.

The free response supplies **no IV or Greeks**. Enable **Use calculated analytics**
in the sidebar to estimate them with explicit model assumptions. Zero trades stay blank; previous
close remains separate. Open interest is reported verbatim (including zeros),
without assuming its completeness. Prices and premiums are in ARS, without
contract-size multiplication. Only ARS / 24hs local GGAL option rows are included.
Here "24hs" is the public feed's code 2 label: current BYMA rules settle option
premiums T+0 and exercises T+1; the provider code does not override those rules.

Explicit strikePrice is used when available. Otherwise short or decimal GFG
codes are parsed. Five-digit strike codes can hide adjusted decimals; they remain
in the table with an unresolved strike and are not subject to the strike slider.
No scale is inferred from the underlying price. Expiry uses the provider's date.

The interface behind the public website is undocumented and may change. HTTPS
certificate verification stays enabled. A failed request produces an error;
it never silently falls back to a synthetic or old snapshot.

See [data source comparison and paid alternatives](DATA_SOURCES.md).

## Run in your py4fi environment

Double-click `start_dashboard.bat`, or run in a Conda terminal from this folder:

```powershell
conda activate py4fi
python -m streamlit run app.py
```

Open http://localhost:8501. The launcher uses the existing `py4fi` environment and opens a browser.
For a fresh installation, run `python -m pip install -r requirements.txt` inside `py4fi`.

## Connect to Alpaca (US ADR market)

Enter your API key and secret in the dashboard's password fields. They are retained only in the Streamlit session.
Alternatively copy `.env.example` to `.env` and fill in `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY` locally.
The same names can be set in environment variables or `.streamlit/secrets.toml`.
`ALPACA_API_KEY` and `ALPACA_SECRET_KEY` environment variable aliases are also accepted.
Never commit or share those files. No account or order endpoints are called.

A connection inside another app does not automatically expose credentials to this local Python program.
The sample-data toggle provides an explicitly synthetic preview without credentials; it never substitutes for failed live requests.

## Features

- Optional calculated IV and five Greeks for either market. Review the underlying
  price, dividend yield and premium source in the sidebar, plus the ARS funding
  controls above the chain. USD and manual ARS rates are continuous annual inputs.
  Manual rate/yield defaults of zero are assumptions, not observed market rates.
- Payoff builder tab: add/remove long or short calls, puts and shares for a single
  expiration, set entry premiums and explicit contract multipliers, chart P/L and export CSV.

Calculated analytics use European Black–Scholes–Merton, with calendar days/365.
They do not model American early exercise. IV is annualized percent; Delta and Gamma
are per underlying unit, Theta per day, Vega per one volatility percentage point,
and Rho per one rate percentage point. Same-day/expired contracts, missing inputs
and prices outside model bounds produce a reason in `model_status`. Zero-IV boundary
prices have no calculated Greeks. Provider values remain in `reported_*` columns
when calculations are enabled. Model inputs are included in the chain CSV.
The payoff chart includes undiscounted premiums and excludes fees, financing and
dividends. Displayed minimum/maximum P/L apply only to the chosen price range.

- Calls and puts, one or multiple expirations, strike and moneyness axes.
- Implied-volatility smiles and charts for Delta, Gamma, Theta, Vega and Rho.
- Contract details, bid/ask/mid/last, timestamps and CSV export.
- Adjustable quote-age and relative bid–ask spread filters.
- Explicit refresh with a 60-second session cache; all chain pages are retrieved.
- OPRA and indicative options feeds; IEX and SIP underlying feeds.

## Interpretation

The US market selection displays Nasdaq-listed GGAL ADR options, separate from the BYMA selection.
Alpaca is not a Nasdaq-only venue feed.
Adjusted roots such as GGAL1 are excluded. Prices are USD per underlying unit.
In provider mode, IV is displayed as a percent; Greeks are unchanged Alpaca values, without contract-size scaling.
The app does not infer or rescale Alpaca's Theta/Vega/Rho time or percentage conventions.
Alpaca uses Black–Scholes; early exercise and dividends can affect American-option estimates.
Missing or nonfinite provider analytics remain blank in provider mode. Calculated mode is explicitly labeled.
Contracts are shown by default, with quote-status labels for zero-bid, crossed, stale or wide quotes.
Enable the optional quality filter to hide those contracts. If it hides everything, use "Show available contracts".
Outside trading hours, increase maximum quote age or disable filtering to see the last available observations.
The last underlying trade can be stale, especially with IEX; its timestamp is displayed separately.

Alpaca's indicative feed modifies quotes and delays trades. OPRA and SIP require the relevant data entitlements.
See [option chain API](https://docs.alpaca.markets/us/reference/optionchain) and
[Alpaca's explanation of missing Greeks](https://docs.alpaca.markets/us/docs/market-data-faq).

## Validation

```powershell
conda run -n py4fi python -m unittest discover -s tests -v
```

Tests cover chain pagination, request failures, missing analytics, option-symbol parsing,
quote quality, and dashboard filtering using synthetic fixtures and mocked API responses.
Live US data requires local Alpaca credentials and suitable entitlements. BYMA needs no key.
BYMA tests cover a recorded public response from September 4, 2026 (73 contracts),
ambiguous strikes, missing dates, currency/settlement selection, service errors,
and switching markets without carrying over incompatible filters.

## README screenshots

The images in `docs/images/` were captured from the running application on
September 9, 2026, with **US · GGAL ADR · USD** and **Preview with sample data**
enabled. They show the synthetic provider preview; **Use calculated analytics**
was disabled. These images document the interface, not historical market prices.

The payoff illustration uses two hypothetical call legs expiring September 24,
2026: long one call at strike 45 with an entry premium of 2.10 USD per unit, and
short one call at strike 55 with an entry premium of 0.80 USD per unit. Both use
100 units per contract, with an underlying-price plot range of 0–90 USD. The
premiums were entered for illustration and are not quoted execution prices.
