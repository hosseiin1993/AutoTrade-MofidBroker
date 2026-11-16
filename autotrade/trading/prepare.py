from __future__ import annotations

import logging
from typing import Any

from autotrade.broker.client import EasyTraderClient, buying_power, order_total_value
from autotrade.broker.constants import MIN_NOTIONAL_RIAL
from autotrade.broker.errors import EasyApiError
from autotrade.models import PreparedOrder, PriceMode, Side
from autotrade.trading.price import PriceError, resolve_price

logger = logging.getLogger(__name__)


class PrepareError(RuntimeError):
    pass


def _rial(amount: int) -> str:
    return f"{int(amount):,} Rial ({int(amount) // 10:,} Toman)"


def _positive(source: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, float) and value.is_integer() and int(value) > 0:
            return int(value)
    return None


def validate_volume(md: dict[str, Any], *, side: Side, quantity: int) -> None:
    if side is Side.BUY:
        min_q = md.get("minValidBuyVolume")
        max_q = md.get("maxValidBuyVolume")
    else:
        min_q = md.get("minValidSellVolume") or md.get("minValidBuyVolume")
        max_q = md.get("maxValidSellVolume") or md.get("maxValidBuyVolume")
    if min_q and int(quantity) < int(min_q):
        raise PrepareError(f"quantity {quantity} below min volume {min_q}.")
    if max_q and int(quantity) > int(max_q):
        raise PrepareError(f"quantity {quantity} above max volume {max_q}.")


def validate_limit_terms(
    *,
    price: int,
    quantity: int,
    side: Side,
    symbol: dict[str, Any],
    md: dict[str, Any],
) -> None:
    """Band / lot / tick / volume / notional checks used when editing an open order."""
    low = _positive(md, "lowAllowedPrice", "minDailyPrice")
    high = _positive(md, "highAllowedPrice", "maxDailyPrice")
    if low is None or high is None:
        raise PrepareError("daily price band is missing for this symbol")
    if price < low or price > high:
        raise PrepareError(f"price {price} is outside the daily band {low}–{high}")

    lot = _positive(symbol, "minDealableCount", "lotSize") or _positive(
        md, "minDealableCount", "lotSize"
    )
    if lot and quantity % lot != 0:
        raise PrepareError(f"quantity {quantity} is not a multiple of lot size {lot}")

    tick = _positive(symbol, "minDealablePrice") or _positive(md, "minDealablePrice")
    if tick and tick > 1 and price % tick != 0:
        raise PrepareError(f"price {price} is not a multiple of the price step {tick}")

    validate_volume(md, side=side, quantity=quantity)

    notional = price * quantity
    if notional < MIN_NOTIONAL_RIAL:
        raise PrepareError(
            f"order notional {notional:,} Rial is below the {MIN_NOTIONAL_RIAL:,} Rial minimum"
        )


def prepare_order(
    client: EasyTraderClient,
    *,
    side: Side,
    symbol: str,
    quantity: int,
    price_mode: PriceMode = PriceMode.AUTO,
    price: int = 0,
) -> PreparedOrder:
    if not symbol:
        raise PrepareError("No symbol configured.")
    if quantity <= 0:
        raise PrepareError("quantity must be > 0.")

    try:
        sym = client.find_symbol(symbol)
        isin = sym["symbolIsin"]
        md = client.market_data(isin)
        final_price, resolved_mode = resolve_price(
            md, side=side, price_mode=price_mode, fixed_price=price
        )
        commission = client.commission_rate(md, side)
    except (EasyApiError, PriceError, KeyError) as exc:
        raise PrepareError(f"Order prep failed: {exc}") from exc

    validate_volume(md, side=side, quantity=quantity)

    value = order_total_value(
        side=side, price=final_price, quantity=int(quantity), commission=commission
    )

    power: int | None = None
    try:
        power = buying_power(client.money())
    except EasyApiError as exc:
        logger.warning("Account balance unavailable (%s).", exc)

    prepared = PreparedOrder(
        side=side,
        symbol=symbol,
        isin=isin,
        quantity=int(quantity),
        price=final_price,
        price_mode=resolved_mode,
        commission=commission,
        order_value=value,
        high_allowed=md.get("highAllowedPrice"),
        low_allowed=md.get("lowAllowedPrice"),
        closing=md.get("closingPrice"),
        buying_power=power,
        market_data=md,
    )

    if side is Side.BUY and power is not None and value > power:
        logger.warning(
            "Order value %s exceeds buying power %s — broker may reject.",
            _rial(value),
            _rial(power),
        )

    logger.info(
        "Prepared %s: %s x%d @ %s [%s] value=%s",
        side.value,
        symbol,
        quantity,
        _rial(final_price),
        resolved_mode.value,
        _rial(value),
    )
    return prepared


def log_order_review(prepared: PreparedOrder) -> None:
    logger.info("Order review:")
    logger.info("  side          %s (%s)", prepared.side.value, prepared.side.label_fa)
    logger.info("  symbol        %s (%s)", prepared.symbol, prepared.isin)
    logger.info("  quantity      %s", f"{prepared.quantity:,}")
    logger.info(
        "  price         %s [%s]",
        _rial(prepared.price),
        prepared.price_mode.value,
    )
    logger.info(
        "  commission    %.4f%% → %s",
        prepared.commission * 100,
        _rial(round(prepared.price * prepared.quantity * prepared.commission)),
    )
    logger.info("  order value   %s", _rial(prepared.order_value))
    if prepared.buying_power is None:
        logger.warning("  buying power  unknown")
    else:
        logger.info("  buying power  %s", _rial(prepared.buying_power))
        if prepared.side is Side.BUY:
            after = prepared.buying_power - prepared.order_value
            logger.info("  balance after %s", _rial(after))
