from math import exp

from optibook.common_types import OptionKind

from common.black_scholes import call_delta, put_delta
from common.orderbook import has_top, mid
from common.timeutil import time_to_expiry
from config import RATE, SIGMA

BASIS_THRESHOLD = 0.10
CALENDAR_THRESHOLD = 0.05
PARITY_THRESHOLD = 0.20
ARB_VOLUME = 5


def run_calendar_arb(ex, ob5x_futs: list, insts: dict, pos):
    # Implemented but intentionally left out of run_cross_arb's live rotation,
    # which only runs basis and parity. Kept ready as a calendar leg.
    for i in range(len(ob5x_futs)):
        for j in range(i + 1, len(ob5x_futs)):
            near, far = ob5x_futs[i], ob5x_futs[j]
            nb, fb = ex.book(near), ex.book(far)
            if not (has_top(nb) and has_top(fb)):
                continue
            tn = time_to_expiry(insts[near].expiry)
            tf = time_to_expiry(insts[far].expiry)
            if tn <= 0 or tf <= 0:
                continue
            fair_far = mid(nb) * exp(RATE * (tf - tn))
            spread = mid(fb) - fair_far

            if spread > CALENDAR_THRESHOLD:
                v = min(ARB_VOLUME, pos.hr(far, "ask"), pos.hr(near, "bid"))
                if v > 0:
                    ex.cancel(far)
                    ex.insert(far, fb.bids[0].price, v, "ask", "ioc")
                    pos.fill(far, v, "ask")
                    ex.cancel(near)
                    ex.insert(near, nb.asks[0].price, v, "bid", "ioc")
                    pos.fill(near, v, "bid")
                    return
            elif spread < -CALENDAR_THRESHOLD:
                v = min(ARB_VOLUME, pos.hr(far, "bid"), pos.hr(near, "ask"))
                if v > 0:
                    ex.cancel(far)
                    ex.insert(far, fb.asks[0].price, v, "bid", "ioc")
                    pos.fill(far, v, "bid")
                    ex.cancel(near)
                    ex.insert(near, nb.bids[0].price, v, "ask", "ioc")
                    pos.fill(near, v, "ask")
                    return


def run_basis_arb(ex, stock_futs: dict, insts: dict, pos):
    for stock, futs in stock_futs.items():
        sb = ex.book(stock)
        if not has_top(sb):
            continue
        s_mid = mid(sb)
        for fid in futs:
            if fid not in insts:
                continue
            fbook = ex.book(fid)
            if not has_top(fbook):
                continue
            tau = time_to_expiry(insts[fid].expiry)
            if tau <= 0:
                continue
            fair = s_mid * exp(RATE * tau)
            basis = mid(fbook) - fair

            if basis > BASIS_THRESHOLD:
                v = min(ARB_VOLUME, pos.hr(fid, "ask"), pos.hr(stock, "bid"))
                if v > 0:
                    ex.cancel(fid)
                    ex.insert(fid, fbook.bids[0].price, v, "ask", "ioc")
                    pos.fill(fid, v, "ask")
                    ex.cancel(stock)
                    ex.insert(stock, sb.asks[0].price, v, "bid", "ioc")
                    pos.fill(stock, v, "bid")
                    return
            elif basis < -BASIS_THRESHOLD:
                v = min(ARB_VOLUME, pos.hr(fid, "bid"), pos.hr(stock, "ask"))
                if v > 0:
                    ex.cancel(fid)
                    ex.insert(fid, fbook.asks[0].price, v, "bid", "ioc")
                    pos.fill(fid, v, "bid")
                    ex.cancel(stock)
                    ex.insert(stock, sb.bids[0].price, v, "ask", "ioc")
                    pos.fill(stock, v, "ask")
                    return


def run_parity_arb(ex, option_pairs: dict, insts: dict, pos):
    for (underlying, expiry, strike), kinds in option_pairs.items():
        if OptionKind.CALL not in kinds or OptionKind.PUT not in kinds:
            continue

        call_id = kinds[OptionKind.CALL]
        put_id = kinds[OptionKind.PUT]

        cb = ex.book(call_id)
        pb = ex.book(put_id)
        sb = ex.book(underlying)

        if not (has_top(cb) and has_top(pb) and has_top(sb)):
            continue

        tau = time_to_expiry(expiry)
        if tau <= 0:
            continue

        s_mid = mid(sb)
        pv_strike = strike * exp(-RATE * tau)
        theo_diff = s_mid - pv_strike

        market_diff = mid(cb) - mid(pb)
        mispricing = market_diff - theo_diff

        if mispricing > PARITY_THRESHOLD:
            v = min(ARB_VOLUME, pos.hr(call_id, "ask"), pos.hr(put_id, "bid"))
            if v > 0:
                ex.cancel(call_id)
                ex.insert(call_id, cb.bids[0].price, v, "ask", "ioc")
                pos.fill(call_id, v, "ask")
                ex.cancel(put_id)
                ex.insert(put_id, pb.asks[0].price, v, "bid", "ioc")
                pos.fill(put_id, v, "bid")
                d_call = call_delta(s_mid, strike, tau, RATE, SIGMA)
                d_put = put_delta(s_mid, strike, tau, RATE, SIGMA)
                hedge_lots = round(v * (d_call + d_put))
                if hedge_lots > 0:
                    hv = min(hedge_lots, pos.hr(underlying, "bid"))
                    if hv > 0:
                        ex.insert(underlying, sb.asks[0].price, hv, "bid", "ioc")
                        pos.fill(underlying, hv, "bid")
                return

        elif mispricing < -PARITY_THRESHOLD:
            v = min(ARB_VOLUME, pos.hr(call_id, "bid"), pos.hr(put_id, "ask"))
            if v > 0:
                ex.cancel(call_id)
                ex.insert(call_id, cb.asks[0].price, v, "bid", "ioc")
                pos.fill(call_id, v, "bid")
                ex.cancel(put_id)
                ex.insert(put_id, pb.bids[0].price, v, "ask", "ioc")
                pos.fill(put_id, v, "ask")
                d_call = call_delta(s_mid, strike, tau, RATE, SIGMA)
                d_put = put_delta(s_mid, strike, tau, RATE, SIGMA)
                hedge_lots = round(v * abs(d_call + d_put))
                if hedge_lots > 0:
                    hv = min(hedge_lots, pos.hr(underlying, "ask"))
                    if hv > 0:
                        ex.insert(underlying, sb.bids[0].price, hv, "ask", "ioc")
                        pos.fill(underlying, hv, "ask")
                return


def run_cross_arb(ex, ob5x_futs, stock_futs, option_pairs, insts, pos, sub_cursor: int):
    phase = sub_cursor % 2
    if phase == 0:
        run_basis_arb(ex, stock_futs, insts, pos)
    else:
        run_parity_arb(ex, option_pairs, insts, pos)
