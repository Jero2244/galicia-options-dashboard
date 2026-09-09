# Galicia BYMA option data

Checked September 4, 2026. This comparison is for options on GGAL local shares in
ARS. US options on the GGAL ADR are a different market.

Funding update (September 7): the app also reads BYMADATA's ARS caución panel.
Its undated trade hours require explicit research opt-in before use. Bonistas
LECAP yields are an optional, separately labeled comparison/fallback proxy.
See [ARS funding sources, checks and conventions](ARS_FUNDING_METHODOLOGY.md).

## Best fit for this program: BYMADATA Open

For free access without opening a broker account, my recommendation is BYMA's own
public feed. Its options endpoint returned 73 GGAL contracts during the live check,
including calls and puts with September, October and December expirations.
The accompanying GGAL stock panel also responded successfully with certificate
verification enabled. The program now uses this connection by default.

[BYMA's open-access announcement](https://www.byma.com.ar/newsroom/byma-habilita-un-acceso-abierto-a-bymadata)
describes a free service with a 20-minute delay.

The checked response contains bid/ask, last trade, previous close, volume, open
interest and maturity dates. It lacks IV, Greeks, an explicit strike field and
full quote timestamps. Some contracts have no bids, offers or trades. Four of the
73 symbols use ambiguous five-digit strike codes: the app retains those rows
with strike blank instead of guessing whether a decimal separator was omitted.
Other strike codes are decoded from the symbol and labeled accordingly.

This is the public website's interface, not a contracted developer API with a
stability guarantee. It suits occasional personal snapshots. Missing analytics
would need a separately specified valuation model, rates and dividend assumptions;
buying faster quotes alone does not guarantee IV or Greeks.

## Other free or account-based choices

**IOL:** The strongest alternative to investigate if you already have an account.
Its official API advertises real-time Argentine options and historical quotes.
It requires account access and API activation, so it cannot be connected here
without your credentials. The tariff currently waives charges for up to 25,000
calls per month. Sources: [API coverage and activation](https://www.invertironline.com/herramientas/api),
[current tariff](https://www.invertironline.com/tarifas).

**Data912 (corrected September 8):** Offers Argentine options through
`/live/arg_options`, as well as US EOD options through `/eod/option_chain/{ticker}`.
The live check returned 87 GGAL local rows, including bid/ask and sizes, with 83
symbols shared by the September 7 BYMA archive. Local rows lack dated quotes,
explicit strikes, expirations, settlement and IV/Greeks. The US chain returned
HTTP 500 for GGAL and AAPL during this check; ADR prices and volatility summaries
did respond. See the [recorded comparison](research/DATA912_CHECK_20260908.md)
and [API documentation](https://data912.apidocs.ar/).

**Public broker web tables:** These can supplement instrument details, but add
another site's availability and HTML changes to the integration. An Allaria
production options URL failed during this check, so it was not selected as a
dependency. No broker website is used as a silent fallback.

## Paid upgrades

| Source | Improvement for this program | Published cost / access |
| --- | --- | --- |
| BYMA Market Data API, Snapshot | Official real-time snapshot integration with a defined request allowance | Page lists USD 120, 500 and 1,000/month tiers. Eligibility and licensing category must be confirmed with BYMA. |
| BYMA Market Data API, Delay / EOD | Contracted delayed or closing-data access, useful for a maintained application | Listed Delay tiers: USD 60, 100 and 500/month; EOD tiers include USD 30 and 50/month, plus a member free tier. Confirm the applicable category. |
| Primary API through a participating broker | Real-time and historical market data; suitable for a future streaming connection | Production access, BYMA entitlements and charges depend on the broker; no single retail price was verified. |
| IOL API above its free allowance | Official account-based API with real-time options and historical quotes | Tariff says ARS 500 + VAT after 25,000 monthly calls, credited toward trading commissions over the next 30 days. Confirm the tariff when activating. |

BYMA's Snapshot tiers list 79,200 or 237,600 monthly requests; Delay lists 39,600
or 79,200 and 20-minute latency. Direct access requires a market-data agreement.
Its Instruments API is separately listed and can provide reference data; confirm
exact GGAL adjusted strikes, contract sizes and package inclusion before subscribing.
Source: [BYMA API catalogue and prices](https://www.byma.com.ar/productos/productos-de-datos/market-data/apis).

Primary publishes a REST/WebSocket API and BYMA instrument support. Production
credentials and permissions need to come from the relevant provider/broker;
test-market credentials are not a production BYMA feed.
Sources: [Primary API hub](https://apihub.primary.com.ar/),
[Primary API manual](https://apihub.primary.com.ar/assets/docs/Primary-API.pdf).

For this personal dashboard, I would keep the integrated free feed and investigate
IOL or your existing broker's Primary access first if you need real-time data or
verified contract metadata. Direct BYMA licensing is more appropriate when formal
API access and ongoing integration justify its cost. A paid terminal subscription
should not be assumed to include permission or credentials for a Python API.
