"""Place, edit, and cancel orders on Mofid EasyTrader."""

from autotrade.api import buy, cancel_order, edit_order, list_orders, sell
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
    "cancel_order",
    "edit_order",
    "get_settings",
    "list_orders",
    "place_order",
    "sell",
    "setup_logging",
    "with_account",
    "__version__",
]
