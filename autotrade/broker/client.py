from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any

from autotrade.broker.constants import (
    API_BASE,
    BUY_POWER_KEYS,
    DEFAULT_BUY_COMMISSION,
    DEFAULT_SELL_COMMISSION,
    MIN_TOKEN_LEN,
    ORDER_FROM,
    ORDER_MODEL_TYPE,
    SIDE_BUY,
    SIDE_SELL,
    SUBMIT_INTERVAL_FLOOR_S,
    TEHRAN_TZ,
    VALIDITY_TYPE_DAY,
)
from autotrade.broker.errors import ApiAuthError, EasyApiError
from autotrade.broker.transport import Transport
from autotrade.models import Side

logger = logging.getLogger(__name__)

_BEARER_RE = re.compile(r"^Bearer (.+)$", re.IGNORECASE)


def _as_int(value: object) -> int | None:
    """Whole number from the broker, or None when the field is missing or not numeric."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _match_count(
    orders: list[dict[str, Any]],
    *,
    isin: str,
    quantity: int,
    price: int,
    side: Side,
) -> int:
    return sum(
        1
        for item in orders
        if _row_matches(item, isin=isin, quantity=quantity, price=price, side=side)
    )


def _row_matches(
    item: dict[str, Any],
    *,
    isin: str,
    quantity: int,
    price: int,
    side: Side,
) -> bool:
    row = item.get("order") or item
    isin_f = row.get("symbolIsin") or row.get("isin") or item.get("symbolIsin")
    return (
        str(isin_f or "") == str(isin)
        and _as_int(row.get("quantity")) == quantity
        and _as_int(row.get("price")) == price
        and _as_int(row.get("side")) == side.api_code
    )


def buying_power(money: dict[str, Any]) -> int | None:
    if not isinstance(money, dict):
        return None
    for key in BUY_POWER_KEYS:
        value = money.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def parse_oms_error(resp: Any) -> dict[str, Any] | None:
    if not isinstance(resp, dict):
        return None
    errs = resp.get("omsError") or resp.get("errors")
    first = (
        errs[0]
        if isinstance(errs, list) and errs and isinstance(errs[0], dict)
        else None
    )
    top = resp.get("message") or resp.get("error")
    if first is None and not top and resp.get("isSuccessful") is not False:
        return None
    code = None
    name = ""
    message = str(top or "")
    if first is not None:
        try:
            code = int(first.get("code"))
        except (TypeError, ValueError):
            code = None
        name = str(first.get("name") or "")
        message = str(first.get("error") or first.get("message") or message)
    return {"code": code, "name": name, "message": message}


def format_create_datetime(n: datetime) -> str:
    """Match EasyTrader's en-US style: no leading zero on the 12-hour hour."""
    h12 = n.hour % 12 or 12
    ampm = "AM" if n.hour < 12 else "PM"
    return f"{n.month:02d}/{n.day:02d}/{n.year}, {h12}:{n.minute:02d}:{n.second:02d} {ampm}"


def order_total_value(*, side: Side, price: int, quantity: int, commission: float) -> int:
    if side is Side.BUY:
        return round(price * quantity * (1 + commission))
    return round(price * quantity * (1 - commission))


