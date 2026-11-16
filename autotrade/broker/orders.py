"""Parse order rows from GET /core/api/order."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autotrade.broker.constants import (
    CANCELLED_ORDER_STATES,
    DELETABLE_ORDER_STATES,
    EXECUTED_ORDER_STATES,
    OPEN_ORDER_STATES,
    ORDER_STATE_NAMES,
    ORDER_STATE_ON_CANCELING,
    VALIDITY_TYPE_DAY,
)
from autotrade.models import Side
from autotrade.order import OrderError

_OPEN_NAMES = {ORDER_STATE_NAMES[code].casefold() for code in OPEN_ORDER_STATES}
_CANCELLED_NORM = {
    "".join(ch for ch in ORDER_STATE_NAMES[code].casefold() if ch.isalnum())
    for code in CANCELLED_ORDER_STATES
}
_STATE_BY_NAME = {name.casefold(): code for code, name in ORDER_STATE_NAMES.items()}


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
    return None


def _norm_status(value: str) -> str:
    return "".join(ch for ch in value.casefold() if ch.isalnum())


@dataclass(frozen=True)
class LiveOrder:
    id: str
    symbol: str
    isin: str
    side: Side
    quantity: int
    filled: int
    price: int
    status: str
    state: int | None = None
    parent_id: str | None = None
    validity_type: int = VALIDITY_TYPE_DAY
    validity_date: str | None = None

    @property
    def remainder(self) -> int:
        return max(self.quantity - self.filled, 0)

    @property
    def status_norm(self) -> str:
        return _norm_status(self.status)

    @property
    def cancelled(self) -> bool:
        if self.state in CANCELLED_ORDER_STATES:
            return True
        return self.status_norm in _CANCELLED_NORM

    @property
    def fully_executed(self) -> bool:
        if self.quantity > 0 and self.filled >= self.quantity:
            return True
        if self.state in EXECUTED_ORDER_STATES:
            return True
        if self.status_norm == "orderexecuted":
            return True
        return self.status_norm == "done" and self.remainder <= 0

    @property
    def cancel_pending(self) -> bool:
        """Broker accepted a cancel and has not finished it yet (OnCanceling)."""
        return (
            self.state == ORDER_STATE_ON_CANCELING or self.status_norm == "oncanceling"
        )

    def _state_allows(self, allowed: frozenset[int], names: set[str]) -> bool:
        if self.state in allowed:
            return True
        if self.state is None and (
            not self.status or self.status == "Unknown" or self.status.casefold() in names
        ):
            return True
        return False

    @property
    def editable(self) -> bool:
        if self.cancelled or self.fully_executed or self.remainder <= 0:
            return False
        return self._state_allows(OPEN_ORDER_STATES, _OPEN_NAMES)

    @property
    def cancellable(self) -> bool:
        """Open remainder the ticket can delete. A Modify parent is not actionable."""
        if self.cancelled or self.fully_executed or self.remainder <= 0:
            return False
        return self._state_allows(DELETABLE_ORDER_STATES, _OPEN_NAMES | {"error"})

    def refuse_edit(self) -> None:
        if self.cancelled:
            raise OrderError(f"order {self.id} is cancelled ({self.status})")
        if self.fully_executed or self.remainder <= 0:
            raise OrderError(
                f"order {self.id} is fully executed "
                f"(filled {self.filled} of {self.quantity})"
            )
        if not self.editable:
            raise OrderError(
                f"order {self.id} is not open ({self.status}); "
                "only the unfilled remainder of an open order can be edited"
            )

    def refuse_cancel(self) -> None:
        if self.cancelled:
            raise OrderError(f"order {self.id} is already cancelled ({self.status})")
        if self.fully_executed or self.remainder <= 0:
            raise OrderError(
                f"order {self.id} is fully executed "
                f"(filled {self.filled} of {self.quantity}); nothing left to cancel"
            )
        if not self.cancellable:
            raise OrderError(
                f"order {self.id} cannot be cancelled ({self.status})"
            )


def _side(value: object) -> Side | None:
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"buy", "0"}:
            return Side.BUY
        if text in {"sell", "1"}:
            return Side.SELL
        return None
    code = _as_int(value)
    if code == 0:
        return Side.BUY
    if code == 1:
        return Side.SELL
    return None


def _filled(row: dict[str, Any]) -> int:
    explicit = 0
    for key in ("executedQuantity", "ExecutedQuantity", "volumeDone"):
        number = _as_int(row.get(key))
        if number is not None and number > explicit:
            explicit = number
    traded = 0
    trades = row.get("trades")
    if isinstance(trades, list):
        for trade in trades:
            if not isinstance(trade, dict) or trade.get("isCancel"):
                continue
            qty = _as_int(trade.get("quantity"))
            if qty is not None and qty > 0:
                traded += qty
    return max(explicit, traded)


def _row_dict(item: dict[str, Any]) -> dict[str, Any]:
    nested = item.get("order")
    if not isinstance(nested, dict):
        return item
    merged = dict(nested)
    for key, value in item.items():
        if key == "order":
            continue
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def parse_live_order(item: dict[str, Any]) -> LiveOrder:
    if not isinstance(item, dict):
        raise ValueError("order row is not an object")
    row = _row_dict(item)
    raw_id = row.get("id") or row.get("orderId")
    if raw_id is None or str(raw_id).strip() == "":
        raise ValueError("order row is missing an id")
    side = _side(row.get("side"))
    if side is None:
        raise ValueError(f"order {raw_id} is missing a side")
    quantity = _as_int(row.get("quantity"))
    price = _as_int(row.get("price"))
    if quantity is None or price is None:
        raise ValueError(f"order {raw_id} is missing quantity or price")

    state_value = row.get("orderState")
    state = _as_int(state_value)
    status_text = str(row.get("orderStateStr") or row.get("stateStr") or "").strip()
    if state is None and isinstance(state_value, str) and state_value.strip():
        status_text = status_text or state_value.strip()
        state = _STATE_BY_NAME.get(state_value.strip().casefold())
    status = status_text or (
        ORDER_STATE_NAMES.get(state, str(state)) if state is not None else "Unknown"
    )

    validity = _as_int(row.get("validityType"))
    validity_date = row.get("validityDate")
    parent = row.get("parentId")
    return LiveOrder(
        id=str(raw_id).strip(),
        symbol=str(row.get("symbolName") or row.get("symbol") or "").strip(),
        isin=str(row.get("symbolIsin") or row.get("isin") or "").strip(),
        side=side,
        quantity=quantity,
        filled=_filled(row),
        price=price,
        status=status,
        state=state,
        parent_id=str(parent).strip() if parent not in (None, "") else None,
        validity_type=VALIDITY_TYPE_DAY if validity is None else validity,
        validity_date=str(validity_date) if validity_date not in (None, "") else None,
    )


def format_orders(orders: list[LiveOrder]) -> str:
    if not orders:
        return "No open or today's orders."
    lines = ["id\tsymbol\tside\tqty\tfilled\tprice\tstatus"]
    for order in orders:
        lines.append(
            f"{order.id}\t{order.symbol}\t{order.side.value}\t"
            f"{order.quantity}\t{order.filled}\t{order.price}\t{order.status}"
        )
    return "\n".join(lines)
