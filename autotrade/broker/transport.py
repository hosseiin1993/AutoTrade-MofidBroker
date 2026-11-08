from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from autotrade.broker.constants import READ_TIMEOUT_MS
from autotrade.broker.errors import EasyApiError


class Transport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: Any,
    ) -> tuple[int, str]: ...


class PlaywrightTransport:
    """Send via Chromium's network stack (required — WAF blocks plain HTTP clients)."""

    def __init__(self, api_request_context: Any) -> None:
        self.ctx = api_request_context

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: Any,
    ) -> tuple[int, str]:
        try:
            if method.upper() == "GET":
                resp = self.ctx.get(url, headers=headers, timeout=READ_TIMEOUT_MS)
            else:
                data = json.dumps(json_body) if json_body is not None else None
                resp = self.ctx.post(
                    url, headers=headers, data=data, timeout=READ_TIMEOUT_MS
                )
        except Exception as exc:
            raise EasyApiError(
                f"{method} {url} transport error: {type(exc).__name__}: {exc}"
            ) from exc
        return resp.status, resp.text()


class MockTransport:
    """Scripted (method, url_substring) → (status, body) for unit tests."""

    def __init__(
        self,
        routes: dict[tuple[str, str], tuple[int, str | Callable[[], str]]],
        calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = calls if calls is not None else []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: Any,
    ) -> tuple[int, str]:
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json_body": json_body,
            }
        )
        for (m, frag), (status, text) in self.routes.items():
            if m == method and frag in url:
                if callable(text):
                    text = text()
                return status, text
        return 500, '{"error":"no route"}'
