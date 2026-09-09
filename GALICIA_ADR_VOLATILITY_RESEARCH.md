# Galicia ADR volatility research

The GGAL ADR calculation is available in **US · GGAL ADR · USD > Volatility index**.
Select **Saved research snapshot** to reproduce the September 4 observation without
network access. Select **Latest Alpaca quotes** to request new data with the existing
project credentials. The source feed, quote valuation time and retrieval time are
displayed separately. A historical quote is never labeled as today's index.

## First recorded result

On September 7, 2026, the project's Alpaca credentials returned 92 standard GGAL
contracts through the indicative chain endpoint. OPRA access returned HTTP 403.
The saved quotes range from **September 4, 15:55:05.338020356 to
15:59:59.556050695 America/New_York**. Their latest timestamp is the valuation
anchor. All 92 quote timestamps fall within the default 30-minute tolerance.

The resulting **30-day research value is 46.12177157 volatility points**, using
an explicitly illustrative **0% continuously compounded annual USD rate**.
This is an annualized percentage, not the expected percentage move over 30 days.
It uses modified indicative premiums and is not a validated or official index.

| Expiry | Days remaining | Contracts | Positive two-sided quotes | OTM puts / calls selected | Term volatility | Forward | K0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-18 | 14 | 44 | 28 | 1 / 1 | 35.0924% | 44.170 | 44 |
| 2026-10-16 | 42 | 48 | 41 | 8 / 8 | 48.4887% | 44.235 | 44 |

There is also one averaged call/put contribution at K0 in each term. The total
variance interpolation weights are 3/7 and 4/7. After accounting for each tenor,
the annualized 30-day variance equals 0.2 times September variance plus 0.8 times
October variance. Volatility percentages themselves are not interpolated.

Liquidity is the main limitation. September's contribution-weighted spread is
114.56% of midpoint and one strike supplies 49.71% of gross variance. October's
weighted spread is 98.84%; its largest strike gap exceeds 10% of the forward.
Both wings stop after the required two zero quotes; a stop does not establish
that these indicative prices form a reliable market benchmark.

| Illustrative continuous USD rate | 30-day research value |
|---:|---:|
| 0% | 46.1218 |
| 3% | 46.1952 |
| 4% | 46.2197 |
| 5% | 46.2442 |

These rates are sensitivity scenarios, not observed September 4 Treasury yields.

## Cboe arithmetic and ADR conventions

The shared engine follows the supplied
`Volatility_Index_Methodology_Cboe_Volatility_Index.pdf` and its worked example:

1. At each expiration, find the usable call/put pair with the smallest absolute
   midpoint difference; the lowest strike breaks ties. Infer
   `F = K* + exp(r*T) * (C(K*) - P(K*))`.
2. Set K0 to the listed strike at or immediately below F. Use out-of-the-money
   puts below K0, calls above it, and the average of call/put midpoints at K0.
3. Move outward on each wing, skipping zero prices and stopping at two
   consecutive zero bid/ask quotes. Missing quotes are excluded and never
   converted to zero bids. Crossed wing quotes fail the term.
4. Compute adjacent-strike delta K, using the half-distance between neighbors
   internally and one-sided distances at the edges. Calculate
   `variance = 2*exp(r*T)/T * sum(deltaK * Q(K)/K^2) - (F/K0 - 1)^2/T`.
5. Select the nearest supplied expirations bracketing 30 days, interpolate total
   variance, annualize and return `100*sqrt(variance30)`.

