"""Edit and cancel open orders through the same HTTP API as buy and sell."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from autotrade.broker.client import EasyTraderClient
from autotrade.broker.constants import TEHRAN_TZ
from autotrade.broker.errors import EasyApiError
from autotrade.broker.orders import LiveOrder, parse_live_order
from autotrade.models import PriceMode, Side
from autotrade.order import OrderError, TradeError
from autotrade.trading.prepare import PrepareError, validate_limit_terms
from autotrade.trading.price import PriceError, resolve_price
from autotrade.trading.submit import classify_submit_response

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EditResult:
    order_id: str
    new_order_id: str | None
    symbol: str
    side: Side
    quantity: int
    price: int
    payload: dict[str, Any]
    dry_run: bool


@dataclass(frozen=True)
class CancelResult:
    order_id: str
    symbol: str
    filled: int
    status: str
    outcome: str
    dry_run: bool


def list_live_orders(client: EasyTraderClient) -> list[LiveOrder]:
    rows = client.list_orders()
    orders: list[LiveOrder] = []
    for item in rows:
        try:
            orders.append(parse_live_order(item))
        except ValueError as exc:
            logger.warning("Skipping an order row: %s", exc)
    return orders


def find_live_order(client: EasyTraderClient, order_id: str) -> LiveOrder:
    target = (order_id or "").strip()
    if not target:
        raise OrderError("set --order-id")
    for order in list_live_orders(client):
        if order.id == target:
            return order
    raise OrderError(f"order {target} not found")


def _coerce_mode(price_mode: PriceMode | str | None) -> PriceMode | None:
    if price_mode is None or isinstance(price_mode, PriceMode):
        return price_mode
    try:
        return PriceMode(str(price_mode).strip().lower())
    except ValueError as exc:
        raise OrderError(f"unknown price mode {price_mode!r}") from exc


def resolve_edit_price(
    md: dict[str, Any],
    order: LiveOrder,
    price_mode: PriceMode | None,
    price: int | None,
) -> int:
    if price_mode is None and price is None:
        if order.price <= 0:
            raise PrepareError("order price is missing")
        return order.price
    mode = price_mode if price_mode is not None else PriceMode.FIXED
    try:
        resolved, _used = resolve_price(
            md, side=order.side, price_mode=mode, fixed_price=price or 0
        )
    except PriceError as exc:
        raise PrepareError(str(exc)) from exc
    return resolved


def resolve_edit_quantity(order: LiveOrder, quantity: int | None) -> int:
    """Quantity of the unfilled remainder. ``-q`` replaces that remainder."""
    if quantity is None:
        return order.remainder
    if quantity <= 0:
        raise OrderError("quantity must be > 0")
    return quantity


def prepare_edit(
    client: EasyTraderClient,
    order_id: str,
    *,
    price_mode: PriceMode | str | None = None,
    price: int | None = None,
    quantity: int | None = None,
    now: datetime | None = None,
) -> EditResult:
    order = find_live_order(client, order_id)
    order.refuse_edit()
    mode = _coerce_mode(price_mode)
    try:
        symbol = client.find_symbol_by_isin(order.isin)
        md = client.market_data(order.isin)
    except EasyApiError as exc:
        raise PrepareError(f"Order prep failed: {exc}") from exc
    final_price = resolve_edit_price(md, order, mode, price)
    final_qty = resolve_edit_quantity(order, quantity)
    validate_limit_terms(
        price=final_price,
        quantity=final_qty,
        side=order.side,
        symbol=symbol,
        md=md,
    )
    commission = client.commission_rate(md, order.side)
    symbol_name = order.symbol or str(symbol.get("symbolName") or order.isin)
    payload = EasyTraderClient.build_modify_payload(
        side=order.side,
        isin=order.isin,
        symbol_name=symbol_name,
        quantity=final_qty,
        price=final_price,
        commission=commission,
        parent_id=order.id,
        validity_type=order.validity_type,
        validity_date=order.validity_date,
        now=now or datetime.now(TEHRAN_TZ),
    )
    logger.info(
        "Prepared edit %s: open qty %s @ %s (filled %s of %s stays filled)",
        order.id,
        final_qty,
        final_price,
        order.filled,
        order.quantity,
    )
    return EditResult(
        order_id=order.id,
        new_order_id=None,
        symbol=symbol_name,
        side=order.side,
        quantity=final_qty,
        price=final_price,
        payload=payload,
        dry_run=True,
    )


def apply_edit(client: EasyTraderClient, plan: EditResult) -> EditResult:
    """Send the modify once. An accepted edit is not retried."""
    resp = client.modify_order(plan.payload)
    outcome = classify_submit_response(resp)
    if not outcome.ok:
        code = outcome.code if outcome.code is not None else "-"
        message = outcome.message or "broker did not accept the edit"
        raise TradeError(f"Edit rejected (code {code}): {message}")
    logger.info("Edit accepted parentId=%s id=%s", plan.order_id, outcome.order_id or "-")
    return EditResult(
        order_id=plan.order_id,
        new_order_id=outcome.order_id,
        symbol=plan.symbol,
        side=plan.side,
        quantity=plan.quantity,
        price=plan.price,
        payload=plan.payload,
        dry_run=False,
    )


def run_edit(
    client: EasyTraderClient,
    order_id: str,
    *,
    price_mode: PriceMode | str | None = None,
    price: int | None = None,
    quantity: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
) -> EditResult:
    plan = prepare_edit(
        client,
        order_id,
        price_mode=price_mode,
        price=price,
        quantity=quantity,
        now=now,
    )
    if dry_run:
        logger.info("Dry run — modify not sent for %s.", order_id)
        return plan
    return apply_edit(client, plan)


def run_cancel(
    client: EasyTraderClient,
    order_id: str,
    *,
    dry_run: bool = False,
    confirm_timeout: float = 5.0,
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> CancelResult:
    order = find_live_order(client, order_id)
    order.refuse_cancel()
    if dry_run:
        logger.info("Dry run — cancel not sent for %s.", order.id)
        return CancelResult(
            order_id=order.id,
            symbol=order.symbol,
            filled=order.filled,
            status=order.status,
            outcome="dry-run",
            dry_run=True,
        )
    resp = client.cancel_order(order.id)
    outcome = classify_submit_response(resp)
    if not outcome.ok:
        code = outcome.code if outcome.code is not None else "-"
        message = outcome.message or "broker did not accept the cancel"
        raise TradeError(f"Cancel rejected (code {code}): {message}")
    # One DELETE was sent. OnCanceling means it is in progress, so keep reading
    # the list. Do not send the cancel again.
    deadline = monotonic_fn() + confirm_timeout
    while True:
        try:
            after = list_live_orders(client)
        except EasyApiError as exc:
            raise TradeError(
                f"Cancel was accepted for {order.id}, but the order list could not be read "
                f"to confirm it ({exc}). Not sending the cancel again. Filled {order.filled}."
            ) from exc
        found = next((row for row in after if row.id == order.id), None)
        if found is None:
            logger.info("Cancel confirmed: %s is gone. Filled %s.", order.id, order.filled)
            return CancelResult(
                order_id=order.id,
                symbol=order.symbol,
                filled=order.filled,
                status="gone",
                outcome="gone",
                dry_run=False,
            )
        if found.cancelled:
            logger.info(
                "Cancel confirmed: %s is %s. Filled %s.",
                order.id,
                found.status,
                found.filled,
            )
            return CancelResult(
                order_id=order.id,
                symbol=found.symbol or order.symbol,
                filled=found.filled,
                status=found.status,
                outcome="cancelled",
                dry_run=False,
            )
        if found.cancel_pending and monotonic_fn() < deadline:
            sleep_fn(0.4)
            continue
        filled = found.filled
        raise TradeError(
            f"Cancel was accepted for {order.id}, but the order is still {found.status}. "
            f"Not sending the cancel again. Filled {filled}."
        )


def summarize_edit(result: EditResult) -> str:
    headline = (
        f"{result.symbol} {result.side.value} open qty {result.quantity} @ {result.price}"
    )
    if result.dry_run:
        body = json.dumps(result.payload, ensure_ascii=False, indent=2)
        return f"Dry run — modify not sent for {result.order_id}: {headline}\n{body}"
    new_id = result.new_order_id or "-"
    return f"Edited {result.order_id} → {new_id}: {headline}"


def summarize_cancel(result: CancelResult) -> str:
    if result.dry_run:
        return (
            f"Dry run — cancel not sent. {result.order_id} {result.symbol} "
            f"filled {result.filled} status {result.status}"
        )
    return f"Cancelled {result.order_id}: filled {result.filled} ({result.outcome})"


__all__ = [
    "CancelResult",
    "EditResult",
    "run_cancel",
    "run_edit",
    "summarize_cancel",
    "summarize_edit",
]
