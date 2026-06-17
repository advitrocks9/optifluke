# Main loop: one rate-limited connection drives every strategy. Each iteration
# interleaves dual listing, ETF/future quoting, a slice of option quoting, and
# periodic index-option unwind and cross-instrument arb, then hedges net delta
# across stocks and the index and prints diagnostics on a fixed cadence.

import time
import logging
from math import exp

from common.orderbook import has_top, mid
from common.timeutil import time_to_expiry
from config import RATE, ETF_M

from exchange import Ex
from positions import Pos
from discovery import discover
from hedging import compute_constituent_index, unwind_index_options, hedge_all_deltas

from strategies.dual_listing import run_dual_listing
from strategies.etf_future import run_etf_quoting
from strategies.options_mm import quote_single_option, compute_stock_delta, compute_index_delta
from strategies.cross_arb import run_cross_arb

from optibook.common_types import InstrumentType

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)-8s] %(message)s", datefmt="%H:%M:%S")
logging.getLogger("client").setLevel("ERROR")
log = logging.getLogger("run")

OPTIONS_PER_ITER = 3
LOOP_SLEEP = 0.25
DIAG_INTERVAL = 40


def run_diagnostics(ex, pos, insts, stock_opts, stock_futs, idx_opts, ob5x_futs, primary_fut, duals, prev_pnl, iteration):
    pnl = ex.get_pnl()
    dpnl = pnl - prev_pnl if prev_pnl is not None else 0.0

    lines = [f"=== DIAG iter={iteration} PnL={pnl:.2f} (d={dpnl:+.2f}) ==="]

    active = {k: v for k, v in pos.items() if v != 0}
    if active:
        pos_parts = [f"{k}={v:+d}" for k, v in sorted(active.items())]
        lines.append(f"POS: {' '.join(pos_parts)}")
    else:
        lines.append("POS: flat")

    for underlying, opts in stock_opts.items():
        u_mid = mid(ex.book(underlying))
        if u_mid is None:
            continue
        futs = stock_futs.get(underlying, [])
        delta = compute_stock_delta(pos, underlying, opts, futs, u_mid)
        if abs(delta) > 0.1:
            lines.append(f"DELTA {underlying}: {delta:+.1f} (stock={pos.get(underlying):+d} dual={pos.get(underlying + '_DUAL'):+d} futs={sum(pos.get(f) for f in futs):+d})")

    if primary_fut and ob5x_futs:
        pfb = ex.book(primary_fut)
        if has_top(pfb):
            tau = time_to_expiry(insts[primary_fut].expiry)
            if tau > 0:
                idx_val = mid(pfb) / exp(RATE * tau)
                idx_delta = compute_index_delta(pos, idx_opts, ob5x_futs, ETF_M, idx_val)
                etf_pos = pos.get("OB5X_ETF")
                fut_pos = sum(pos.get(f) for f in ob5x_futs)
                lines.append(f"DELTA OB5X: {idx_delta:+.1f} (etf={etf_pos:+d}*{ETF_M}={ETF_M*etf_pos:+.1f} futs={fut_pos:+d})")

    for liquid, dual in duals:
        lp, dp = pos.get(liquid), pos.get(dual)
        if lp != 0 or dp != 0:
            lines.append(f"DUAL {liquid}: liq={lp:+d} dual={dp:+d} net={lp+dp:+d}")

    opt_positions = []
    for oid in sorted(insts):
        p = pos.get(oid)
        if p != 0 and (insts[oid].instrument_type == InstrumentType.STOCK_OPTION or insts[oid].instrument_type == InstrumentType.INDEX_OPTION):
            opt_positions.append(f"{oid}={p:+d}")
    if opt_positions:
        lines.append(f"OPTS: {' '.join(opt_positions)}")

    log.info("\n".join(lines))
    return pnl


def main():
    e = Ex()
    insts, duals, ob5x_futs, stock_futs, stock_opts, idx_opts, option_pairs, all_options, primary_fut = discover(e)

    const_idx: float | None = None
    prev_pnl: float | None = None
    opt_cursor = 0
    dual_cursor = 0
    arb_cursor = 0
    iteration = 0

    log.info(f"primary_fut={primary_fut}, {len(all_options)} options, {len(duals)} dual pairs")

    while True:
        try:
            if not e.is_connected():
                log.warning("disconnected, reconnecting...")
                e.reconnect()
                insts, duals, ob5x_futs, stock_futs, stock_opts, idx_opts, option_pairs, all_options, primary_fut = discover(e)
                opt_cursor = 0
                dual_cursor = 0
                arb_cursor = 0
                time.sleep(2)
                continue

            pos = Pos(e.get_positions())
            iteration += 1

            if iteration % 5 == 1:
                const_idx = compute_constituent_index(e)

            tau = 0.0
            fut_idx = None
            if primary_fut:
                pfb = e.book(primary_fut)
                if has_top(pfb):
                    tau = time_to_expiry(insts[primary_fut].expiry)
                    if tau > 0:
                        fut_idx = mid(pfb) / exp(RATE * tau)

            pricing_idx = fut_idx or const_idx

            if duals:
                pair = duals[dual_cursor % len(duals)]
                run_dual_listing(e, pair[0], pair[1], pos, insts)
                liquid, dual = pair
                if liquid not in stock_opts:
                    net = pos.get(liquid) + pos.get(dual)
                    if abs(net) > 1:
                        lb2 = e.book(liquid)
                        if has_top(lb2):
                            if net > 0:
                                hv = min(abs(net), pos.hr(liquid, "ask"))
                                if hv > 0:
                                    e.cancel(liquid)
                                    e.insert(liquid, lb2.bids[0].price, hv, "ask", "ioc")
                                    pos.fill(liquid, hv, "ask")
                            else:
                                hv = min(abs(net), pos.hr(liquid, "bid"))
                                if hv > 0:
                                    e.cancel(liquid)
                                    e.insert(liquid, lb2.asks[0].price, hv, "bid", "ioc")
                                    pos.fill(liquid, hv, "bid")
                dual_cursor += 1

            run_etf_quoting(e, primary_fut, insts, pos, const_idx, tau)

            if all_options:
                for i in range(OPTIONS_PER_ITER):
                    idx = (opt_cursor + i) % len(all_options)
                    oid, opt, base = all_options[idx]
                    if base == "OB5X":
                        u_mid = pricing_idx
                    else:
                        u_mid = mid(e.book(base)) if base in insts else None
                    if u_mid is not None:
                        quote_single_option(e, oid, opt, u_mid, pos, insts)
                opt_cursor = (opt_cursor + OPTIONS_PER_ITER) % max(1, len(all_options))

            if iteration % 3 == 0:
                unwind_index_options(e, idx_opts, pos)

            if iteration % 4 == 0:
                run_cross_arb(e, ob5x_futs, stock_futs, option_pairs, insts, pos, arb_cursor)
                arb_cursor += 1

            hedge_all_deltas(e, insts, stock_opts, stock_futs, idx_opts, ob5x_futs, primary_fut, pos)

            if iteration % DIAG_INTERVAL == 0:
                prev_pnl = run_diagnostics(e, pos, insts, stock_opts, stock_futs, idx_opts, ob5x_futs, primary_fut, duals, prev_pnl, iteration)

            time.sleep(LOOP_SLEEP)

        except Exception as exc:
            log.error(f"error: {exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
