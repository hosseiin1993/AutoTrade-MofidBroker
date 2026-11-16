"""Edit, cancel, and order-list behaviour against mocked HTTP."""

from __future__ import annotations

import json
import logging
from datetime import datetime

import pytest

from autotrade.broker.client import EasyTraderClient, order_total_value
from autotrade.broker.constants import MIN_NOTIONAL_RIAL, ORDER_FROM, TEHRAN_TZ
from autotrade.broker.errors import EasyApiError
from autotrade.broker.orders import format_orders, parse_live_order
from autotrade.broker.transport import MockTransport, PlaywrightTransport
from autotrade.models import PriceMode, Side
from autotrade.order import OrderError, TradeError
from autotrade.trading.manage import run_cancel, run_edit
from autotrade.trading.prepare import PrepareError

TOKEN = "TESTTOKEN-DO-NOT-LOG-" + ("x" * 64)
NOW = datetime(2026, 11, 16, 10, 15, 0, tzinfo=TEHRAN_TZ)
ISIN = "IRO1FOLD0001"
ORDER_ID = "1121Ak37W5X[dJ,C"


def _order(**overrides: object) -> dict:
    row = {
        "id": ORDER_ID,
        "symbolName": "فولاد",
        "symbolIsin": ISIN,
        "price": 50_000,
        "quantity": 200,
        "side": 0,
        "orderState": 6,
        "orderStateStr": "OnBoard",
        "executedQuantity": 0,
        "hon": 998877,
        "parentId": "older-parent",
    }
    row.update(overrides)
    return row


def _symbol() -> dict:
    return {
        "symbolName": "فولاد",
        "symbolIsin": ISIN,
        "isActive": True,
        "minDealableCount": 1,
        "minDealablePrice": 10,
    }


def _market(**overrides: object) -> dict:
    row = {
        "symbolIsin": ISIN,
        "highAllowedPrice": 60_000,
        "lowAllowedPrice": 40_000,
        "closingPrice": 50_000,
        "buyRatio": "0.003712",
        "sellRatio": "0.0088",
        "minValidBuyVolume": 1,
        "maxValidBuyVolume": 100_000,
        "minValidSellVolume": 1,
        "maxValidSellVolume": 100_000,
    }
    row.update(overrides)
    return row


class _Resp:
    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    def text(self) -> str:
        return self._text


class _Ctx:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def put(self, url: str, headers: dict | None = None, data: str | None = None, timeout: int | None = None):
        self.calls.append(("PUT", url, data))
        return _Resp(200, "{}")

    def delete(self, url: str, headers: dict | None = None, data: str | None = None, timeout: int | None = None):
        self.calls.append(("DELETE", url, data))
        return _Resp(200, "{}")


def _client(
    order: dict | None = None,
    *,
    orders_body=None,
    modify_status: int = 200,
    modify_body: dict | None = None,
    delete_status: int = 200,
    delete_body: dict | None = None,
    market: dict | None = None,
    symbol: dict | None = None,
) -> tuple[EasyTraderClient, list]:
    order = _order() if order is None else order
    modify_body = {"isSuccessful": True, "id": "new-id"} if modify_body is None else modify_body
    delete_body = {"isSuccessful": True, "id": ORDER_ID} if delete_body is None else delete_body
    if orders_body is None:
        orders_body = {"orders": [order]}

    def orders_text() -> str:
        body = orders_body() if callable(orders_body) else orders_body
        return json.dumps(body)

    routes = {
        ("GET", "/core/api/order"): (200, orders_text),
        ("POST", "/symbols/api/symbols/all"): (
            200,
            json.dumps({"symbols": [symbol or _symbol()]}),
        ),
        ("POST", "/symbols/api/marketdata/v2"): (
            200,
            json.dumps([market or _market()]),
        ),
        ("PUT", "/core/api/v2/order"): (modify_status, json.dumps(modify_body)),
        ("DELETE", "/core/api/v2/delete-order"): (delete_status, json.dumps(delete_body)),
    }
    calls: list = []
    return EasyTraderClient(TOKEN, MockTransport(routes, calls), min_submit_interval=0), calls


