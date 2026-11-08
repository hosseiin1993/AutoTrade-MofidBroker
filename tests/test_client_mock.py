import json

import pytest

from autotrade.broker.client import EasyTraderClient
from autotrade.broker.transport import MockTransport
from autotrade.config import Settings
from autotrade.models import PreparedOrder, PriceMode, Side
from autotrade.order import TradeError
from autotrade.trading.submit import execute_order


def test_find_symbol_and_submit_sell():
    routes = {
        ("POST", "/symbols/api/symbols/all"): (
            200,
            json.dumps(
                {
                    "symbols": [
                        {
                            "symbolName": "فولاد",
                            "symbolIsin": "IRO1FOLD0001",
                            "isActive": True,
                        }
                    ]
                }
            ),
        ),
        ("POST", "/symbols/api/marketdata/v2"): (
            200,
            json.dumps(
                [
                    {
                        "symbolIsin": "IRO1FOLD0001",
                        "highAllowedPrice": 5000,
                        "lowAllowedPrice": 4000,
                        "closingPrice": 4500,
                        "buyRatio": "0.003712",
                        "sellRatio": "0.0088",
                        "minValidBuyVolume": 1,
                        "maxValidBuyVolume": 100000,
                    }
                ]
            ),
        ),
        ("POST", "/core/api/v2/order"): (
            200,
            json.dumps({"isSuccessful": True, "id": "abc"}),
        ),
        ("GET", "/core/api/order"): (200, json.dumps({"orders": []})),
        ("GET", "/easy/api/money"): (
            200,
            json.dumps({"buyPowerT0": 1_000_000_000, "t0": 1_000_000_000}),
        ),
        ("GET", "/easy/api/account/server-time/"): (
            200,
            json.dumps({"serverTimestamp": 1_700_000_000_000, "diff": 0}),
        ),
    }
    calls: list = []
    transport = MockTransport(routes, calls)
    client = EasyTraderClient("x" * 80, transport, min_submit_interval=0)

    sym = client.find_symbol("فولاد")
    assert sym["symbolIsin"] == "IRO1FOLD0001"
    md = client.market_data(sym["symbolIsin"])
    assert client.commission_rate(md, Side.SELL) == 0.0088

    resp = client.submit_order(
        side=Side.SELL,
        isin="IRO1FOLD0001",
        symbol_name="فولاد",
        quantity=2,
        price=4000,
        commission=0.0088,
    )
    assert resp["isSuccessful"] is True
    submit = next(c for c in calls if c["url"].endswith("/core/api/v2/order"))
    assert submit["json_body"]["order"]["side"] == 1

    client.money()
    client.list_orders()
    # GET must not send content-type (WAF)
    get_calls = [c for c in calls if c["method"] == "GET"]
    assert get_calls
    for c in get_calls:
        assert "content-type" not in {k.lower() for k in c["headers"]}


def _orders_client(orders: list) -> EasyTraderClient:
    transport = MockTransport(
        {("GET", "/core/api/order"): (200, json.dumps({"orders": orders}))}
    )
    return EasyTraderClient("x" * 80, transport, min_submit_interval=0)


def test_order_appeared_matches_a_complete_row() -> None:
    client = _orders_client(
        [
            {
                "order": {
                    "symbolIsin": "IRO1FOLD0001",
                    "quantity": 2,
                    "price": 4000.0,
                    "side": 1,
                }
            }
        ]
    )
    assert client.order_appeared(
        isin="IRO1FOLD0001",
        quantity=2,
        price=4000,
        side=Side.SELL,
        baseline=[],
    )


def test_order_appeared_ignores_a_preexisting_match() -> None:
    match = {
        "order": {
            "symbolIsin": "IRO1FOLD0001",
            "quantity": 2,
            "price": 4000,
            "side": 1,
        }
    }
    other = {
        "order": {
            "symbolIsin": "IRO1BMLT0001",
            "quantity": 1,
            "price": 1000,
            "side": 0,
        }
    }
    client = _orders_client([match, other])
    assert (
        client.order_appeared(
            isin="IRO1FOLD0001",
            quantity=2,
            price=4000,
            side=Side.SELL,
            baseline=[match],
        )
        is False
    )


def test_order_appeared_accepts_a_second_matching_row() -> None:
    match = {
        "order": {
            "symbolIsin": "IRO1FOLD0001",
            "quantity": 2,
            "price": 4000,
            "side": 1,
        }
    }
    client = _orders_client([match, match])
    assert client.order_appeared(
        isin="IRO1FOLD0001",
        quantity=2,
        price=4000,
        side=Side.SELL,
        baseline=[match],
    )


def test_execute_order_stops_before_submit_when_baseline_is_unreadable() -> None:
    transport = MockTransport({})
    client = EasyTraderClient("x" * 80, transport, min_submit_interval=0)
    prepared = PreparedOrder(
        side=Side.BUY,
        symbol="فولاد",
        isin="IRO1FOLD0001",
        quantity=1,
        price=4000,
        price_mode=PriceMode.FIXED,
        commission=0.0,
        order_value=4000,
    )
    settings = Settings(
        _env_file=None,
        max_order_attempts=3,
        preopen_max_attempts=3,
        submit_interval=0,
        min_submit_interval=0,
    )
    with pytest.raises(TradeError, match="Could not read baseline"):
        execute_order(client, prepared, settings, verify=True)
    assert not any("v2/order" in call["url"] for call in transport.calls)


def test_order_appeared_rejects_a_row_missing_quantity() -> None:
    client = _orders_client(
        [{"order": {"symbolIsin": "IRO1FOLD0001", "price": 4000, "side": 1}}]
    )
    assert (
        client.order_appeared(
            isin="IRO1FOLD0001",
            quantity=2,
            price=4000,
            side=Side.SELL,
            baseline=[],
        )
        is False
    )
