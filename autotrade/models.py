from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def api_code(self) -> int:
        """EasyTrader OMS side: 0 = buy, 1 = sell."""
        return 0 if self is Side.BUY else 1

    @property
    def label_fa(self) -> str:
        return "خرید" if self is Side.BUY else "فروش"


class PriceMode(str, Enum):
    AUTO = "auto"
    CEILING = "ceiling"
    FLOOR = "floor"
    REFERENCE = "reference"
    FIXED = "fixed"

    def resolve_for(self, side: Side) -> PriceMode:
        """`auto` → ceiling for buys, floor for sells."""
        if self is PriceMode.AUTO:
            return PriceMode.CEILING if side is Side.BUY else PriceMode.FLOOR
        return self


class PreparedOrder(BaseModel):
    side: Side
    symbol: str
    isin: str
    quantity: int = Field(gt=0)
    price: int = Field(gt=0)
    price_mode: PriceMode
    commission: float = Field(ge=0)
    order_value: int = Field(ge=0)
    high_allowed: int | None = None
    low_allowed: int | None = None
    closing: int | None = None
    buying_power: int | None = None
    market_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price_mode", mode="before")
    @classmethod
    def _coerce_mode(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower()
        return v
