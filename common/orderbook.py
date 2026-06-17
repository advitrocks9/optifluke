from math import floor, ceil


def has_top(book) -> bool:
    return bool(book and book.bids and book.asks)


def mid(book):
    return (book.bids[0].price + book.asks[0].price) / 2.0 if has_top(book) else None


def round_down(price, tick):
    return floor(price / tick) * tick


def round_up(price, tick):
    return ceil(price / tick) * tick
