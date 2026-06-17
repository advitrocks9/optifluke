from config import POSITION_LIMIT


class Pos:
    def __init__(self, raw: dict):
        self._p = dict(raw)

    def sync(self, raw: dict):
        # Replace the cache from a fresh exchange snapshot so callers
        # do not reach into self._p directly.
        self._p = dict(raw)

    def get(self, iid: str) -> int:
        return self._p.get(iid, 0)

    def hr(self, iid: str, side: str) -> int:
        p = self.get(iid)
        return max(0, POSITION_LIMIT - p) if side == "bid" else max(0, POSITION_LIMIT + p)

    def fill(self, iid: str, vol: int, side: str):
        if side == "bid":
            self._p[iid] = self.get(iid) + vol
        else:
            self._p[iid] = self.get(iid) - vol

    def items(self):
        return self._p.items()
