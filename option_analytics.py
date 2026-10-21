"""Binomial (Leisen–Reimer) option analytics and expiration P/L.

Prices, implied volatility and Greeks come from a recombining lattice with optional
American early exercise and a continuous dividend yield. Black–Scholes–Merton is kept
as the European closed-form reference. Everything is vectorised over contracts.

Rates, yield and volatility are annual decimals; time is in years (the caller decides
the day-count and expiry cutoff). Greeks are per underlying unit: theta/day, vega and
rho/percentage point, from bump-and-reprice on the same lattice.
"""
import math

import numpy as np

STEPS = 101  # odd, as the Leisen–Reimer inversion requires
MAX_IV = 10.  # 1000%; higher volatilities overflow the lattice


def _finite(**values):
    if any(not math.isfinite(v) for v in values.values()):
        raise ValueError("Inputs must be finite numbers.")


def _inputs(spot, strike, time, rate, yield_rate, option_type):
    _finite(spot=spot, strike=strike, time=time, rate=rate, yield_rate=yield_rate)
    if spot <= 0 or strike <= 0 or time < 0:
        raise ValueError("Spot and strike must be positive; time cannot be negative.")
    if option_type.lower() not in ("call", "put"):
        raise ValueError("Option type must be call or put.")
    return 1 if option_type.lower() == "call" else -1


def _cdf(x):
    return math.erfc(-x / math.sqrt(2)) / 2


def bs_price(spot, strike, time, rate, volatility, option_type="call", yield_rate=0.):
    """European closed-form reference price per underlying unit; supports expiry and zero volatility."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    _finite(volatility=volatility)
    if volatility < 0:
        raise ValueError("Volatility cannot be negative.")
    s, k = spot * math.exp(-yield_rate*time), strike * math.exp(-rate*time)
    if time == 0 or volatility == 0:
        return max(sign*(s-k), 0.)
    width = volatility * math.sqrt(time)
    d1 = (math.log(spot/strike)+(rate-yield_rate)*time)/width + width/2
    return sign*(s*_cdf(sign*d1)-k*_cdf(sign*(d1-width)))


def _steps(steps):
    steps = int(steps)
    if steps < 3:
        raise ValueError("The lattice needs at least 3 steps.")
    return steps | 1


def _peizer_pratt(z, n):
    """Peizer–Pratt method 2 inversion of the normal CDF for the Leisen–Reimer tree."""
    return 0.5 + 0.5*np.sign(z)*np.sqrt(1 - np.exp(-(z/(n+1/3+0.1/(n+1)))**2*(n+1/6)))


def _lattice(spot, strike, time, rate, vol, sign, yield_rate, steps, american):
    """Leisen–Reimer price for 1-D arrays with time > 0 and vol > 0."""
    n = steps
    dt = time/n
    root = vol*np.sqrt(time)
    d1 = (np.log(spot/strike)+(rate-yield_rate+vol**2/2)*time)/root
    pp = np.clip(_peizer_pratt(d1, n), 1e-12, 1-1e-12)
    p = np.clip(_peizer_pratt(d1-root, n), 1e-12, 1-1e-12)
    growth = np.exp((rate-yield_rate)*dt)
    up, down = growth*pp/p, growth*(1-pp)/(1-p)
    disc = np.exp(-rate*dt)[:, None]
    p = p[:, None]
    j = np.arange(n+1)
    # Terminal prices in log space so extreme volatilities fail soft instead of overflowing.
    nodes = np.exp(np.log(spot)[:, None] + j*np.log(up)[:, None] + (n-j)*np.log(down)[:, None])
    k, sgn, down = strike[:, None], sign[:, None], down[:, None]
    value = np.maximum(sgn*(nodes-k), 0.)
    for i in range(n-1, -1, -1):
        value = disc*(p*value[:, 1:] + (1-p)*value[:, :-1])
        if american:
            nodes = nodes[:, :i+1]/down
            value = np.maximum(value, sgn*(nodes-k))
    return value[:, 0]


def _deterministic(spot, strike, time, rate, sign, yield_rate, steps, american):
    """Zero-volatility value: the best discounted payoff along the forward path."""
    t = time[:, None]*np.linspace(0, 1, steps+1)
    payoff = np.maximum(sign[:, None]*(spot[:, None]*np.exp((rate-yield_rate)[:, None]*t) - strike[:, None]), 0.)
    payoff *= np.exp(-rate[:, None]*t)
    return payoff.max(axis=1) if american else payoff[:, -1]


def _price(spot, strike, time, rate, vol, sign, yield_rate, steps=STEPS, american=True):
    """Vectorised lattice price; expired and zero-volatility contracts use closed forms."""
    spot, strike, time, rate, vol, sign, yield_rate = (
        np.array(a, dtype=float).ravel() for a in np.broadcast_arrays(spot, strike, time, rate, vol, sign, yield_rate))
    steps = _steps(steps)
    out = np.empty(spot.shape)
    expired = time <= 0
    flat = ~expired & (vol <= 0)
    live = ~expired & ~flat
    out[expired] = np.maximum(sign[expired]*(spot[expired]-strike[expired]), 0.)
    with np.errstate(all="ignore"):
        if flat.any():
            m = flat
            out[m] = _deterministic(spot[m], strike[m], time[m], rate[m], sign[m], yield_rate[m], steps, american)
        if live.any():
            m = live
            out[m] = _lattice(spot[m], strike[m], time[m], rate[m], vol[m], sign[m], yield_rate[m], steps, american)
    return out


def binomial_price(spot, strike, time, rate, volatility, option_type="call", yield_rate=0.,
                   american=True, steps=STEPS):
    """Lattice price per underlying unit; American early exercise unless american=False."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    _finite(volatility=volatility)
    if volatility < 0:
        raise ValueError("Volatility cannot be negative.")
    return float(_price(spot, strike, time, rate, volatility, sign, yield_rate, steps, american)[0])


