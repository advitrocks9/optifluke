# All exchange calls share one token-bucket budget (18/s) so the strategies,
# hedging, and discovery never collectively exceed the API rate limit.

import time

from optibook.synchronous_client import Exchange


class RateLimiter:
    def __init__(self, rate: int = 18):
        self._rate = rate
        self._tokens = float(rate)
        self._max = float(rate)
        self._last = time.monotonic()

    def acquire(self, n: int = 1):
        while True:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._max, self._tokens + elapsed * self._rate)
            if self._tokens >= n:
                self._tokens -= n
                return
            wait = (n - self._tokens) / self._rate
            time.sleep(wait)


class Ex:
    def __init__(self):
        self._inner = Exchange()
        self._inner.connect()
        self._rl = RateLimiter(18)

    def reconnect(self):
        self._inner = Exchange()
        self._inner.connect()

    def is_connected(self):
        return self._inner.is_connected()

    def get_instruments(self):
        self._rl.acquire()
        return self._inner.get_instruments()

    def get_positions(self):
        self._rl.acquire()
        return self._inner.get_positions()

    def get_pnl(self):
        self._rl.acquire()
        return self._inner.get_pnl()

    def book(self, iid: str):
        self._rl.acquire()
        return self._inner.get_last_price_book(iid)

    def insert(self, iid: str, price: float, volume: int, side: str, otype: str):
        self._rl.acquire()
        return self._inner.insert_order(iid, price=price, volume=volume, side=side, order_type=otype)

    def cancel(self, iid: str):
        self._rl.acquire()
        self._inner.delete_orders(iid)
