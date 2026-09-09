# ARS funding for Galicia options

Implemented 7 September 2026. This is a research funding proxy for BYMA GGAL
options, not a validated risk-free curve. USD ADR inputs remain separate.

## Dashboard use

In **BYMA > Volatility index > Calculation assumptions**, the default rate
source is **Caución curve**. In **Option analytics**, enable **Use calculated
analytics** to see the same funding controls above the chain.

Strict mode requires dated observations. BYMADATA's checked public caución
response supplies `tradeHour` without a trade date. To use those observations,
select **Funding quality and conventions > Allow undated caución observations
for research**. This is an explicit data-quality exception, not proof of
freshness. Otherwise rates and dependent option estimates remain unavailable.

**Refresh data** refreshes options and funding together. **Refresh funding data**
refreshes both funding providers. Requests are cached for 60 seconds on reruns;
there is no background polling. Failures never return a previously successful
curve or substitute zero. Existing displayed results are snapshots: refresh
before treating them as a new observation.

**Manual continuous rates** remains available, including rates by expiry.
These are explicitly labeled scenarios.

## Data and quality rules

The [BYMA public caución endpoint](https://open.bymadata.com.ar/vanoms-be-core/rest/api/bymadata/free/cauciones)
is queried using the same TLS-verifying client as the option chain. Only BYMA
ARS cauciones (`QS`) with same-day settlement are used. USD, other security
types and settlements are excluded. The feed has no contracted API guarantee.

The saved fixture `tests/fixtures/byma_cauciones_20260907.json` was retrieved on
September 7 Buenos Aires time (September 8 UTC). It contains ARS and USD rows.
For the ARS 30-day instrument, `trade=0.24` means 24% TNA. The `settlementPrice`
field uses different units and never supplies a curve input. Neither closing
prices nor previous-day prices substitute for missing trades.

Defaults require at least ARS 1,000,000 reported nominal volume and five reported
orders. These are configurable research thresholds. `numberOfOrders` is not a
verified trade count, and aggregate volume does not establish the size of the
last trade. Detailed transaction data would be needed for a robust synchronized
short-window estimator. Higher rates are not automatically rejected as outliers.

Each retained node requires a positive finite selected rate, future maturity,
and agreement between calendar days to maturity and `daysToMaturity`. Duplicate
eligible maturities are rejected rather than arbitrarily chosen or averaged.

Where a full timestamp is supplied, the default maximum trade age is 30 minutes.
Future, malformed and timezone-free timestamps are rejected. Undated opt-in never
relaxes an explicitly stale timestamp. Funding retrieval must be within five
minutes of the option valuation and on the same Buenos Aires date; a snapshot
over 120 seconds old is rejected on evaluation. These checks cannot establish
the age of undated source prices or the synchronization of BYMA option quotes.

## Discounting and expiry matching

For annual decimal TNA `j` and contractual calendar tenor `d`:

```
D(d) = 1 / (1 + j*d/365)
r_continuous(d) = -log(D(d)) / (d/365)
```

The fixed 365 divisor is specified in the published
[caución rules, interest calculation](https://data-widgets.byma.com.ar/wp-content/uploads/2017/04/TOC2013.pdf).
The dashboard uses this basis. The pure calculation function also supports 360
for explicit offline convention sensitivity; the source does not select it.
Broker-specific fees, haircuts and actual borrowing costs are not incorporated.

Curve nodes use calendar-day settlement tenors mapped to valuation-relative
days. Exact cash-settlement times are unavailable. VIX research queries the
curve using minutes to the existing 15:30 Buenos Aires expiry cutoff; IV/Greeks
retain their existing calendar-days/365 convention. These time conventions are
recorded research approximations and can yield slightly different rates.

Between adjacent eligible nodes, interpolate `log(D)`, including the mathematical
anchor `D(0)=1`. Do not average 1-, 7- and 30-day TNA or carry overnight rates
through longer maturities. All eligible tenors may be used. Beyond the last
node there is no extrapolation. The default largest interpolation gap is 14
calendar days, configurable explicitly. Negative implied forward segments are
flagged and retained, not smoothed away. Each query records its bracketing nodes.

Each option expiration needs its own rate, including the two component expiries
of a constant 30-day volatility calculation. Missing funding fails that term;
the term remains in maturity selection and cannot be skipped for a later expiry.

## Volatile periods and sensitivity

Last trade is the default observation. Daily volume-weighted average is an
explicit alternative with a warning that it can lag an intraday move. Daily
VWAP is never described as a short-window or contemporaneous rate. Last versus
VWAP differences of at least five TNA percentage points are flagged without
deleting the observation. An overnight spike does not overwrite the 30-day node.

The volatility view compares selected rates, configurable positive/negative
continuous-rate shocks (default five percentage points), the alternative
last/VWAP curve and the optional LECAP proxy. Option quotes stay fixed while the
forward and strike selection are recalculated. Results show volatility-point
changes by expiry and at 30 days, retaining unavailable scenarios. These are
sensitivities, not confidence bounds or a time-series attribution model.

## Optional Treasury comparison and fallback

**Compare with Bonistas LECAP yields** is off by default. It reads the
[Bonistas bond feed](https://bonistas.com/api/bonds), restricting it to CI
`LETRAS-FIJO` records with a positive price/activity, performing status, consistent
maturity and the current estimation date. No CER, TAMAR, dual, dollar-linked,
coupon-bearing BONCAP, 24-hour settlement or fitted duration-curve data enters.

This is a **reported-TEA proxy**, not an independently bootstrapped Treasury
curve. Enabling its use requires the date-only/TEA research checkbox. Assume
reported `tir` is effective annual ACT/365, check it against `(1+mtir)^12-1`
within 0.002 annual decimal units, and set `log(D)=-log(1+tir)*d/365`. The
consistency check is not independent verification of cash flows or day count.
Provider prose about issuers and inferred final payments is not trusted.

Using that proxy as a fallback requires a separate checkbox. It substitutes an
entire expiry only when the caución query fails and the independent LECAP curve
covers the expiry under the gap policy. It never splices a Treasury node into
the caución curve. The selected source and fallback flag are displayed/exported.
Differences reflect sovereign and funding risks as well as source conventions.
Verified instrument terms and final cash flows are still required before
calling this a validated sovereign discount curve.

## Audit and verification

Funding JSON includes raw inputs, retrieval times, quality policy, accepted and
rejected observations, interpolation nodes, per-expiry sources, alternative
rates and failures. The volatility JSON embeds the funding audit and sensitivity
results. Calculated option CSVs include `model_rate`, `model_rate_source`,
`model_rate_fallback` and `model_rate_status`.

Tests cover TNA conversion, interpolation, overnight spikes, insufficient
liquidity, timestamps, expired snapshots, currency/settlement separation,
duplicate maturities, gap limits, no extrapolation, explicit Treasury fallback,
missing-term propagation, UI opt-in and recovery after data-source failure.
The previous Cboe worked-example and ADR regression checks remain applicable.

```
python -m unittest discover -s tests -v
```
