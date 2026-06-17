from math import exp

from common.orderbook import has_top, round_down, round_up
from config import RATE, ETF_M

ETF_C = 2.50
ETF_CREDIT = 0.02
ETF_VOLUME = 25
POS_SKEW_THRESHOLD = 10
POS_SKEW_DIVISOR = 3


def run_etf_quoting(ex, primary_fut: str, insts: dict, pos, const_idx: float | None, tau: float):
    if not primary_fut or "OB5X_ETF" not in insts:
        return

    fb = ex.book(primary_fut)
    if not has_top(fb):
        return

    if tau <= 0:
        tau = 1e-6

    tick = insts["OB5X_ETF"].tick_size
    fbid, fask = fb.bids[0].price, fb.asks[0].price

    fair_bid = ETF_C + ETF_M * (fbid / exp(RATE * tau))
    fair_ask = ETF_C + ETF_M * (fask / exp(RATE * tau))

    if const_idx is not None:
        from_const = ETF_C + ETF_M * const_idx
        fair_bid = min(fair_bid, from_const)
        fair_ask = max(fair_ask, from_const)

    bp = round_down(fair_bid - ETF_CREDIT, tick)
    ap = round_up(fair_ask + ETF_CREDIT, tick)
    if bp <= 0 or ap <= 0 or bp >= ap:
        return

    ep = pos.get("OB5X_ETF")
    bv = min(ETF_VOLUME, pos.hr("OB5X_ETF", "bid"))
    av = min(ETF_VOLUME, pos.hr("OB5X_ETF", "ask"))
    if ep > POS_SKEW_THRESHOLD:
        bv = max(0, bv - ep // POS_SKEW_DIVISOR)
    elif ep < -POS_SKEW_THRESHOLD:
        av = max(0, av + ep // POS_SKEW_DIVISOR)

    ex.cancel("OB5X_ETF")
    if bv > 0:
        ex.insert("OB5X_ETF", bp, bv, "bid", "limit")
    if av > 0:
        ex.insert("OB5X_ETF", ap, av, "ask", "limit")
