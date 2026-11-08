from autotrade.broker.client import buying_power
from autotrade.models import PreparedOrder, PriceMode, Side
from autotrade.trading.submit import (
    SUBMIT_ACCEPTED,
    SUBMIT_NOT_OPEN,
    SUBMIT_REJECTED,
    SUBMIT_THROTTLED,
    cash_changed,
    classify_submit_response,
    order_appears,
)


def test_accepted():
    assert classify_submit_response({"isSuccessful": True}).kind == SUBMIT_ACCEPTED


def test_throttled():
    resp = {
        "isSuccessful": False,
        "omsError": [{"code": 13021, "name": "OrderIntervalError", "error": "interval"}],
    }
    assert classify_submit_response(resp).kind == SUBMIT_THROTTLED


def test_not_open():
    resp = {
        "isSuccessful": False,
        "omsError": [{"code": 11000, "error": "وضعیت گروه اجازه فعالیت نمی‌دهد"}],
    }
    assert classify_submit_response(resp).kind == SUBMIT_NOT_OPEN


def test_ack_without_success_flag_is_rejected():
    outcome = classify_submit_response({"id": "abc", "message": ""})
    assert outcome.kind == SUBMIT_REJECTED


def test_successful_ack_keeps_the_id():
    outcome = classify_submit_response(
        {"isSuccessful": True, "id": "1121", "message": "", "omsError": None}
    )
    assert outcome.kind == SUBMIT_ACCEPTED
    assert outcome.order_id == "1121"


def test_buying_power_uses_t2_when_same_day_power_is_zero():
    assert buying_power({"buyPowerT0": 0, "t2": 50_000_000}) == 50_000_000


def test_cash_changed_sees_a_t2_move():
    assert cash_changed({"t2": 50_000_000, "block": 0}, {"t2": 44_970_898, "block": 0})
    assert cash_changed({"t2": 50_000_000, "block": 0}, {"t2": 50_000_000, "block": 0}) is False


def _prepared() -> PreparedOrder:
    return PreparedOrder(
        side=Side.BUY,
        symbol="تمشک",
        isin="IRT1TMSK0001",
        quantity=92,
        price=54600,
        price_mode=PriceMode.FIXED,
        commission=0.001175,
        order_value=5_029_102,
    )


def test_order_appears_rejects_a_row_that_vanishes():
    class Client:
        def __init__(self) -> None:
            self.calls = 0

        def order_appeared(self, **_kwargs: object) -> bool:
            self.calls += 1
            return self.calls == 1

    clock = {"n": 0}

    def timeout() -> float:
        clock["n"] += 1
        return 0 if clock["n"] < 5 else 10

    assert (
        order_appears(
            Client(),
            _prepared(),
            [],
            deadline_s=5,
            timeout_fn=timeout,
            sleep_fn=lambda _seconds: None,
        )
        is False
    )


def test_rejected():
    resp = {
        "isSuccessful": False,
        "omsError": [{"code": 8006, "error": "حداقل سفارش"}],
    }
    assert classify_submit_response(resp).kind == SUBMIT_REJECTED
