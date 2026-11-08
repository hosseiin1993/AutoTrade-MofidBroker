from __future__ import annotations

from typing import Any

from autotrade.models import PriceMode, Side


class PriceError(ValueError):
    pass


def resolve_price(
    md: dict[str, Any],
    *,
    side: Side,
    price_mode: PriceMode,
    fixed_price: int = 0,
) -> tuple[int, PriceMode]:
    """
    Pick the limit price from live market data.

    auto → ceiling (buy) / floor (sell)
    ceiling → highAllowedPrice
    floor → lowAllowedPrice
    reference → closingPrice
    fixed → caller-supplied PRICE
    """
    mode = price_mode.resolve_for(side)

    if mode is PriceMode.FIXED:
        p = int(fixed_price or 0)
        if p <= 0:
            raise PriceError("PRICE_MODE=fixed requires PRICE > 0.")
        return p, mode

    if mode is PriceMode.CEILING:
        p = int(md.get("highAllowedPrice") or 0)
        if p <= 0:
            raise PriceError("highAllowedPrice missing/zero.")
        return p, mode

    if mode is PriceMode.FLOOR:
        p = int(md.get("lowAllowedPrice") or 0)
        if p <= 0:
            raise PriceError("lowAllowedPrice missing/zero.")
        return p, mode

    if mode is PriceMode.REFERENCE:
        p = int(md.get("closingPrice") or 0)
        if p <= 0:
            raise PriceError("closingPrice missing/zero.")
        return p, mode

    raise PriceError(f"Unknown price mode {price_mode!r}.")
