"""European Black–Scholes–Merton analytics and expiration P/L.

Rates, yield and volatility are annual decimals; time is ACT/365 years.
Greeks are per underlying unit: theta/day, vega and rho/percentage point.
"""
import math


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
    """Price per underlying unit; supports expiry and zero volatility."""
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


def implied_volatility(premium, spot, strike, time, rate, option_type="call", yield_rate=0.):
    """Solve annual decimal IV; reject expired options and impossible prices."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    _finite(premium=premium)
    if time <= 0:
        raise ValueError("IV requires time remaining before expiry.")
    s, k = spot*math.exp(-yield_rate*time), strike*math.exp(-rate*time)
    lower, upper = max(sign*(s-k), 0.), s if sign == 1 else k
    if premium < lower or premium >= upper:
        raise ValueError("Premium is outside finite-IV model price bounds.")
    if premium == lower:
        return 0.
    lo, hi = 0., 1.
    while bs_price(spot, strike, time, rate, hi, option_type, yield_rate) < premium:
        hi *= 2
        if hi > 1024:
            raise ValueError("Could not bracket IV.")
    for _ in range(100):
        mid = (lo+hi)/2
        if bs_price(spot, strike, time, rate, mid, option_type, yield_rate) < premium:
            lo = mid
        else:
            hi = mid
    return (lo+hi)/2


def calculate_greeks(spot, strike, time, rate, volatility, option_type="call", yield_rate=0.):
    """Delta, gamma, theta/day, vega/1 vol point, rho/1 rate point."""
    sign = _inputs(spot, strike, time, rate, yield_rate, option_type)
    _finite(volatility=volatility)
    if time <= 0 or volatility <= 0:
        raise ValueError("Greeks require positive time and volatility.")
    root = math.sqrt(time)
    d1 = (math.log(spot/strike)+(rate-yield_rate+volatility**2/2)*time)/(volatility*root)
    d2 = d1-volatility*root
    discount = math.exp(-yield_rate*time)
    k = strike*math.exp(-rate*time)
    density = math.exp(-d1*d1/2)/math.sqrt(2*math.pi)
    return dict(delta=sign*discount*_cdf(sign*d1),
                gamma=discount*density/(spot*volatility*root),
                theta=(-spot*discount*density*volatility/(2*root)
                       -sign*rate*k*_cdf(sign*d2)
                       +sign*yield_rate*spot*discount*_cdf(sign*d1))/365,
                vega=spot*discount*density*root/100,
                rho=sign*k*time*_cdf(sign*d2)/100)


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
