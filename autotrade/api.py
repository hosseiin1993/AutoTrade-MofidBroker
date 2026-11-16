"""Small helpers for embedding AutoTrade in another project."""

from __future__ import annotations

from autotrade.config import Settings, get_settings
from autotrade.logging_setup import setup_logging
from autotrade.models import PriceMode, Side
from autotrade.broker.orders import LiveOrder
from autotrade.order import Order, with_account
from autotrade.session import (
    cancel_account_order,
    edit_account_order,
    list_account_orders,
    place_order,
)
from autotrade.trading.manage import CancelResult, EditResult


def buy(
    symbol: str,
    quantity: int,
    *,
    price_mode: PriceMode | str = PriceMode.AUTO,
    price: int = 0,
    target_time: str = "now",
    dry_run: bool = False,
    verify: bool | None = None,
    username: str | None = None,
    password: str | None = None,
    settings: Settings | None = None,
    configure_logging: bool = True,
) -> None:
    """Place a buy. Credentials come from ``settings`` / ``.env``, or pass both username and password."""
    _run(
        Side.BUY,
        symbol,
        quantity,
        price_mode=price_mode,
        price=price,
        target_time=target_time,
        dry_run=dry_run,
        verify=verify,
        username=username,
        password=password,
        settings=settings,
        configure_logging=configure_logging,
    )


def sell(
    symbol: str,
    quantity: int,
    *,
    price_mode: PriceMode | str = PriceMode.AUTO,
    price: int = 0,
    target_time: str = "now",
    dry_run: bool = False,
    verify: bool | None = None,
    username: str | None = None,
    password: str | None = None,
    settings: Settings | None = None,
    configure_logging: bool = True,
) -> None:
    """Place a sell. Credentials come from ``settings`` / ``.env``, or pass both username and password."""
    _run(
        Side.SELL,
        symbol,
        quantity,
        price_mode=price_mode,
        price=price,
        target_time=target_time,
        dry_run=dry_run,
        verify=verify,
        username=username,
        password=password,
        settings=settings,
        configure_logging=configure_logging,
    )


def _run(
    side: Side,
    symbol: str,
    quantity: int,
    *,
    price_mode: PriceMode | str,
    price: int,
    target_time: str,
    dry_run: bool,
    verify: bool | None,
    username: str | None,
    password: str | None,
    settings: Settings | None,
    configure_logging: bool,
) -> None:
    account = with_account(
        settings if settings is not None else get_settings(),
        username,
        password,
    )
    if configure_logging:
        setup_logging(account.log_level, account.log_file)
    order = Order.resolve(
        account,
        side=side,
        symbol=symbol,
        quantity=quantity,
        price_mode=price_mode,
        price=price,
        target_time=target_time,
        dry_run=dry_run,
        verify=verify,
    )
    place_order(order, account)


def list_orders(
    *,
    username: str | None = None,
    password: str | None = None,
    settings: Settings | None = None,
    configure_logging: bool = True,
    use_token_cache: bool = True,
) -> list[LiveOrder]:
    """List open and today's orders. Credentials come from ``settings`` / ``.env``, or pass both username and password."""
    account = with_account(
        settings if settings is not None else get_settings(),
        username,
        password,
    )
    if configure_logging:
        setup_logging(account.log_level, account.log_file)
    return list_account_orders(account, use_token_cache=use_token_cache)


def edit_order(
    order_id: str,
    *,
    price_mode: PriceMode | str | None = None,
    price: int | None = None,
    quantity: int | None = None,
    dry_run: bool = False,
    username: str | None = None,
    password: str | None = None,
    settings: Settings | None = None,
    configure_logging: bool = True,
    use_token_cache: bool = True,
) -> EditResult:
    """Modify the unfilled remainder of an open order. One request; an accept is not retried."""
    account = with_account(
        settings if settings is not None else get_settings(),
        username,
        password,
    )
    if configure_logging:
        setup_logging(account.log_level, account.log_file)
    return edit_account_order(
        account,
        order_id,
        price_mode=price_mode,
        price=price,
        quantity=quantity,
        dry_run=dry_run,
        use_token_cache=use_token_cache,
    )


def cancel_order(
    order_id: str,
    *,
    dry_run: bool = False,
    username: str | None = None,
    password: str | None = None,
    settings: Settings | None = None,
    configure_logging: bool = True,
    use_token_cache: bool = True,
) -> CancelResult:
    """Cancel an open order, then confirm it is gone or cancelled. An accept is not retried."""
    account = with_account(
        settings if settings is not None else get_settings(),
        username,
        password,
    )
    if configure_logging:
        setup_logging(account.log_level, account.log_file)
    return cancel_account_order(
        account,
        order_id,
        dry_run=dry_run,
        use_token_cache=use_token_cache,
    )