def _puts(calls: list) -> list:
    return [c for c in calls if c["method"] == "PUT"]


def _deletes(calls: list) -> list:
    return [c for c in calls if c["method"] == "DELETE"]


def test_parse_nested_row_and_trade_fills() -> None:
    order = parse_live_order(
        {
            "id": ORDER_ID,
            "order": {
                "symbolName": "فولاد",
                "symbolIsin": ISIN,
                "price": 50_000.0,
                "quantity": 10,
                "side": 1,
                "trades": [
                    {"quantity": 4, "isCancel": False},
                    {"quantity": 1, "isCancel": True},
                ],
            },
        }
    )
    assert order.side is Side.SELL
    assert order.filled == 4
    assert order.remainder == 6
    assert order.price == 50_000


def test_format_orders_columns() -> None:
    text = format_orders([parse_live_order(_order(executedQuantity=15))])
    assert text.splitlines()[0] == "id\tsymbol\tside\tqty\tfilled\tprice\tstatus"
    assert "فولاد\tbuy\t200\t15\t50000\tOnBoard" in text


def test_edit_sends_modify_order_with_parent_id_once(caplog: pytest.LogCaptureFixture) -> None:
    client, calls = _client(_order(side=1, quantity=300, executedQuantity=100))
    with caplog.at_level(logging.INFO):
        result = run_edit(
            client,
            ORDER_ID,
            price_mode=PriceMode.FIXED,
            price=50_000,
            now=NOW,
        )
    puts = _puts(calls)
    assert len(puts) == 1
    assert puts[0]["method"] == "PUT"
    assert puts[0]["url"].endswith("/core/api/v2/order")
    body = puts[0]["json_body"]
    modify = body["modifyOrder"]
    assert "order" not in body
    assert modify["parentId"] == ORDER_ID
    assert modify["id"] is None
    assert modify["quantity"] == 200
    assert modify["price"] == 50_000
    assert modify["side"] == 1
    assert modify["orderFrom"] == ORDER_FROM
    assert modify["symbolIsin"] == ISIN
    assert modify["symbolName"] == "فولاد"
    assert modify["orderModelType"] == 1
    assert "hon" not in modify
    assert "998877" not in json.dumps(body)
    assert modify["createDateTime"] == "11/16/2026, 10:15:00 AM"
    assert modify["totalValue"] == order_total_value(
        side=Side.SELL, price=50_000, quantity=200, commission=0.0088
    )
    assert result.new_order_id == "new-id"
    assert result.dry_run is False
    assert TOKEN not in caplog.text
    assert puts[0]["headers"]["authorization"] == f"Bearer {TOKEN}"


def test_edit_price_modes_use_the_daily_band() -> None:
    client, calls = _client(_order(side=0))
    ceiling = run_edit(client, ORDER_ID, price_mode="ceiling", now=NOW)
    assert ceiling.price == 60_000
    floor = run_edit(client, ORDER_ID, price_mode=PriceMode.FLOOR, now=NOW)
    assert floor.price == 40_000
    reference = run_edit(client, ORDER_ID, price_mode=PriceMode.REFERENCE, now=NOW)
    assert reference.price == 50_000
    auto = run_edit(client, ORDER_ID, price_mode=PriceMode.AUTO, now=NOW)
    assert auto.price == 60_000
    assert len(_puts(calls)) == 4


def test_edit_auto_on_a_sell_uses_the_floor() -> None:
    client, calls = _client(_order(side=1))
    result = run_edit(client, ORDER_ID, price_mode=PriceMode.AUTO, now=NOW)
    assert result.payload["modifyOrder"]["price"] == 40_000
    assert result.payload["modifyOrder"]["side"] == 1
    assert len(_puts(calls)) == 1


def test_edit_dry_run_does_not_send() -> None:
    client, calls = _client()
    result = run_edit(client, ORDER_ID, price_mode=PriceMode.FIXED, price=50_000, dry_run=True, now=NOW)
    assert result.dry_run is True
    assert result.payload["modifyOrder"]["parentId"] == ORDER_ID
    assert _puts(calls) == []


