from datetime import datetime, timedelta


def time_to_expiry(expiry) -> float:
    # Years remaining until expiry, used as T in the option pricing formulas.
    return (expiry - datetime.now()) / timedelta(days=1) / 365
