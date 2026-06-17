from math import exp

from common.orderbook import has_top, mid
from common.timeutil import time_to_expiry
from config import RATE, ETF_M, INDEX_DIVISOR, CONSTITUENTS, POSITION_LIMIT
from strategies.options_mm import compute_stock_delta, compute_index_delta

DELTA_HEDGE_THRESHOLD = 0.5


def compute_constituent_index(ex):
    total = 0.0
    for sid, w in CONSTITUENTS.items():
        m = mid(ex.book(sid))
        if m is None:
            return None
        total += w * m
    return total / INDEX_DIVISOR


def unwind_index_options(ex, idx_opts, pos):
    for oid in idx_opts:
        p = pos.get(oid)
        if abs(p) <= 20:
            continue
        ob = ex.book(oid)
        if not has_top(ob):
            continue
        if p > 20:
            sell_vol = min(p - 15, 5)
            ex.cancel(oid)
            ex.insert(oid, ob.bids[0].price, sell_vol, "ask", "ioc")
            pos.fill(oid, sell_vol, "ask")
        elif p < -20:
            buy_vol = min(abs(p) - 15, 5)
            ex.cancel(oid)
            ex.insert(oid, ob.asks[0].price, buy_vol, "bid", "ioc")
            pos.fill(oid, buy_vol, "bid")


def hedge_stock(ex, underlying: str, delta: float, pos):
    if abs(delta) <= DELTA_HEDGE_THRESHOLD:
        return
    b = ex.book(underlying)
    if not has_top(b):
        return
    if delta > DELTA_HEDGE_THRESHOLD:
        lots = min(round(delta), pos.hr(underlying, "ask"), POSITION_LIMIT)
        if lots > 0:
            ex.cancel(underlying)
            ex.insert(underlying, b.bids[0].price, lots, "ask", "ioc")
            pos.fill(underlying, lots, "ask")
    else:
        lots = min(round(abs(delta)), pos.hr(underlying, "bid"), POSITION_LIMIT)
        if lots > 0:
            ex.cancel(underlying)
            ex.insert(underlying, b.asks[0].price, lots, "bid", "ioc")
            pos.fill(underlying, lots, "bid")


def hedge_all_deltas(ex, insts, stock_opts, stock_futs, idx_opts, ob5x_futs, primary_fut, pos):
    # Re-fetch real positions before hedging so we hedge against the true book,
    # not the optimistically-filled local cache.
    real_pos = ex.get_positions()
    pos.sync(real_pos)

    for underlying, opts in stock_opts.items():
        u_mid = mid(ex.book(underlying))
        if u_mid is None:
            continue
        futs = stock_futs.get(underlying, [])
        delta = compute_stock_delta(pos, underlying, opts, futs, u_mid)
        hedge_stock(ex, underlying, delta, pos)

    if ob5x_futs:
        ref_book = ex.book(ob5x_futs[0])
        if has_top(ref_book):
            tau = time_to_expiry(insts[ob5x_futs[0]].expiry)
            if tau > 0:
                idx_val = mid(ref_book) / exp(RATE * tau)
                delta = compute_index_delta(pos, idx_opts, ob5x_futs, ETF_M, idx_val)
                remaining = delta
                if abs(remaining) > DELTA_HEDGE_THRESHOLD:
                    for fid in ob5x_futs:
                        if abs(remaining) <= DELTA_HEDGE_THRESHOLD:
                            break
                        fb = ex.book(fid)
                        if not has_top(fb):
                            continue
                        if remaining > DELTA_HEDGE_THRESHOLD:
                            lots = min(round(remaining), pos.hr(fid, "ask"), POSITION_LIMIT)
                            if lots > 0:
                                ex.cancel(fid)
                                ex.insert(fid, fb.bids[0].price, lots, "ask", "ioc")
                                pos.fill(fid, lots, "ask")
                                remaining -= lots
                        elif remaining < -DELTA_HEDGE_THRESHOLD:
                            lots = min(round(abs(remaining)), pos.hr(fid, "bid"), POSITION_LIMIT)
                            if lots > 0:
                                ex.cancel(fid)
                                ex.insert(fid, fb.asks[0].price, lots, "bid", "ioc")
                                pos.fill(fid, lots, "bid")
                                remaining += lots