def solve_iv(premium, spot, strike, time, rate, sign, yield_rate, american=True, steps=STEPS):
    """Implied volatilities for arrays of contracts. Returns (iv, errors); errors[i] is None when solved."""
    cols = [np.array(a, dtype=float).ravel() for a in
            np.broadcast_arrays(premium, spot, strike, time, rate, sign, yield_rate)]
    premium, spot, strike, time, rate, sign, yield_rate = cols
    steps = _steps(steps)
    count = len(premium)
    iv, errors = np.full(count, np.nan), np.full(count, None, dtype=object)
    ok = np.ones(count, bool)

    def reject(mask, message):
        nonlocal ok
        errors[mask & ok] = message
        ok &= ~mask

    reject(~np.all([np.isfinite(c) for c in cols], axis=0), "Inputs must be finite numbers.")
    with np.errstate(invalid="ignore"):
        reject((spot <= 0) | (strike <= 0) | (time < 0), "Spot and strike must be positive; time cannot be negative.")
        reject(time <= 0, "IV requires time remaining before expiry.")
    idx = np.flatnonzero(ok)
    if not len(idx):
        return iv, errors
    prem, S, K, T, r, sg, q = (c[idx] for c in cols)
    floor = _price(S, K, T, r, np.zeros(len(idx)), sg, q, steps, american)
    upper = np.where(sg == 1, S, K)
    tol = 1e-9*np.maximum(1., K)  # absorb float noise at the intrinsic-value boundary
    outside = (prem < floor - tol) | (prem >= upper)
    errors[idx[outside]] = "Premium is outside finite-IV model price bounds."
    at_floor = ~outside & (prem <= floor + tol)
    iv[idx[at_floor]] = 0.
    live = ~outside & ~at_floor
    if not live.any():
        return iv, errors
    idx, prem, S, K, T, r, sg, q = (a[live] for a in (idx, prem, S, K, T, r, sg, q))

    def price(vol):
        return _price(S, K, T, r, vol, sg, q, steps, american)

    lo, hi = np.full(len(idx), 1e-6), np.ones(len(idx))
    for _ in range(5):  # 1 -> 2 -> 4 -> 8 -> MAX_IV
        short = price(hi) < prem
        if not short.any():
            break
        hi = np.where(short, np.minimum(hi*2, MAX_IV), hi)
    unbracketed = ~(price(hi) >= prem)
    errors[idx[unbracketed]] = "Could not bracket IV."
    for _ in range(50):
        mid = (lo+hi)/2
        below = price(mid) < prem
        lo, hi = np.where(below, mid, lo), np.where(below, hi, mid)
        if (hi-lo).max() < 1e-10:
            break
    solved = ~unbracketed
    iv[idx[solved]] = ((lo+hi)/2)[solved]
    return iv, errors


