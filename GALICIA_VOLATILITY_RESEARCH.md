# Galicia volatility: methodology and feasibility

Research version 1.0 | 7 September 2026 | GGAL local shares, BYMA, ARS

Implementation update: the dashboard now supports a caución funding curve,
explicit undated-data research mode, optional Bonistas LECAP reported-yield
comparison/fallback, and funding sensitivity. See
[ARS funding methodology](ARS_FUNDING_METHODOLOGY.md). The recorded snapshot
results and rate scenarios below remain the original version 1.0 audit; they
have not been recomputed using today's funding data.

## Finding

A VIX-style research calculator is feasible with BYMADATA's public quotes. A reliable constant 30-day Galicia index is **not supported by the observed snapshot**. October has substantial quote coverage; September has no usable two-sided quotes, and December lacks a usable same-strike call/put pair. Those are concrete calculation failures, not merely concerns about small trading volumes.

The dashboard now has **Workspace > Volatility index** when BYMA is selected. It displays liquidity by expiry and option type, runs the strip arithmetic, explains failures, and exports the calculation audit. The default requires resolved strikes. An optional partial-strip diagnostic uses only the known strikes, with its limitations displayed. No validated index is published.

This is a measure of **one company's local share option prices in pesos**. It cannot be interpreted as volatility of the Argentine equity market as a whole, nor compared mechanically with the S&P 500 VIX or Galicia's USD ADR volatility.

## Snapshot evidence

Source: public BYMADATA `options` and `leading-equity` endpoints. Retrieved **7 September 2026, 13:54:00 Buenos Aires / 16:54:00 UTC**. The options panel returned 476 rows in total, of which 87 were GGAL options. All 87 had ARS currency and provider settlement code `2`. This counts contracts supplied by the panel, not an independently verified security master of every listed series.

GGAL's reported underlying last trade was ARS 6,945, with a supplied trade hour of 13:33:15. The response does not establish the trade date or a quote timestamp. Retrieval time is preserved separately. The public service advertises delayed data; an advertised delay does not prove the age or synchronization of individual quotes.

| Expiration | Side | Contracts supplied | Positive uncrossed bid/ask | With a reported trade | Reported volume | Median spread / midpoint |
|---|---|---:|---:|---:|---:|---:|
| 18 Sep 2026 | Calls | 5 | 0 | 0 | 0 | Unavailable |
| 18 Sep 2026 | Puts | 2 | 0 | 0 | 0 | Unavailable |
| 16 Oct 2026 | Calls | 29 | 29 | 27 | 13,026 | 2.96% |
| 16 Oct 2026 | Puts | 29 | 28 | 17 | 8,205 | 14.08% |
| 18 Dec 2026 | Calls | 10 | 8 | 2 | 12 | 41.41% |
| 18 Dec 2026 | Puts | 12 | 4 | 0 | 0 | 83.31% |

Spread medians use only positive, uncrossed two-sided quotes and include both ITM and OTM contracts. Volume is the provider's raw `volume` field summed within each group; its lot/nominal convention is not independently verified. A reported trade does not establish a fresh quote. A nonzero bid is not evidence that a portfolio can be executed at useful size.

October represents 21,231 of 21,243 reported volume units across these expirations, approximately **99.94%**. Only 13 October calls and 15 October puts have at least five provider quantity units on *both* quote sides. December has only one such call and no such put. Open interest is zero for all 87 rows: its completeness cannot be established, so it is not used as proof of no positions or as an eligibility filter.

This is **one intraday observation**. It establishes feasibility and failures at the recorded snapshot, not sustained liquidity, quote persistence, typical daily volume, market-maker commitment or execution capacity.

## Rules taken from the supplied VIX methodology

