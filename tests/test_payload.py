from datetime import datetime

from autotrade.broker.client import EasyTraderClient, order_total_value
from autotrade.broker.constants import SIDE_BUY, SIDE_SELL, TEHRAN_TZ
from autotrade.models import Side


def test_buy_payload_shape():
    now = datetime(2026, 10, 16, 19, 17, 58, tzinfo=TEHRAN_TZ)
    payload = EasyTraderClient.build_order_payload(
        side=Side.BUY,
        isin="IRO1FOLD0001",
        symbol_name="فولاد",
        quantity=1,
        price=4540,
        commission=0.003712,
        now=now,
    )
    order = payload["order"]
    assert order["side"] == SIDE_BUY
    assert order["price"] == 4540
    assert order["quantity"] == 1
    assert order["symbolIsin"] == "IRO1FOLD0001"
    assert order["totalValue"] == 4557
    assert order["createDateTime"] == "10/16/2026, 7:17:58 PM"


def test_sell_payload_side_and_value():
    now = datetime(2026, 10, 16, 10, 0, 0, tzinfo=TEHRAN_TZ)
    payload = EasyTraderClient.build_order_payload(
        side=Side.SELL,
        isin="IRO1FOLD0001",
        symbol_name="فولاد",
        quantity=10,
        price=4000,
        commission=0.0088,
        now=now,
    )
    order = payload["order"]
    assert order["side"] == SIDE_SELL
    assert order["totalValue"] == order_total_value(
        side=Side.SELL, price=4000, quantity=10, commission=0.0088
    )
    assert order["createDateTime"] == "10/16/2026, 10:00:00 AM"
