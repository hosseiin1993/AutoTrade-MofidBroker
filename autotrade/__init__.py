"""Place buy and sell orders on Mofid EasyTrader."""

from autotrade.api import buy, sell
from autotrade.config import Settings, get_settings
from autotrade.logging_setup import setup_logging
from autotrade.models import PriceMode, Side
from autotrade.order import Order, OrderError, TradeError, with_account
from autotrade.session import place_order

__version__ = "0.1.1"

__all__ = [
    "Order",
    "OrderError",
    "PriceMode",
    "Settings",
    "Side",
    "TradeError",
    "buy",
    "get_settings",
    "place_order",
    "sell",
    "setup_logging",
    "with_account",
    "__version__",
]
