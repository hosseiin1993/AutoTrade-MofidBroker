from __future__ import annotations

import logging
import time
from datetime import datetime, time as dt_time, timedelta
from typing import Callable

from autotrade.broker.client import EasyTraderClient
from autotrade.broker.constants import ORDER_WINDOW_CLOSE, ORDER_WINDOW_OPEN, TEHRAN_TZ

logger = logging.getLogger(__name__)

MARKET_LATEST = dt_time(15, 30, 0)


class ApiClock:
    """Broker wall clock from HTTP server-time + local offset."""

    def __init__(
        self,
        client: EasyTraderClient,
        *,
        resync_after_s: float = 60.0,
        now_fn=time.time,
    ) -> None:
        self.client = client
        self.resync_after_s = resync_after_s
        self._now_fn = now_fn
        self._offset_ms = 0.0
        self._synced_at = 0.0

    def sync(self) -> ApiClock:
        local_ms = self._now_fn() * 1000.0
        self._offset_ms = float(self.client.server_timestamp()) - local_ms
        self._synced_at = self._now_fn()
        logger.info("API clock synced (offset %+.0f ms).", self._offset_ms)
        return self

    def now(self) -> datetime:
        if self._synced_at and (self._now_fn() - self._synced_at) > self.resync_after_s:
            try:
                self.sync()
            except Exception as exc:
                self._synced_at = self._now_fn()
                logger.warning("API clock re-sync failed (%s).", exc)
        ts = (self._now_fn() * 1000.0 + self._offset_ms) / 1000.0
        return datetime.fromtimestamp(ts, TEHRAN_TZ)

    def time(self) -> dt_time:
        return self.now().time()

    def __call__(self) -> dt_time:
        return self.time()


def wait_until(
    target: dt_time,
    now_fn: Callable[[], dt_time],
    *,
    poll_interval: float = 0.05,
    deadline_seconds: float = 3600.0,
    should_stop: Callable[[], bool] | None = None,
) -> dt_time | None:
    """Busy-wait until broker clock >= target (and <= 15:30). Returns None if stopped."""
    deadline = datetime.now() + timedelta(seconds=deadline_seconds)
    logger.info(
        "Waiting for broker clock >= %s (deadline %s)",
        target.strftime("%H:%M:%S"),
        deadline.strftime("%H:%M:%S"),
    )
    now_fn()  # fail fast if clock unreadable

    while True:
        if should_stop and should_stop():
            logger.info("Stop requested — leaving clock wait.")
            return None
        if datetime.now() > deadline:
            raise TimeoutError(
                f"Target {target} not reached within {deadline_seconds}s."
            )
        try:
            now = now_fn()
        except Exception as exc:
            if should_stop and should_stop():
                return None
            logger.warning("Clock read failed (%s), retrying...", exc)
            time.sleep(poll_interval)
            continue
        if now >= target and now <= MARKET_LATEST:
            logger.info("Target time reached: %s", now.strftime("%H:%M:%S"))
            return now
        if now > MARKET_LATEST:
            raise TimeoutError(f"Market closed (broker clock {now}).")
        time.sleep(poll_interval)


def window_state(now_fn: Callable | None = None) -> str:
    if now_fn is None:
        return "unknown"
    try:
        now = now_fn()
    except Exception:
        return "unknown"
    t = now.time() if isinstance(now, datetime) else now
    if not isinstance(t, dt_time):
        return "unknown"
    if t < dt_time(*ORDER_WINDOW_OPEN):
        return "early"
    if t > dt_time(*ORDER_WINDOW_CLOSE):
        return "late"
    return "open"


def seconds_until_window_open(now_fn: Callable | None = None) -> float | None:
    if now_fn is None:
        return None
    try:
        now = now_fn()
    except Exception:
        return None
    if isinstance(now, dt_time):
        now = datetime.combine(datetime.now(TEHRAN_TZ).date(), now, tzinfo=TEHRAN_TZ)
    if not isinstance(now, datetime):
        return None
    target = now.replace(
        hour=ORDER_WINDOW_OPEN[0],
        minute=ORDER_WINDOW_OPEN[1],
        second=0,
        microsecond=0,
    )
    return (target - now).total_seconds()
