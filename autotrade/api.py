"""Small helpers for embedding AutoTrade in another project."""

from __future__ import annotations

from autotrade.config import Settings, get_settings
from autotrade.logging_setup import setup_logging
from autotrade.models import PriceMode, Side
from autotrade.order import Order, with_account
from autotrade.session import place_order


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
