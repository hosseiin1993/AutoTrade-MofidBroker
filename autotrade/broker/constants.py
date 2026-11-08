from datetime import timedelta, timezone

API_BASE = "https://api-mts.orbis.easytrader.ir"

# Captured from live EasyTrader traffic (buy ticket, 2026-10).
SIDE_BUY = 0
SIDE_SELL = 1
ORDER_MODEL_TYPE = 1
ORDER_FROM = 34
VALIDITY_TYPE_DAY = 0

DEFAULT_BUY_COMMISSION = 0.003712
# Sell fee is typically higher (commission + tax). Prefer marketdata sellRatio.
DEFAULT_SELL_COMMISSION = 0.0088

SUBMIT_INTERVAL_FLOOR_S = 0.32

ORDER_WINDOW_OPEN = (8, 45)
ORDER_WINDOW_CLOSE = (12, 30)

OMS_CODE_ORDER_INTERVAL = 13021
OMS_CODE_ORDER_WINDOW = 8702
OMS_CODE_GROUP_INACTIVE = 11000
OMS_CODE_MIN_ORDER_VALUE = 8006
OMS_CODES_NOT_OPEN = frozenset({OMS_CODE_ORDER_WINDOW, OMS_CODE_GROUP_INACTIVE})

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))

# The order ticket uses t2 as buying power. buyPowerT0 can be 0 while t2 holds the cash.
BUY_POWER_KEYS = ("t2", "buyPowerT2", "buyPowerT1", "t1", "t0", "buyPowerT0")

READ_TIMEOUT_MS = 10_000
MIN_TOKEN_LEN = 64