def greeks_batch(spot, strike, time, rate, vol, sign, yield_rate, american=True, steps=STEPS):
    """Delta, gamma, theta/day, vega/vol point and rho/rate point by central bump-and-reprice."""
    spot, strike, time, rate, vol, sign, yield_rate = (
        np.array(a, dtype=float).ravel() for a in np.broadcast_arrays(spot, strike, time, rate, vol, sign, yield_rate))
    count = len(spot)
    h_spot, h_time = 0.01*spot, np.minimum(1/365, time/2)
    h_vol, h_rate = np.minimum(0.01, vol/2), 0.01
    zero = np.zeros(count)
    # Variants (spot, time, vol, rate shifts): base, spot +/-, shorter time, vol +/-, rate +/-
    shifts = [(zero, zero, zero, zero), (h_spot, zero, zero, zero), (-h_spot, zero, zero, zero),
              (zero, -h_time, zero, zero), (zero, zero, h_vol, zero), (zero, zero, -h_vol, zero),
              (zero, zero, zero, h_rate+zero), (zero, zero, zero, -h_rate+zero)]

    def stack(base, column):
        return np.concatenate([base + s[column] for s in shifts])
    prices = _price(stack(spot, 0), np.tile(strike, 8), stack(time, 1), stack(rate, 3), stack(vol, 2),
                    np.tile(sign, 8), np.tile(yield_rate, 8), steps, american).reshape(8, count)
    base, up, down, shorter, vol_up, vol_down, rate_up, rate_down = prices
    with np.errstate(all="ignore"):
        return dict(delta=(up-down)/(2*h_spot),
                    gamma=(up-2*base+down)/h_spot**2,
                    theta=(shorter-base)/h_time/365,
                    vega=(vol_up-vol_down)/(2*h_vol)/100,
                    rho=(rate_up-rate_down)/(2*h_rate)/100)


def implied_volatility(premium, spot, strike, time, rate, option_type="call", yield_rate=0.,
                       american=True, steps=STEPS):
    """Solve annual decimal IV on the lattice; reject expired options and impossible prices."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    iv, errors = solve_iv(premium, spot, strike, time, rate, sign, yield_rate, american, steps)
    if errors[0] is not None:
        raise ValueError(errors[0])
    return float(iv[0])


def calculate_greeks(spot, strike, time, rate, volatility, option_type="call", yield_rate=0.,
                     american=True, steps=STEPS):
    """Delta, gamma, theta/day, vega/1 vol point, rho/1 rate point."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    _finite(volatility=volatility)
    if time <= 0 or volatility <= 0:
        raise ValueError("Greeks require positive time and volatility.")
    values = greeks_batch(spot, strike, time, rate, volatility, sign, yield_rate, american, steps)
    return {name: float(value[0]) for name, value in values.items()}


def build_payoff(prices, legs):
    """Return total expiration P/L for signed quantities and explicit multipliers.

    Each leg: type (call/put/stock), strike, premium (stock entry price),
    quantity (negative for short), multiplier. Options must share an expiry.
    Premiums are undiscounted; fees, financing and dividends are excluded.
    """
    prices, legs = list(prices), list(legs)
    for price in prices:
        _finite(price=price)
        if price < 0:
            raise ValueError("Underlying prices cannot be negative.")
    expiries = {leg.get("expiration") for leg in legs if leg["type"].lower() != "stock"}
    if len(expiries) > 1:
        raise ValueError("Option legs must share one expiration.")
    result = [0.]*len(prices)
    for leg in legs:
        kind = leg["type"].lower()
        strike, premium, quantity, multiplier = (float(leg[k]) for k in ("strike", "premium", "quantity", "multiplier"))
        _finite(strike=strike, premium=premium, quantity=quantity, multiplier=multiplier)
        if kind not in ("call", "put", "stock") or premium < 0 or multiplier <= 0 or (kind != "stock" and strike <= 0):
            raise ValueError("Check leg type, strike, premium and positive multiplier.")
        for i, price in enumerate(prices):
            intrinsic = price if kind == "stock" else max((price-strike)*(1 if kind == "call" else -1), 0.)
            result[i] += quantity*multiplier*(intrinsic-premium)
    return result
