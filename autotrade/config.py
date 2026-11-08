from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from autotrade.models import PriceMode, Side

# Source checkout root when running from a clone. After `pip install` this is
# site-packages, so runtime files (.env, token cache) must not assume it.
PROJECT_DIR = Path(__file__).resolve().parent.parent


def parse_hhmmss(value: str) -> time:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise ValueError(f"Expected HH:MM:SS, got {value!r}")
    return time(int(parts[0]), int(parts[1]), int(parts[2]))


def resolve_env_file() -> Path | None:
    """Env file for an installed package or a source checkout.

    `AUTOTRADE_ENV` wins. Otherwise the current directory, then a `.env`
    sitting next to the source tree (editable checkout).
    """
    explicit = os.environ.get("AUTOTRADE_ENV", "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"AUTOTRADE_ENV does not exist: {path}")
        return path
    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env
    sibling = PROJECT_DIR / ".env"
    if sibling.is_file():
        return sibling
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def __init__(self, **data: object) -> None:
        if "_env_file" not in data:
            env = resolve_env_file()
            if env is not None:
                data["_env_file"] = env
        super().__init__(**data)

    mofid_user: str = Field(default="", alias="MOFID_USER")
    mofid_pass: str = Field(default="", alias="MOFID_PASS")

    side: Side = Field(default=Side.BUY, alias="SIDE")
    symbol: str = Field(default="", alias="SYMBOL")
    quantity: int = Field(default=0, alias="QUANTITY")
    price_mode: PriceMode = Field(default=PriceMode.AUTO, alias="PRICE_MODE")
    price: int = Field(default=0, alias="PRICE")
    target_time: str = Field(default="08:44:58", alias="TARGET_TIME")

    broker_url: str = Field(default="https://d.easytrader.ir/", alias="BROKER_URL")
    api_base_url: str = Field(
        default="https://api-mts.orbis.easytrader.ir",
        alias="API_BASE_URL",
    )

    max_order_attempts: int = Field(default=20, alias="MAX_ORDER_ATTEMPTS")
    preopen_max_attempts: int = Field(default=30, alias="PREOPEN_MAX_ATTEMPTS")
    submit_interval: float = Field(default=0.35, alias="SUBMIT_INTERVAL")
    min_submit_interval: float = Field(default=0.32, alias="MIN_SUBMIT_INTERVAL")
    order_window_grace: float = Field(default=8.0, alias="ORDER_WINDOW_GRACE")
    verify_order: bool = Field(default=True, alias="VERIFY_ORDER")

    token_cache: bool = Field(default=True, alias="TOKEN_CACHE")
    token_cache_path: str = Field(default=".mofid_token.json", alias="TOKEN_CACHE_PATH")
    token_cache_min_validity: int = Field(default=120, alias="TOKEN_CACHE_MIN_VALIDITY")

    headless: bool = Field(default=False, alias="HEADLESS")
    chrome_user_data_dir: str = Field(default="", alias="CHROME_USER_DATA_DIR")
    instance_id: str = Field(default="", alias="INSTANCE_ID")

    login_max_attempts: int = Field(default=5, alias="LOGIN_MAX_ATTEMPTS")
    login_timeout: float = Field(default=20.0, alias="LOGIN_TIMEOUT")
    clock_poll_interval: float = Field(default=0.05, alias="CLOCK_POLL_INTERVAL")
    clock_deadline_seconds: float = Field(default=3600.0, alias="CLOCK_DEADLINE_SECONDS")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="autotrade.log", alias="LOG_FILE")

    @field_validator("side", mode="before")
    @classmethod
    def _side(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator("price_mode", mode="before")
    @classmethod
    def _mode(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().lower()
        return v

    def target_as_time(self) -> time:
        return parse_hhmmss(self.target_time)

    def token_path(self) -> Path:
        """JWT cache path. Absolute paths are kept. Relative paths use the working directory."""
        path = Path(self.token_cache_path).expanduser()
        if path.is_absolute():
            return path
        return Path.cwd() / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
