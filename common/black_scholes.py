import numpy as np
from scipy.stats import norm


def _d1(S, K, T, r, sigma):
    return (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))


def call_value(S, K, T, r, sigma):
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def put_value(S, K, T, r, sigma):
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def call_delta(S, K, T, r, sigma):
    return norm.cdf(_d1(S, K, T, r, sigma))


def put_delta(S, K, T, r, sigma):
    return call_delta(S, K, T, r, sigma) - 1.0


def call_vega(S, K, T, r, sigma):
    return S * norm.pdf(_d1(S, K, T, r, sigma)) * np.sqrt(T)


# Vega is the same for calls and puts (put-call parity differentiates to zero in sigma).
def put_vega(S, K, T, r, sigma):
    return call_vega(S, K, T, r, sigma)