def test_edit_refuses_a_full_fill_and_a_cancel() -> None:
    filled, calls = _client(_order(quantity=200, executedQuantity=200))
    with pytest.raises(OrderError, match="fully executed"):
        run_edit(filled, ORDER_ID, price=50_000, now=NOW)
    assert _puts(calls) == []

    cancelled, calls = _client(_order(orderState=3, orderStateStr="Cancel"))
    with pytest.raises(OrderError, match="cancelled"):
        run_edit(cancelled, ORDER_ID, price=50_000, now=NOW)
    assert _puts(calls) == []


def test_edit_refuses_price_band_lot_and_notional_before_sending() -> None:
    client, calls = _client()
    with pytest.raises(PrepareError, match="daily band"):
        run_edit(client, ORDER_ID, price=1_000, now=NOW)
    assert _puts(calls) == []

    lot_client, lot_calls = _client(symbol={**_symbol(), "minDealableCount": 10})
    with pytest.raises(PrepareError, match="lot size 10"):
        run_edit(lot_client, ORDER_ID, price=50_000, quantity=15, now=NOW)
    assert _puts(lot_calls) == []

    small, small_calls = _client(
        _order(quantity=10),
        market=_market(lowAllowedPrice=1_000, highAllowedPrice=2_000),
    )
    with pytest.raises(PrepareError, match="5,000,000"):
        run_edit(small, ORDER_ID, price=1_000, now=NOW)
    assert _puts(small_calls) == []
    assert MIN_NOTIONAL_RIAL == 5_000_000


def test_edit_rejection_is_not_retried() -> None:
    client, calls = _client(
        modify_body={
            "isSuccessful": False,
            "omsError": [{"code": 8006, "error": "حداقل مبلغ سفارش"}],
        }
    )
    with pytest.raises(TradeError, match="Edit rejected \\(code 8006\\)"):
        run_edit(client, ORDER_ID, price=50_000, now=NOW)
    assert len(_puts(calls)) == 1


def test_cancel_confirms_the_order_is_gone_and_reports_the_fill() -> None:
    state = {"n": 0}

    def orders():
        state["n"] += 1
        if state["n"] == 1:
            return {"orders": [_order(executedQuantity=40, quantity=200)]}
        return {"orders": []}

    client, calls = _client(orders_body=orders)
    result = run_cancel(client, ORDER_ID)
    assert result.outcome == "gone"
    assert result.filled == 40
    assert result.dry_run is False
    deletes = _deletes(calls)
    assert len(deletes) == 1
    assert deletes[0]["url"].endswith("/core/api/v2/delete-order")
    assert deletes[0]["json_body"] == {"orderId": ORDER_ID, "orderFrom": ORDER_FROM}
    assert TOKEN not in json.dumps(deletes[0]["json_body"])


def test_cancel_confirms_a_cancelled_status() -> None:
    state = {"n": 0}

    def orders():
        state["n"] += 1
        if state["n"] == 1:
            return {"orders": [_order(executedQuantity=7)]}
        return {"orders": [_order(orderState=18, orderStateStr="CancelByBroker", executedQuantity=7)]}

    client, calls = _client(orders_body=orders)
    result = run_cancel(client, ORDER_ID)
    assert result.outcome == "cancelled"
    assert result.filled == 7
    assert result.status == "CancelByBroker"
    assert len(_deletes(calls)) == 1


def test_cancel_does_not_retry_when_the_order_stays_open() -> None:
    client, calls = _client(_order())
    with pytest.raises(TradeError, match="still OnBoard"):
        run_cancel(client, ORDER_ID)
    assert len(_deletes(calls)) == 1


def test_cancel_rejection_and_confirm_failure_are_not_retried() -> None:
    rejected, calls = _client(
        delete_body={"isSuccessful": False, "omsError": [{"code": 42, "error": "نمی توان حذف کرد"}]}
    )
    with pytest.raises(TradeError, match="Cancel rejected \\(code 42\\)"):
        run_cancel(rejected, ORDER_ID)
    assert len(_deletes(calls)) == 1

    state = {"n": 0}

    def orders():
        state["n"] += 1
        if state["n"] == 1:
            return {"orders": [_order()]}
        raise EasyApiError("order list unavailable")

    flaky, flaky_calls = _client(orders_body=orders)
    with pytest.raises(TradeError, match="Not sending the cancel again"):
        run_cancel(flaky, ORDER_ID)
    assert len(_deletes(flaky_calls)) == 1


