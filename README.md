# optifluke

A market-making bot for Optiver's Optibook simulator, built for the Imperial Optiver Trading Academy 2026. It quotes and arbitrages four instrument families at once and finished 9th of 30+ teams.

## The one number that shaped everything

Optibook caps you at about 25 exchange calls per second, and a read costs the same as a write. Go over and the exchange drops your connection. With four strategies all wanting to read books and fire orders on every pass, that budget, not the market, is the real adversary.

Every design choice in this repo traces back to it:

- **One connection.** Never open a second.
- **A token bucket in front of every call** (`exchange.py`). Reads and writes draw from the same budget, so the bot cannot burst past the cap. It runs at 18 calls per second to leave headroom for reconnects.
- **Strategies take turns** (`run.py`). They run round-robin inside each loop pass instead of all firing at once, so none starves the others.
- **Never spend a call on what you already know** (`positions.py`). Positions are tracked locally and only refetched from the exchange right before hedging, the one place where stale data costs real money.

## The loop

```
connect once, wrap every call in the rate limiter
discover instruments: dual pairs, futures, options, the ETF and its index
repeat:
    dual listing   arb the pair, quote the illiquid leg
    ETF / future   price the ETF off the future, quote around it
    options        quote a few contracts, advancing a cursor each pass
    cross arb      basis and put-call parity
    hedge          flatten net delta with IOC orders past a threshold
    diagnostics    PnL, positions, deltas every N passes
```

Options are quoted a slice at a time on a rotating cursor, so the whole chain gets covered over several passes without dumping every quote at once. Cross-arb and index-option unwinding run every few passes, not every one, to keep call volume flat.

## The strategies

**Dual listing.** The same name trades on two venues. When the books cross, the bot arbs them with paired IOC orders. Otherwise it quotes the thinner leg around the liquid mid and skews size by inventory.

**ETF and future.** The ETF tracks an index that also has a future. The bot discounts the future to spot by cost-of-carry, applies the ETF multiplier and constant to get fair value, and quotes a bid and ask around it.

**Option market making.** Black-Scholes sets the theo. The quoted edge grows with the option's vega and the current book spread, then skews by inventory so the bot leans against its own position.

**Cross-instrument arb.** No-arbitrage links between related instruments. Basis (stock versus its future) and put-call parity (call, put, underlying) run in the live rotation; a calendar spread (future versus future) is implemented but kept out of the hot loop. When a link drifts past its threshold, the bot crosses it with IOC orders.

## Staying flat

Pricing is half the job. The other half is not blowing up on a one-sided fill. Delta is netted per underlying, across the stock, its dual listing, and its futures for single names, and across the ETF and index options for the index, then flattened with IOC orders whenever it crosses the hedge threshold (`hedging.py`).

## Running it

It does not run on its own. It imports Optiver's private `optibook` package, which is not public, and expects the academy's simulated exchange on the other end. What is here is the strategy and the systems work around it.

## Team

Advit Arora ([advitrocks9](https://github.com/advitrocks9)), chapmaj21 ([chapmaj21](https://github.com/chapmaj21)), and Maxim Subbotsky ([maximsub](https://github.com/maximsub)). Imperial Optiver Trading Academy 2026, 9th of 30+ teams.