The original PDF example still reproduces **13.927842, rounding to 13.93**.
The formula is not an average of Alpaca's per-contract IVs and needs no underlying
last trade, Black-Scholes fitted price, Greek, volume or contract multiplier.
Prices and strikes are USD per ADR unit. GGAL's US ADS listing is on Nasdaq;
options market data should not be interpreted as a Nasdaq-only venue feed.
[Nasdaq GGAL listing](https://www.nasdaq.com/market-activity/stocks/ggal/advanced-charting).

For ADR research, expiry is **16:00 America/New_York on the OCC symbol date**.
Time is floored to whole calendar minutes and divided by 525,600. UTC subtraction
correctly includes daylight-saving transitions. This is a research trading cutoff;
early-close expirations and exercise deadlines are not modeled.

The implementation deliberately differs from an official VIX calculation:

- GGAL equity options replace SPX/SPXW options. Standard equity options are
  American style and can deliver ADRs; adjusted roots such as GGAL1 are excluded,
  but deliverables are not independently checked against corporate-action records.
  Early exercise can distort the parity-derived forward and strip interpretation.
  [OCC specifications](https://www.theocc.com/clearance-and-settlement/clearing/equity-options-product-specifications).
- The supplied GGAL expirations replace the SPX eligible series universe. The
  research tool refuses maturity extrapolation and cannot skip a failed nearest
  term to use a later liquid term. Exact 30-day maturities use that term alone.
- Quotes older than the chosen tolerance, missing timestamps and future quotes
  are nulled before forward and strike selection. Strikes and expiries remain
  present, and exclusion counts are recorded. This tolerance is a local policy,
  not Cboe's real-time filtering algorithm.
- Positive uncrossed ATM/K0 pairs are required. Provisional checks flag fewer
  than five OTM strikes per wing, over 20% weighted spread, over 25% single-strike
  concentration and over 10% strike gaps. They are diagnostic thresholds.
- USD rates are entered per expiry or as a flat scenario. Cboe's Treasury CMT
  bounded cubic spline and bond-equivalent-to-continuous-rate conversion are
  not implemented. No automatic dividend or early-exercise adjustment is made.
- Cboe's real-time filters, settlement auction and stale-value republication are
  not reproduced. A finite result always remains labeled research-only.

See [Cboe mathematics](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Volatility_Index_Mathematics_Methodology.pdf)
for the official calculation, rate conversion and filtering rules.

## Historical data actually obtained

The quotes are prior-session observations returned by a latest-chain request.
They are not a historical chain queried for an arbitrary date. The documented
Alpaca options client exposes historical bars/trades and latest quotes/snapshots,
so a historical bid/ask backtest requires saved snapshots or another quote archive.
[Alpaca options client](https://alpaca.markets/sdks/python/api_reference/data/option/historical.html).

The indicative feed modifies quotes; OPRA is the consolidated BBO feed and
requires the appropriate access. The account's OPRA failure is recorded in
`research/adr_data_access_20260907.json`.
[Alpaca data sources](https://docs.alpaca.markets/us/docs/historical-option-data).

A separate historical-bars request for September 4 succeeded: **11 daily bars
across 11 of the 92 requested contracts, totaling 219 reported contracts of
volume**. They are stored in `research/adr_bars_20260904.json`. Missing bars mean
no bar was returned, not a confirmed zero-volume observation. The symbol universe
was discovered later, so this is not a survivorship-free historical universe.
The bars endpoint rejects a `feed` argument; its endpoint-default data is recorded
separately and is not relabeled as indicative. OHLC and volume never enter the
volatility calculation. [Historical bars API](https://docs.alpaca.markets/us/reference/optionbars).

## Reproduce and extend

From the project folder in the `py4fi` environment:

```powershell
python research/adr_research.py audit research/adr_snapshot_20260907_indicative.json
python research/adr_research.py audit research/adr_snapshot_20260907_indicative.json --rate 0.04 --output research/adr_audit_rate4.json
python research/adr_research.py capture --feed indicative --start 2026-09-07 --end 2026-12-31
python research/adr_research.py bars research/adr_snapshot_20260907_indicative.json --date 2026-09-04
python -m unittest discover -s tests -v
```

`capture` dates filter expirations, not quote dates. It saves timestamped source
archives; `audit` is offline and exports the calculation JSON, source quotes CSV
and per-expiry constituent CSVs. The dashboard also downloads its assumptions,
results and constituent weights. No credentials enter these artifacts.

Next validation requires actual OPRA quotes with sufficient liquidity, a dated
USD discount curve and review of dividends, deliverables and early exercise.
Repeated quote captures would allow an observed daily series; no time series has
been fabricated from this single observation.