def test_cancel_dry_run_and_terminal_orders_do_not_send() -> None:
    client, calls = _client(_order(executedQuantity=12))
    result = run_cancel(client, ORDER_ID, dry_run=True)
    assert result.dry_run is True
    assert result.filled == 12
    assert _deletes(calls) == []

    done, done_calls = _client(_order(orderState=20, orderStateStr="OrderExecuted", executedQuantity=10, quantity=200))
    with pytest.raises(OrderError, match="fully executed"):
        run_cancel(done, ORDER_ID)
    assert _deletes(done_calls) == []


def test_playwright_transport_put_and_delete_keep_the_json_body() -> None:
    ctx = _Ctx()
    transport = PlaywrightTransport(ctx)
    status, text = transport.request(
        method="PUT",
        url="https://api.example/core/api/v2/order",
        headers={"authorization": "Bearer secret"},
        json_body={"modifyOrder": {"id": None, "parentId": ORDER_ID}},
    )
    assert status == 200
    assert text == "{}"
    method, url, data = ctx.calls[0]
    assert method == "PUT"
    assert json.loads(data)["modifyOrder"]["id"] is None
    status, _ = transport.request(
        method="DELETE",
        url="https://api.example/core/api/v2/delete-order",
        headers={},
        json_body={"orderId": ORDER_ID, "orderFrom": 34},
    )
    assert status == 200
    assert json.loads(ctx.calls[1][2])["orderId"] == ORDER_ID


def test_cli_orders_edit_and_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    import autotrade.cli as cli
    from autotrade.config import Settings

    monkeypatch.delenv("MOFID_USER", raising=False)
    monkeypatch.delenv("MOFID_PASS", raising=False)
    monkeypatch.setattr(cli, "setup_logging", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: Settings(_env_file=None, mofid_user="", mofid_pass=""),
    )
    runner = CliRunner()
    secret = "cli-secret-should-not-print"

    help_result = runner.invoke(cli.app, ["--help"])
    assert help_result.exit_code == 0
    for name in ("orders", "edit", "cancel"):
        assert name in help_result.stdout

    missing = runner.invoke(cli.app, ["orders"])
    assert missing.exit_code == 2
    assert secret not in missing.stdout

    def fake_list(settings: Settings, use_token_cache: bool) -> list:
        assert settings.mofid_pass == secret
        assert use_token_cache is True
        return [parse_live_order(_order(executedQuantity=15))]

    monkeypatch.setattr(cli, "list_account_orders", fake_list)
    listed = runner.invoke(
        cli.app, ["orders", "--user", "09120000000", "--password", secret]
    )
    assert listed.exit_code == 0
    assert "فولاد" in listed.stdout
    assert "15" in listed.stdout
    assert secret not in listed.stdout

    def fake_edit(*_args: object, **_kwargs: object) -> None:
        raise TradeError("Edit rejected (code 8006): حداقل مبلغ")

    monkeypatch.setattr(cli, "edit_account_order", fake_edit)
    edited = runner.invoke(
        cli.app,
        ["edit", "--order-id", ORDER_ID, "--user", "u", "--password", secret, "-p", "50000"],
    )
    assert edited.exit_code == 1
    assert secret not in (edited.stdout + edited.stderr)

    no_id = runner.invoke(cli.app, ["cancel", "--user", "u", "--password", secret])
    assert no_id.exit_code != 0
    assert secret not in (no_id.stdout + no_id.stderr)


def test_modify_payload_requires_a_parent_id() -> None:
    with pytest.raises(EasyApiError, match="parentId"):
        EasyTraderClient.build_modify_payload(
            side=Side.BUY,
            isin=ISIN,
            symbol_name="فولاد",
            quantity=200,
            price=50_000,
            commission=0.003712,
            parent_id="",
        )