class EasyTraderClient:
    """HTTP client for EasyTrader's undocumented MTS API."""

    def __init__(
        self,
        token: str,
        transport: Transport,
        base_url: str = API_BASE,
        min_submit_interval: float = SUBMIT_INTERVAL_FLOOR_S,
        monotonic_fn=time.monotonic,
        sleep_fn=time.sleep,
    ) -> None:
        if not token:
            raise EasyApiError("Empty auth token.")
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.token = token.strip()
        self.min_submit_interval = max(0.0, float(min_submit_interval))
        self._monotonic = monotonic_fn
        self._sleep = sleep_fn
        self._last_submit_at: float | None = None
        self._symbols_cache: list[dict[str, Any]] | None = None
        self._cache_lock = threading.Lock()

    def _headers(self, *, content_type: bool = False) -> dict[str, str]:
        headers = {
            "authorization": f"Bearer {self.token}",
            "accept": "application/json, text/plain, */*",
            "accept-language": "fa",
            "origin": "https://d.easytrader.ir",
            "referer": "https://d.easytrader.ir/",
        }
        if content_type:
            headers["content-type"] = "application/json"
        return headers

    def _request(self, method: str, path: str, *, json_body: Any = None) -> Any:
        url = self.base_url + path
        headers = self._headers(
            content_type=json_body is not None and method.upper() != "GET"
        )
        status, text = self.transport.request(
            method=method, url=url, headers=headers, json_body=json_body
        )
        if status == 401:
            raise ApiAuthError(f"{method} {path} → 401 Unauthorized (token expired?).")
        if not (200 <= status < 300):
            snippet = (text or "")[:150].replace("\n", " ")
            if "waf" in snippet.lower() or "<html" in snippet.lower():
                raise EasyApiError(
                    f"{method} {path} → HTTP {status}: WAF/HTML challenge "
                    "(use PlaywrightTransport)."
                )
            raise EasyApiError(f"{method} {path} → HTTP {status}: {snippet}")
        try:
            return json.loads(text)
        except ValueError as exc:
            snippet = (text or "")[:150].replace("\n", " ")
            if "<html" in snippet.lower():
                raise EasyApiError(
                    f"{method} {path} → HTML body (WAF) with HTTP {status}"
                ) from exc
            raise EasyApiError(f"{method} {path} → non-JSON body: {snippet}") from exc

    def server_timestamp(self) -> int:
        data = self._request(
            "GET",
            f"/easy/api/account/server-time/{int(datetime.now().timestamp() * 1000)}",
        )
        ts = data.get("serverTimestamp")
        if not ts:
            raise EasyApiError(f"server-time missing serverTimestamp: {data!r}")
        return int(ts)

    def all_symbols(self, force: bool = False) -> list[dict[str, Any]]:
        with self._cache_lock:
            if self._symbols_cache is not None and not force:
                return self._symbols_cache
            data = self._request(
                "POST", "/symbols/api/symbols/all", json_body={"hash": "null"}
            )
            symbols = data.get("symbols") if isinstance(data, dict) else None
            if not symbols:
                raise EasyApiError("symbols/all response has no 'symbols' list.")
            self._symbols_cache = symbols
            return symbols

    def find_symbol(self, name: str) -> dict[str, Any]:
        target = (name or "").strip()
        if not target:
            raise EasyApiError("Empty symbol name.")
        matches = [
            s
            for s in self.all_symbols()
            if (s.get("symbolName") or "").strip() == target
            or (s.get("title") or "").strip() == target
        ]
        if not matches:
            raise EasyApiError(
                f"Symbol {name!r} not found "
                f"({len(self.all_symbols())} symbols loaded)."
            )
        matches.sort(key=lambda s: not s.get("isActive", False))
        return matches[0]

    def market_data(self, isin: str) -> dict[str, Any]:
        data = self._request("POST", "/symbols/api/marketdata/v2", json_body=[isin])
        if not isinstance(data, list) or not data:
            raise EasyApiError(f"marketdata/v2 returned no rows for {isin}.")
        for row in data:
            if row.get("symbolIsin") == isin:
                return row
        raise EasyApiError(f"marketdata/v2 missing isin {isin}.")

    def commission_rate(self, md: dict[str, Any], side: Side) -> float:
        if side is Side.BUY:
            raw = md.get("buyRatio")
            default = DEFAULT_BUY_COMMISSION
        else:
            raw = md.get("sellRatio") or md.get("sellCommission")
            default = DEFAULT_SELL_COMMISSION
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    def money(self) -> dict[str, Any]:
        data = self._request("GET", "/easy/api/money")
        if not isinstance(data, dict):
            raise EasyApiError(f"money response is not an object: {str(data)[:120]}")
        return data

    @staticmethod
    def build_order_payload(
        *,
        side: Side,
        isin: str,
        symbol_name: str,
        quantity: int,
        price: int,
        commission: float,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if quantity <= 0:
            raise EasyApiError(f"quantity must be > 0 (got {quantity}).")
        if price <= 0:
            raise EasyApiError(f"price must be > 0 (got {price}).")
        if not isin:
            raise EasyApiError("symbolIsin empty.")
        n = now or datetime.now(TEHRAN_TZ)
        return {
            "order": {
                "price": price,
                "quantity": quantity,
                "side": SIDE_BUY if side is Side.BUY else SIDE_SELL,
                "validityType": VALIDITY_TYPE_DAY,
                "createDateTime": format_create_datetime(n),
                "commission": commission,
                "symbolIsin": isin,
                "symbolName": symbol_name,
                "orderModelType": ORDER_MODEL_TYPE,
                "totalValue": order_total_value(
                    side=side, price=price, quantity=quantity, commission=commission
                ),
                "orderFrom": ORDER_FROM,
            }
        }

    def _wait_submit_slot(self, interval: float) -> float:
        waited = 0.0
        if self._last_submit_at is not None and interval > 0:
            gap = self._monotonic() - self._last_submit_at
            if gap < interval:
                waited = interval - gap
                self._sleep(waited)
        self._last_submit_at = self._monotonic()
        return waited

    def submit_order(
        self,
        *,
        side: Side,
        isin: str,
        symbol_name: str,
        quantity: int,
        price: int,
        commission: float,
        now: datetime | None = None,
        min_interval: float | None = None,
    ) -> Any:
        interval = self.min_submit_interval
        if min_interval is not None:
            interval = max(float(min_interval), self.min_submit_interval)
        self._wait_submit_slot(interval)
        payload = self.build_order_payload(
            side=side,
            isin=isin,
            symbol_name=symbol_name,
            quantity=quantity,
            price=price,
            commission=commission,
            now=now,
        )
        logger.info(
            "Submitting %s via API: %s",
            side.value,
            payload["order"],
        )
        return self._request("POST", "/core/api/v2/order", json_body=payload)

    def list_orders(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/core/api/order")
        orders = data.get("orders") if isinstance(data, dict) else None
        if orders is None:
            raise EasyApiError(f"order list missing 'orders': {str(data)[:120]}")
        return orders

    def order_appeared(
        self,
        *,
        isin: str,
        quantity: int,
        price: int,
        side: Side,
        baseline: list[dict[str, Any]],
    ) -> bool:
        """True when a new row matches this order. A longer list of other orders does not."""
        orders = self.list_orders()
        before = _match_count(baseline, isin=isin, quantity=quantity, price=price, side=side)
        after = _match_count(orders, isin=isin, quantity=quantity, price=price, side=side)
        return after > before


def extract_auth_token(page: Any, timeout: float = 15.0) -> str:
    """Harvest Bearer JWT from the page's outbound API requests."""
    found: dict[str, str] = {}

    def _on_request(req: Any) -> None:
        try:
            auth = (req.headers or {}).get("authorization")
            m = _BEARER_RE.match(auth.strip()) if auth else None
            if m and len(m.group(1)) >= MIN_TOKEN_LEN:
                found["token"] = m.group(1)
        except Exception:
            pass

    try:
        page.on("request", _on_request)
    except Exception as exc:
        raise EasyApiError(f"Can't attach token listener: {exc}") from exc

    try:
        if not found.get("token"):
            try:
                page.wait_for_timeout(int(timeout * 1000))
            except Exception:
                pass
        token = found.get("token")
        if not token:
            raise EasyApiError("No Authorization Bearer header seen on page requests.")
        return token
    finally:
        try:
            page.remove_listener("request", _on_request)
        except Exception:
            pass
