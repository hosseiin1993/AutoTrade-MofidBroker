from datetime import time
from pathlib import Path

import pytest

from autotrade.config import Settings, resolve_env_file
from autotrade.models import PriceMode, Side
from autotrade.order import Order, OrderError, with_account


def _settings(**overrides: object) -> Settings:
    data = {
        "mofid_user": "env-user",
        "mofid_pass": "env-pass",
        "symbol": "",
        "quantity": 0,
        "side": Side.BUY,
        "price_mode": PriceMode.AUTO,
        "price": 0,
        "target_time": "08:44:58",
        "token_cache_path": ".mofid_token.json",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_call_credentials_replace_a_copy_of_settings() -> None:
    base = _settings(symbol="فولاد", quantity=1)
    account = with_account(base, "09120000000", "call-secret")
    order = Order.resolve(account, side="buy")
    assert account.mofid_user == "09120000000"
    assert account.mofid_pass == "call-secret"
    assert base.mofid_user == "env-user"
    assert not hasattr(order, "password")


def test_username_without_password_is_rejected() -> None:
    with pytest.raises(OrderError, match="together"):
        with_account(_settings(symbol="فولاد", quantity=1), "09120000000", None)


def test_missing_credentials_are_rejected() -> None:
    with pytest.raises(OrderError, match="username and password"):
        with_account(_settings(mofid_user="", mofid_pass=""))


def test_missing_symbol_is_rejected() -> None:
    with pytest.raises(OrderError, match="symbol"):
        Order.resolve(_settings(), quantity=1)


def test_non_positive_quantity_is_rejected() -> None:
    with pytest.raises(OrderError, match="quantity"):
        Order.resolve(_settings(symbol="فولاد"), quantity=0)


def test_call_arguments_override_settings() -> None:
    order = Order.resolve(
        _settings(symbol="فولاد", quantity=1, side=Side.BUY),
        side="sell",
        quantity=3,
        price_mode="fixed",
        price=4200,
        target_time="09:15:01",
        dry_run=True,
        verify=False,
        use_token_cache=False,
    )
    assert order.side is Side.SELL
    assert order.symbol == "فولاد"
    assert order.quantity == 3
    assert order.price_mode is PriceMode.FIXED
    assert order.price == 4200
    assert order.target_time == time(9, 15, 1)
    assert order.dry_run is True
    assert order.verify is False
    assert order.use_token_cache is False


def test_bad_clock_time_is_rejected() -> None:
    with pytest.raises(OrderError, match="HH:MM:SS"):
        Order.resolve(_settings(symbol="فولاد", quantity=1), target_time="8:45")


def test_now_means_submit_immediately() -> None:
    order = Order.resolve(
        _settings(symbol="فولاد", quantity=1),
        target_time="now",
    )
    assert order.target_time is None


def test_buy_helper_submits_a_resolved_order(monkeypatch: pytest.MonkeyPatch) -> None:
    from autotrade import api

    seen: list[object] = []

    def fake_place(order: Order, settings: Settings) -> None:
        seen.append((order, settings))

    monkeypatch.setattr(api, "place_order", fake_place)
    monkeypatch.setattr(api, "setup_logging", lambda *_args, **_kwargs: None)
    api.buy(
        "فولاد",
        3,
        price_mode="fixed",
        price=4200,
        dry_run=True,
        settings=_settings(),
        configure_logging=False,
    )
    order, account = seen[0]
    assert order.side is Side.BUY
    assert order.symbol == "فولاد"
    assert order.quantity == 3
    assert order.price == 4200
    assert order.target_time is None
    assert order.dry_run is True
    assert account.mofid_user == "env-user"


def test_sell_helper_defaults_to_now(monkeypatch: pytest.MonkeyPatch) -> None:
    from autotrade import api

    seen: list[Order] = []

    def fake_place(order: Order, _settings: Settings) -> None:
        seen.append(order)

    monkeypatch.setattr(api, "place_order", fake_place)
    api.sell("تمشک", 92, settings=_settings(), configure_logging=False)
    assert seen[0].side is Side.SELL
    assert seen[0].target_time is None


def test_explicit_env_file_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "bot.env"
    env.write_text("SYMBOL=اهرم\nQUANTITY=2\n", encoding="utf-8")
    other = tmp_path / ".env"
    other.write_text("SYMBOL=فولاد\nQUANTITY=9\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SYMBOL", raising=False)
    monkeypatch.delenv("QUANTITY", raising=False)
    monkeypatch.setenv("AUTOTRADE_ENV", str(env))
    assert resolve_env_file() == env
    loaded = Settings()
    assert loaded.symbol == "اهرم"
    assert loaded.quantity == 2


def test_missing_explicit_env_file_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTOTRADE_ENV", str(tmp_path / "missing.env"))
    with pytest.raises(FileNotFoundError, match="AUTOTRADE_ENV"):
        resolve_env_file()


def test_relative_token_is_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _settings().token_path() == tmp_path / ".mofid_token.json"


def test_source_tree_token_is_not_a_second_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / ".mofid_token.json").write_text("{}", encoding="utf-8")
    cwd = tmp_path / "bot"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert _settings().token_path() == cwd / ".mofid_token.json"


def test_absolute_token_path_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "tok.json"
    assert _settings(token_cache_path=str(path)).token_path() == path
