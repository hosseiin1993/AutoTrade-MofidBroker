from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import NamedTuple

from autotrade.broker.client import EasyTraderClient, parse_oms_error
from autotrade.broker.constants import OMS_CODE_ORDER_INTERVAL, OMS_CODES_NOT_OPEN
from autotrade.browser import require_live_browser
from autotrade.config import Settings
from autotrade.models import PreparedOrder
from autotrade.order import TradeError
from autotrade.trading.clock import seconds_until_window_open, window_state
from autotrade.trading.prepare import log_order_review

logger = logging.getLogger(__name__)

SUBMIT_ACCEPTED = "accepted"
SUBMIT_THROTTLED = "throttled"
SUBMIT_NOT_OPEN = "not_open"
SUBMIT_REJECTED = "rejected"

_NOT_OPEN_HINTS = ("اجازه فعالیت نمی‌دهد", "ساعت مجاز ثبت سفارش")


class SubmitOutcome(NamedTuple):
    kind: str
    code: int | None
    message: str
    order_id: str | None = None

    @property
    def ok(self) -> bool:
        return self.kind == SUBMIT_ACCEPTED


def classify_submit_response(resp: object) -> SubmitOutcome:
    if isinstance(resp, dict) and resp.get("isSuccessful") is True:
        err = parse_oms_error(resp)
        if err is None:
            raw_id = resp.get("id")
            return SubmitOutcome(
                SUBMIT_ACCEPTED,
                None,
                "",
                str(raw_id) if raw_id else None,
            )
    err = parse_oms_error(resp)
    if err is None:
        return SubmitOutcome(SUBMIT_REJECTED, None, "broker did not accept the order")
    code, msg = err["code"], err["message"]
    if code == OMS_CODE_ORDER_INTERVAL:
        return SubmitOutcome(SUBMIT_THROTTLED, code, msg)
    if code in OMS_CODES_NOT_OPEN or any(h in msg for h in _NOT_OPEN_HINTS):
        return SubmitOutcome(SUBMIT_NOT_OPEN, code, msg)
    return SubmitOutcome(SUBMIT_REJECTED, code, msg)


_CASH_KEYS = ("t2", "buyPowerT2", "block")


def cash_changed(before: dict | None, after: dict | None) -> bool:
    """True when the broker reserved or spent cash after the acknowledge."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    for key in _CASH_KEYS:
        old, new = before.get(key), after.get(key)
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and int(old) != int(new):
            return True
    return False


def order_appears(
    client: EasyTraderClient,
    prepared: PreparedOrder,
    baseline: list,
    *,
    deadline_s: float = 3.0,
    timeout_fn=time.time,
    sleep_fn=time.sleep,
) -> bool:
    """True only when the order is still on the book at the end of the wait.

    A row that shows up and then disappears is not a kept order.
    """
    end = timeout_fn() + deadline_s
    held = False
    while timeout_fn() < end:
        try:
            held = client.order_appeared(
                isin=prepared.isin,
                quantity=prepared.quantity,
                price=prepared.price,
                side=prepared.side,
                baseline=baseline,
            )
        except Exception as exc:
            require_live_browser(exc)
            logger.debug("order_appeared poll error: %s", exc)
            held = False
        if timeout_fn() >= end:
            break
        sleep_fn(0.25)
    return held


def execute_order(
    client: EasyTraderClient,
    prepared: PreparedOrder,
    settings: Settings,
    *,
    verify: bool,
    now_fn: Callable | None = None,
    timeout_fn=time.time,
) -> None:
    """Burst-submit until accepted. Raises TradeError when the order is not accepted."""
    log_order_review(prepared)

    max_attempts = max(1, settings.max_order_attempts)
    max_refusals = max(1, settings.preopen_max_attempts)
    interval = max(settings.submit_interval, settings.min_submit_interval)

    logger.info(
        "API %s burst: up to %d order attempts + %d pre-open retries, %.0f ms apart",
        prepared.side.value,
        max_attempts,
        max_refusals,
        interval * 1000,
    )

    if verify:
        try:
            baseline = client.list_orders()
        except Exception as exc:
            require_live_browser(exc)
            raise TradeError(f"Could not read baseline orders ({exc}).") from exc
        logger.info("Baseline order count: %d", len(baseline))

    attempts = 0
    refusals = 0
    last_code: int | None = None
    iterations = 0
    max_iterations = (max_attempts + max_refusals) * 4

    while (
        attempts < max_attempts
        and refusals < max_refusals
        and iterations < max_iterations
    ):
        iterations += 1
        try:
            resp = client.submit_order(
                side=prepared.side,
                isin=prepared.isin,
                symbol_name=prepared.symbol,
                quantity=prepared.quantity,
                price=prepared.price,
                commission=prepared.commission,
                min_interval=interval,
            )
        except Exception as exc:
            require_live_browser(exc)
            attempts += 1
            logger.info(
                "Attempt %d/%d: submit error (%s)", attempts, max_attempts, exc
            )
            continue

        outcome = classify_submit_response(resp)

        if outcome.kind == SUBMIT_THROTTLED:
            logger.warning(
                "Throttled (%s) — retrying without spending attempt budget.",
                outcome.message,
            )
            continue

        if outcome.kind == SUBMIT_NOT_OPEN:
            last_code = outcome.code
            state = window_state(now_fn)
            if state == "late":
                raise TradeError(
                    f"Order window closed (code {outcome.code}): {outcome.message}"
                )
            refusals += 1
            if refusals == 1:
                wait_s = (
                    seconds_until_window_open(now_fn) if state == "early" else None
                )
                logger.info(
                    "Session not open yet (code %s) — pre-open retry up to %d.",
                    outcome.code,
                    max_refusals,
                )
                if wait_s is not None and wait_s > settings.order_window_grace:
                    logger.warning(
                        "Session opens in %.1fs — start closer to 08:45.",
                        wait_s,
                    )
            elif refusals % 5 == 0:
                logger.info("Pre-open retries: %d/%d", refusals, max_refusals)
            continue

        attempts += 1
        if outcome.kind == SUBMIT_REJECTED:
            raise TradeError(
                f"Attempt {attempts}/{max_attempts}: rejected "
                f"(code {outcome.code}): {outcome.message}."
            )

        logger.info(
            "Attempt %d/%d: broker ack id=%s.",
            attempts,
            max_attempts,
            outcome.order_id or "-",
        )

        if not verify:
            return

        try:
            cash_before = client.money()
        except Exception as exc:
            require_live_browser(exc)
            cash_before = None
            logger.warning("Could not read cash before verify (%s).", exc)

        held = order_appears(
            client, prepared, baseline, deadline_s=3.0, timeout_fn=timeout_fn
        )
        moved = False
        if cash_before is not None:
            try:
                moved = cash_changed(cash_before, client.money())
            except Exception as exc:
                require_live_browser(exc)
                logger.warning("Could not read cash after verify (%s).", exc)
        if held or moved:
            logger.info("Order kept by the broker.")
            return
        ident = f" id {outcome.order_id}" if outcome.order_id else ""
        raise TradeError(
            f"Broker acknowledged the order{ident}, then did not keep it "
            "on the book and did not reserve cash."
        )

    if refusals >= max_refusals and attempts < max_attempts:
        raise TradeError(
            f"Session never opened after {refusals} pre-open submits (last code {last_code})."
        )
    raise TradeError(f"Order not accepted after {attempts} API attempts.")
