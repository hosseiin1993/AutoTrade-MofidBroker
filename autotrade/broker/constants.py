from datetime import timedelta, timezone

API_BASE = "https://api-mts.orbis.easytrader.ir"

# Captured from live EasyTrader traffic (buy ticket, 2026-10).
SIDE_BUY = 0
SIDE_SELL = 1
ORDER_MODEL_TYPE = 1
ORDER_FROM = 34
VALIDITY_TYPE_DAY = 0

# Same paths the EasyTrader 2.6.1 web app calls (orderUrl + these suffixes).
ORDER_LIST_PATH = "/core/api/order"
ORDER_SUBMIT_PATH = "/core/api/v2/order"
ORDER_DELETE_PATH = "/core/api/v2/delete-order"

# TSE standard-market minimum. EasyTrader uses 5e6 Rial for that check.
MIN_NOTIONAL_RIAL = 5_000_000

# orderState codes from the EasyTrader web app.
ORDER_STATE_NONE = 0
ORDER_STATE_MODIFY = 1
ORDER_STATE_ERROR = 2
ORDER_STATE_CANCEL = 3
ORDER_STATE_ON_BOARD = 6
ORDER_STATE_PARTIALLY = 8
ORDER_STATE_ON_CANCELING = 9
ORDER_STATE_ON_MODIFY_BOARD = 19
ORDER_STATE_EXECUTED = 20
ORDER_STATE_IN_OMS_QUEUE = 28
ORDER_STATE_OPEN = 29

ORDER_STATE_NAMES = {
    ORDER_STATE_NONE: "None",
    ORDER_STATE_MODIFY: "Modify",
    ORDER_STATE_ERROR: "Error",
    ORDER_STATE_CANCEL: "Cancel",
    4: "CancelBySurveillance",
    5: "Done",
    ORDER_STATE_ON_BOARD: "OnBoard",
    7: "OnSending",
    ORDER_STATE_PARTIALLY: "PartiallyExecution",
    ORDER_STATE_ON_CANCELING: "OnCanceling",
    10: "OnCancelError",
    11: "OnModifyError",
    12: "DeleteByBroker",
    13: "Expired",
    14: "PartiallyExecutedAndExpired",
    15: "PartiallyExecutedAndModified",
    16: "OnModifying",
    17: "DeleteByNsc",
    18: "CancelByBroker",
    ORDER_STATE_ON_MODIFY_BOARD: "OnModifyBoard",
    ORDER_STATE_EXECUTED: "OrderExecuted",
    24: "CancelOrderConfirmed",
    ORDER_STATE_IN_OMS_QUEUE: "InOmsQueue",
    ORDER_STATE_OPEN: "Open",
    35: "PartiallyExecutedAndError",
    36: "PartiallyExecutedAndCanceled",
    40: "DeleteBySupervisor",
}
# IsEditValid / U$7, plus board states that still hold an open remainder.
OPEN_ORDER_STATES = frozenset(
    {
        ORDER_STATE_NONE,
        ORDER_STATE_ON_BOARD,
        ORDER_STATE_PARTIALLY,
        10,
        11,
        ORDER_STATE_ON_MODIFY_BOARD,
        ORDER_STATE_IN_OMS_QUEUE,
        ORDER_STATE_OPEN,
    }
)
# IsDeleteValid also allows Error. Modify (1) is the replaced parent — not actionable.
DELETABLE_ORDER_STATES = OPEN_ORDER_STATES | {ORDER_STATE_ERROR}
CANCELLED_ORDER_STATES = frozenset({3, 4, 12, 13, 14, 17, 18, 24, 36, 40})
EXECUTED_ORDER_STATES = frozenset({ORDER_STATE_EXECUTED})

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
