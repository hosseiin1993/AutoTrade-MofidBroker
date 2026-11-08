"""The order ticket the CLI and the library both build."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time as dt_time

from autotrade.config import Settings, parse_hhmmss
from autotrade.models import PriceMode, Side


class OrderError(ValueError):
    """The order request is incomplete or the clock time is not HH:MM:SS."""


class TradeError(RuntimeError):
    """The session ran, and the order was not submitted or not accepted."""


def with_account(
    settings: Settings,
    username: str | None = None,
    password: str | None = None,
) -> Settings:
    """Settings for this call. A passed username and password replace the saved pair."""
    if (username is None) != (password is None):
        raise OrderError("set username and password together")
    if username is None:
        if not settings.mofid_user or not settings.mofid_pass:
            raise OrderError("set username and password")
        return settings
    user = username.strip()
    if not user or password is None or password == "":
        raise OrderError("set username and password")
    if user == settings.mofid_user and password == settings.mofid_pass:
        return settings
    return settings.model_copy(update={"mofid_user": user, "mofid_pass": password})


@dataclass(frozen=True)
class Order:
    side: Side
    symbol: str
    quantity: int
    price_mode: PriceMode
    price: int
    target_time: dt_time | None
    dry_run: bool = False
    verify: bool = True
    use_token_cache: bool = True

    @staticmethod
    def resolve(
        settings: Settings,
        *,
        side: Side | str | None = None,
        symbol: str | None = None,
        quantity: int | None = None,
        price_mode: PriceMode | str | None = None,
        price: int | None = None,
        target_time: str | None = None,
        dry_run: bool = False,
        verify: bool | None = None,
        use_token_cache: bool | None = None,
    ) -> Order:
        """Overlay call arguments on Settings. Does not touch the broker or Settings.

        Pass ``target_time="now"`` to submit as soon as the order is prepared.
        """
        try:
            if target_time is not None and target_time.strip().lower() == "now":
                when: dt_time | None = None
            elif target_time is None:
                when = settings.target_as_time()
            else:
                when = parse_hhmmss(target_time)
        except ValueError as exc:
            raise OrderError(str(exc)) from exc

        chosen_symbol = (symbol if symbol is not None else settings.symbol).strip()
        chosen_qty = quantity if quantity is not None else settings.quantity
        if not chosen_symbol:
            raise OrderError("set --symbol or SYMBOL in .env")
        if chosen_qty <= 0:
            raise OrderError("set --quantity or QUANTITY > 0")

        return Order(
            side=_coerce(Side, side if side is not None else settings.side),
            symbol=chosen_symbol,
            quantity=chosen_qty,
            price_mode=_coerce(
                PriceMode, price_mode if price_mode is not None else settings.price_mode
            ),
            price=price if price is not None else settings.price,
            target_time=when,
            dry_run=dry_run,
            verify=settings.verify_order if verify is None else verify,
            use_token_cache=(
                settings.token_cache if use_token_cache is None else use_token_cache
            ),
        )


def _coerce(kind: type[Side] | type[PriceMode], value: Side | PriceMode | str) -> Side | PriceMode:
    if isinstance(value, kind):
        return value
    try:
        return kind(str(value).strip().lower())
    except ValueError as exc:
        raise OrderError(str(exc)) from exc
