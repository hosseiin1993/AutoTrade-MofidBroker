import pytest

from autotrade.models import PriceMode, Side
from autotrade.trading.price import PriceError, resolve_price

MD = {
    "highAllowedPrice": 5000,
    "lowAllowedPrice": 4000,
    "closingPrice": 4500,
}


def test_auto_buy_uses_ceiling():
    price, mode = resolve_price(MD, side=Side.BUY, price_mode=PriceMode.AUTO)
    assert price == 5000
    assert mode is PriceMode.CEILING


def test_auto_sell_uses_floor():
    price, mode = resolve_price(MD, side=Side.SELL, price_mode=PriceMode.AUTO)
    assert price == 4000
    assert mode is PriceMode.FLOOR


def test_fixed_requires_price():
    with pytest.raises(PriceError):
        resolve_price(MD, side=Side.BUY, price_mode=PriceMode.FIXED, fixed_price=0)


def test_reference():
    price, mode = resolve_price(MD, side=Side.BUY, price_mode=PriceMode.REFERENCE)
    assert price == 4500
    assert mode is PriceMode.REFERENCE