The source is `Volatility_Index_Methodology_Cboe_Volatility_Index.pdf`, version 6.0, revised 26 February 2026. Pages 4-8 describe construction and dissemination; pages 9-18 contain the worked example and input quotes. The companion [Cboe mathematics methodology](https://cdn.cboe.com/api/global/us_indices/governance/Cboe_Volatility_Index_Mathematics_Methodology.pdf) supplies further calculation details.

The implementation preserves the following arithmetic from the PDF:

1. Use **option bid/ask midpoints**, with a distinct variance calculation for each expiry. Last trades, previous closes and calculated Black-Scholes IVs never substitute for quote midpoints.
2. Find the call/put strike with the smallest absolute midpoint difference. The lowest strike breaks ties. Calculate the synthetic forward:

   `F = K* + exp(r*T) * (C(K*) - P(K*))`

3. Set `K0` to the supplied strike equal to or immediately below `F`. A missing K0 call or put is a failure; do not move K0 to whichever pair happens to be liquid.
4. Starting at K0, move down the put wing and up the call wing. Skip zero-priced quotes and stop a wing after two consecutive zero bid/ask quotes. Null quotes remain distinct from observed zeros. Require usable OTM prices on both wings. At K0, average the call and put midpoints.
5. Compute strike intervals using the **selected** strip: half the distance between adjacent strikes internally, and the distance to the adjacent strike at each endpoint. Then calculate annualized variance:

   `variance(T) = (2/T) * sum[deltaK / K^2 * exp(r*T) * Q(K)] - (1/T) * (F/K0 - 1)^2`

6. For a target of 30 days, linearly interpolate **total variance**, not volatility. With `T1 <= T30 <= T2` and `w1 = (T2-T30)/(T2-T1)`, `w2 = 1-w1`:

   `variance30 = (w1*T1*variance1 + w2*T2*variance2) / T30`

   `volatility30 = 100 * sqrt(variance30)`

No volume weighting is introduced. VIX's strike contribution is determined by option price and strike spacing divided by strike squared. Volume and displayed size are separate diagnostics.

**The supplied version uses a 30-day bracket method.** The familiar 23-37-day description of SPX's weekly expiry selection is not imposed as a universal formula rule on BYMA monthly contracts. The prototype selects the closest supplied expiry on each side of the target and retains failed expiries in that selection. It refuses extrapolation as an explicit local safeguard; this is stricter than fallback behavior described in Cboe's general bracket framework.

## Necessary Argentine adaptations

| Topic | Implementation and limitation |
|---|---|
| Instrument | GGAL local shares in ARS; no US ADR contracts are mixed in. |
| Exercise | BYMA options are American. The prototype uses premiums as supplied without removing early-exercise value. European put-call parity and variance replication are therefore approximations here. |
| Interest rate | User-entered continuous annual ARS rates, optionally different by expiry. Zero is an illustrative scenario, not an observed risk-free rate. No US Treasury rate is reused for peso options. |
| Time | Whole minutes to 15:30 Buenos Aires on the provider maturity date, divided by 525,600. This uses the last-trading cutoff as a research convention; it is not a verified valuation timestamp or a claim about the exact economic settlement time. |
| Strike metadata | An explicit provider strike wins; otherwise the existing parser accepts unambiguous short/decimal codes. Five-digit codes remain unresolved. No scale is guessed from spot prices. |
| Missing data | Complete strips fail on unresolved strikes. Partial diagnostics require explicit selection and exclude those rows. Both modes preserve missing quote timestamps. |
| Bad quotes | Positive uncrossed ATM/K0 pairs are required. Encountered crossed wing quotes fail the term. These are local safeguards beyond literal Cboe arithmetic. |
| Stale publication | A failed calculation is displayed as unavailable. Cboe's republishing of its last valid level and intraday smoothing are not reproduced. |
| Settlement index | No VIX Special Opening Quotation, settlement auction or tradable derivative is created. |

[BYMA's current rules](https://www.byma.com.ar/productos/productos-financieros/opciones) specify American exercise, T+0 settlement of premiums and T+1 settlement of exercises. Expiry-day trading ends at 15:30, with exercise instructions accepted until 15:59. The public feed still supplies settlement code `2`; the dashboard preserves this provider code rather than using it to override the current rules. BYMA also states that ordinary dividends do not adjust option terms for expirations from July 2026 onward. Dividend timing and extraordinary corporate actions therefore need explicit treatment before interpreting the result as expected variance.

The response has no usable interest-rate curve or discrete dividend schedule. A matched ARS discount curve needs its own documented source, settlement basis and conversion. For a simple annualized rate `j` on a 365-day basis over `d` days, for example, the equivalent continuous rate is `ln(1+j*d/365)/(d/365)`; different quoting conventions need their own conversion. Peso sovereign and collateralized funding yields also contain risks/bases, so selecting one as the discount curve requires a methodological decision.

## What can be calculated now?

### Constant 30-day measure: unavailable

The required supplied expiries are 18 September and 16 October. They are approximately **11.07 and 39.07 days** from retrieval under the cutoff convention. September has neither a usable two-sided same-strike call/put pair nor a put wing. It cannot produce the forward required by the method. Replacing September with December would extrapolate backward from October/December and answer a different question.

### October: useful partial-strip diagnostic

The default complete-strip mode fails because six October contracts have unresolved five-digit strike codes: `GFGC10300O`, `GFGC10700O`, `GFGC11100O`, and their corresponding puts. December has one additional unresolved call. The quote response supplies no explicit strikes to resolve them. These contracts are never silently assigned strikes or dropped from a supposedly complete index.

When **Calculate diagnostics using resolved strikes only** is selected, October produces:

| Quantity | Recorded result, continuous rate = 0% |
|---|---:|
| Remaining tenor | 56,255 minutes / 39.066 days |
| Forward-selection strike K* | ARS 7,200 |
| Synthetic forward F | ARS 7,124.33 |
| K0 | ARS 7,000 |
| OTM puts / OTM calls / K0 composite | 14 / 11 / 1 |
| Known strike range used | ARS 4,200 to 9,900 |
| Annualized variance | 0.192276 |
| Annualized volatility | **43.85%** |
| Fixed-forward bid / ask sensitivities | 43.56% / 44.14% |
| Contribution-weighted spread | 2.61% |
| Largest strike's share of gross variance | 15.76% |
| Largest selected-strike gap / forward | 5.61% |

The much lower weighted spread than the all-put median reflects the fact that the strip uses OTM puts and OTM calls, rather than including the wide-spread deep ITM puts. This supports investigating October further.

The bid/ask figures hold the midpoint forward and constituent basket fixed. They show sensitivity to the supplied prices; they are **not** executable portfolio bounds or statistical confidence intervals. Displayed depth can be small or stale. Both wings reach the edge of the supplied known-strike universe without an observed two-zero termination; absent tails are not assumed to have zero economic value. Unresolved contracts can also affect strike ordering, forward selection and tail coverage.

Rate sensitivity, using the same recorded partial chain and recomputing the forward:

| Illustrative continuous ARS rate | October volatility |
|---:|---:|
| 0% | 43.85% |
| 20% | 44.34% |
| 40% | 44.83% |
| 60% | 45.33% |
| 100% | 46.34% |

These rates are scenarios, not estimates of the prevailing curve. **43.85% is an unvalidated October partial-strip statistic, not Galicia's 30-day VIX.** Early exercise, dividends, omitted strikes and timestamp uncertainty are outside this sensitivity range.

### December: unavailable even in partial mode

Twelve December rows have two-sided quotes, but their call and put strike sets do not overlap at a usable pair. Quote count alone therefore cannot establish calculability. Its wide spreads, almost absent reported trading and weak displayed depth are additional concerns.

## Publication and liquidity policy

The prototype deliberately remains research-only. It displays provisional checks of at least five selected OTM strikes per wing, contribution-weighted spread at most 20%, largest gross-variance contribution at most 25%, and largest adjacent strike gap at most 10% of forward. These are **locally proposed diagnostics**, not Cboe requirements, statistically calibrated thresholds or sufficient conditions for publication.

Before a production index would be supportable, the remaining work is to obtain a complete instrument master with adjusted strikes/deliverables, dated synchronized quotes and quote histories, and an explicit ARS discount/dividend methodology. American premiums would need a documented treatment, such as a validated early-exercise correction; that introduces model dependence. Quote persistence, depth at intended portfolio sizes, wing truncation, parity dispersion and sensitivity to deleted or perturbed quotes should then be measured over many sessions and through an expiry roll.

An initial **daily, expiry-specific October research series** is more defensible than forcing a constant 30-day number. It must retain days to expiry and roll flags; changes in tenor must not be mistaken for changes in expected volatility. If only near-ATM contracts are usable, an American-model ATM IV series is another possible project, but it would measure a different object and should receive a different name. No historical VIX-style series can be reconstructed faithfully from daily last-trade OHLC bars alone: the bid/ask strip at a common timestamp is missing.

## Reproduction and validation

Files:

- `volatility_index.py`: independent strip arithmetic, maturity interpolation and diagnostics.
- `volatility_ui.py`: dashboard view and downloadable audit.
- `research/byma_snapshot_20260907.json`: raw recorded GGAL rows, underlying quote and retrieval time.
- `research/galicia_audit.json`: complete/partial results, constituent contributions and rate scenarios.
- `research/audit_galicia.py`: offline reproduction from the recorded snapshot.
- `tests/fixtures/cboe_vix_example.json`: numerical quote inputs extracted from the supplied PDF's worked example.
- `tests/test_volatility_index.py`: numerical and UI regression checks.

In the existing `py4fi` environment:

```powershell
python research/audit_galicia.py research/byma_snapshot_20260907.json
python -m unittest discover -s tests -v
```

The full suite passed **30 tests**. Using the complete Cboe example inputs reproduces near variance **0.01923390648**, next variance **0.01942388428**, and VIX **13.92784235**, matching the PDF's rounded **13.93**. Tests also cover the two-zero stopping rule, null-versus-zero handling, K0 failures, irregular strike spacing, scale invariance, total-variance interpolation, no skipping failed maturities, unresolved strikes and dashboard controls.

The calculator reproduces the source example's arithmetic. That validation does not remove the market-data or contract-design differences identified above.
