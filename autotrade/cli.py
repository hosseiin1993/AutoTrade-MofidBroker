from __future__ import annotations

import logging
from typing import Annotated

import typer

from autotrade.broker.errors import EasyApiError
from autotrade.browser import BrowserGone
from autotrade.config import get_settings
from autotrade.logging_setup import setup_logging
from autotrade.models import PriceMode, Side
from autotrade.order import Order, OrderError, TradeError, with_account
from autotrade.session import place_order
from autotrade.trading.prepare import PrepareError

logger = logging.getLogger(__name__)

app = typer.Typer(
    add_completion=False,
    help="Place buy or sell orders on Mofid EasyTrader.",
    no_args_is_help=True,
)

Username = Annotated[
    str | None,
    typer.Option("--user", help="Broker username (overrides MOFID_USER)"),
]
Password = Annotated[
    str | None,
    typer.Option("--password", help="Broker password (overrides MOFID_PASS)"),
]
SymbolOpt = Annotated[
    str | None, typer.Option("--symbol", help="Persian symbol name")
]
QuantityOpt = Annotated[
    int | None, typer.Option("--quantity", "-q", help="Share count")
]
PriceModeOpt = Annotated[
    PriceMode | None,
    typer.Option(
        "--price-mode",
        help="auto|ceiling|floor|reference|fixed (auto = ceiling buy / floor sell)",
    ),
]
PriceOpt = Annotated[
    int | None,
    typer.Option("--price", "-p", help="Limit price (Rial) when --price-mode=fixed"),
]
TimeOpt = Annotated[
    str | None,
    typer.Option(
        "--time",
        "-t",
        help="Broker clock target HH:MM:SS, or 'now' to submit immediately",
    ),
]
DryRunOpt = Annotated[
    bool, typer.Option("--dry-run", help="Prepare only — do not wait or submit")
]
NoVerifyOpt = Annotated[
    bool,
    typer.Option("--no-verify", help="Do not poll the order list after submit"),
]
NoTokenCacheOpt = Annotated[
    bool,
    typer.Option("--no-token-cache", help="Force a fresh Playwright login"),
]
SideOpt = Annotated[
    Side | None,
    typer.Option("--side", "-s", help="buy or sell (default: SIDE env / buy)"),
]


def _go(
    *,
    side: Side | None,
    username: str | None,
    password: str | None,
    symbol: str | None,
    quantity: int | None,
    price_mode: PriceMode | None,
    price: int | None,
    time_: str | None,
    dry_run: bool,
    no_verify: bool,
    no_token_cache: bool,
) -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_file)
    try:
        account = with_account(settings, username, password)
        order = Order.resolve(
            account,
            side=side,
            symbol=symbol,
            quantity=quantity,
            price_mode=price_mode,
            price=price,
            target_time=time_,
            dry_run=dry_run,
            verify=False if no_verify else None,
            use_token_cache=False if no_token_cache else None,
        )
        place_order(order, account)
    except OrderError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(2) from exc
    except (TradeError, PrepareError, BrowserGone, EasyApiError, TimeoutError) as exc:
        logger.error("%s", exc)
        raise typer.Exit(1) from exc
    except Exception:
        logger.exception("Unhandled error")
        raise typer.Exit(1)


@app.command("order")
def order_cmd(
    username: Username = None,
    password: Password = None,
    side: SideOpt = None,
    symbol: SymbolOpt = None,
    quantity: QuantityOpt = None,
    price_mode: PriceModeOpt = None,
    price: PriceOpt = None,
    time_: TimeOpt = None,
    dry_run: DryRunOpt = False,
    no_verify: NoVerifyOpt = False,
    no_token_cache: NoTokenCacheOpt = False,
) -> None:
    """Prepare and submit a buy or sell order at the target broker time."""
    _go(
        side=side,
        username=username,
        password=password,
        symbol=symbol,
        quantity=quantity,
        price_mode=price_mode,
        price=price,
        time_=time_,
        dry_run=dry_run,
        no_verify=no_verify,
        no_token_cache=no_token_cache,
    )


@app.command("buy")
def buy_cmd(
    username: Username = None,
    password: Password = None,
    symbol: SymbolOpt = None,
    quantity: QuantityOpt = None,
    price_mode: PriceModeOpt = None,
    price: PriceOpt = None,
    time_: TimeOpt = None,
    dry_run: DryRunOpt = False,
    no_verify: NoVerifyOpt = False,
    no_token_cache: NoTokenCacheOpt = False,
) -> None:
    """Shortcut for `order --side buy`."""
    _go(
        side=Side.BUY,
        username=username,
        password=password,
        symbol=symbol,
        quantity=quantity,
        price_mode=price_mode,
        price=price,
        time_=time_,
        dry_run=dry_run,
        no_verify=no_verify,
        no_token_cache=no_token_cache,
    )


@app.command("sell")
def sell_cmd(
    username: Username = None,
    password: Password = None,
    symbol: SymbolOpt = None,
    quantity: QuantityOpt = None,
    price_mode: PriceModeOpt = None,
    price: PriceOpt = None,
    time_: TimeOpt = None,
    dry_run: DryRunOpt = False,
    no_verify: NoVerifyOpt = False,
    no_token_cache: NoTokenCacheOpt = False,
) -> None:
    """Shortcut for `order --side sell` (auto price = floor)."""
    _go(
        side=Side.SELL,
        username=username,
        password=password,
        symbol=symbol,
        quantity=quantity,
        price_mode=price_mode,
        price=price,
        time_=time_,
        dry_run=dry_run,
        no_verify=no_verify,
        no_token_cache=no_token_cache,
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
