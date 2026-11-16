from __future__ import annotations

import logging
import signal
from typing import Any

from autotrade.auth.token_cache import (
    account_fingerprint,
    clear_token,
    describe,
    load_token,
    save_token,
)
from autotrade.broker.client import EasyTraderClient, extract_auth_token
from autotrade.broker.errors import ApiAuthError, EasyApiError
from autotrade.broker.transport import PlaywrightTransport
from autotrade.browser import (
    cleanup_all,
    dismiss_announcement,
    launch_browser,
    login,
)
from autotrade.config import Settings, get_settings
from autotrade.broker.orders import LiveOrder
from autotrade.models import PriceMode
from autotrade.order import Order, TradeError
from autotrade.trading.clock import ApiClock, wait_until
from autotrade.trading.manage import (
    CancelResult,
    EditResult,
    list_live_orders,
    run_cancel,
    run_edit,
)
from autotrade.trading.prepare import prepare_order
from autotrade.trading.submit import execute_order

logger = logging.getLogger(__name__)


class StopFlag:
    def __init__(self) -> None:
        self._stop = False

    def request(self, *_args: Any) -> None:
        self._stop = True

    def __call__(self) -> bool:
        return self._stop


def _validate_cached_client(client: EasyTraderClient) -> None:
    """Cheap read-only probes that prove the JWT still works."""
    client.server_timestamp()
    client.list_orders()


def _client(token: str, transport: PlaywrightTransport, settings: Settings) -> EasyTraderClient:
    return EasyTraderClient(
        token,
        transport,
        base_url=settings.api_base_url,
        min_submit_interval=settings.min_submit_interval,
    )


def bootstrap_client(
    settings: Settings,
    *,
    use_token_cache: bool,
) -> tuple[EasyTraderClient, Any, Any]:
    """Open one browser, reuse a cached JWT when it still works, otherwise log in."""
    hint = account_fingerprint(settings.mofid_user)
    path = settings.token_path()
    page, context = launch_browser(settings)
    transport = PlaywrightTransport(context.request)

    if use_token_cache:
        cached = load_token(
            path,
            min_validity_s=settings.token_cache_min_validity,
            account_hint=hint,
        )
        if cached:
            logger.info("Trying %s", describe(path))
            client = _client(cached, transport, settings)
            try:
                _validate_cached_client(client)
                logger.info("Cached token accepted — skipping login.")
                return client, page, context
            except (EasyApiError, ApiAuthError) as exc:
                logger.warning("Cached token rejected (%s) — logging in.", exc)
                clear_token(path)

    if not login(page, settings):
        raise EasyApiError("Login failed.")
    dismiss_announcement(page)
    token = extract_auth_token(page)
    if use_token_cache:
        save_token(token, path, account_hint=hint)
        logger.info("API token cached (%s).", describe(path))
    return _client(token, transport, settings), page, context


def call_with_client(settings: Settings, *, use_token_cache: bool, action: Any) -> Any:
    """Open one broker session, run ``action(client)``, then close the browser."""
    try:
        client, _page, _ctx = bootstrap_client(settings, use_token_cache=use_token_cache)
        return action(client)
    finally:
        cleanup_all()


def list_account_orders(settings: Settings, *, use_token_cache: bool = True) -> list[LiveOrder]:
    return call_with_client(
        settings,
        use_token_cache=use_token_cache,
        action=list_live_orders,
    )


def edit_account_order(
    settings: Settings,
    order_id: str,
    *,
    price_mode: PriceMode | str | None = None,
    price: int | None = None,
    quantity: int | None = None,
    dry_run: bool = False,
    use_token_cache: bool = True,
) -> EditResult:
    def action(client: EasyTraderClient) -> EditResult:
        return run_edit(
            client,
            order_id,
            price_mode=price_mode,
            price=price,
            quantity=quantity,
            dry_run=dry_run,
        )

    return call_with_client(settings, use_token_cache=use_token_cache, action=action)


def cancel_account_order(
    settings: Settings,
    order_id: str,
    *,
    dry_run: bool = False,
    use_token_cache: bool = True,
) -> CancelResult:
    def action(client: EasyTraderClient) -> CancelResult:
        return run_cancel(client, order_id, dry_run=dry_run)

    return call_with_client(settings, use_token_cache=use_token_cache, action=action)


def place_order(order: Order, settings: Settings | None = None) -> None:
    """Run one already-resolved order. Returns after a dry-run or a user stop. Raises on failure."""
    settings = settings if settings is not None else get_settings()
    stop = StopFlag()
    try:
        signal.signal(signal.SIGINT, stop.request)
    except (ValueError, OSError):
        pass

    try:
        client, _page, _ctx = bootstrap_client(
            settings, use_token_cache=order.use_token_cache
        )
        prepared = prepare_order(
            client,
            side=order.side,
            symbol=order.symbol,
            quantity=order.quantity,
            price_mode=order.price_mode,
            price=order.price,
        )
        clock = ApiClock(client).sync()

        if order.dry_run:
            logger.info(
                "Dry run — order prepared (broker clock %s), no submit.",
                clock.time().strftime("%H:%M:%S"),
            )
            return

        if order.target_time is None:
            logger.info(
                "Submitting immediately (broker clock %s).",
                clock.time().strftime("%H:%M:%S"),
            )
        else:
            now = clock.time()
            if now > order.target_time:
                raise TradeError(
                    f"Target time {order.target_time.strftime('%H:%M:%S')} already passed "
                    f"(broker clock {now.strftime('%H:%M:%S')}) — not submitting."
                )

            reached = wait_until(
                order.target_time,
                clock,
                poll_interval=settings.clock_poll_interval,
                deadline_seconds=settings.clock_deadline_seconds,
                should_stop=stop,
            )
            if reached is None:
                logger.info("Exiting before submit (stop requested).")
                return

        execute_order(
            client, prepared, settings, verify=order.verify, now_fn=clock
        )
    finally:
        cleanup_all()
