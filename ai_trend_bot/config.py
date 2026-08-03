import tomllib
from datetime import time
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeedCategory(StrEnum):
    """Supported feed categories."""

    OFFICIAL = "official"
    COMMUNITY = "community"
    RESEARCH = "research"


class FeedKind(StrEnum):
    """How a source is fetched."""

    RSS = "rss"
    HACKER_NEWS = "hn"
    HUGGING_FACE = "hf"


class FeedSource(BaseModel):
    """A configured source."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    url: HttpUrl
    category: FeedCategory
    kind: FeedKind = FeedKind.RSS
    # Firehose sources (arXiv returns 200+ entries) would otherwise drown the triage input.
    max_items: int = Field(default=15, ge=1, le=100)


class WatchAccount(BaseModel):
    """A public Threads account to monitor."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    username: str = Field(min_length=1)
    priority: int = Field(ge=1, le=100)
    collect_replies: bool = False

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, raw: str) -> str:
        """Accept either a username or a Threads profile URL."""
        return raw.rstrip("/").rsplit("/", maxsplit=1)[-1].removeprefix("@")


class ThreadsConfig(BaseModel):
    """Threads collection preferences."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    enabled: bool = True
    watch_accounts: tuple[WatchAccount, ...] = ()
    keywords: tuple[str, ...] = ()
    keyword_daily_max: int = Field(default=4, ge=0, le=20)


class DeliveryConfig(BaseModel):
    """Digest schedule and per-run caps."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    timezone: str = "Asia/Seoul"
    send_times: tuple[time, ...]
    per_source_max: int = Field(default=3, ge=1, le=15)


class AppConfig(BaseModel):
    """Complete non-secret application configuration."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    delivery: DeliveryConfig
    threads: ThreadsConfig
    feeds: tuple[FeedSource, ...] = ()


class RuntimeSecrets(BaseSettings):
    """Credentials loaded from environment variables or a local .env file."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        frozen=True,
        validate_default=True,
    )

    telegram_bot_token: SecretStr = Field(default=SecretStr(""), min_length=1)
    telegram_chat_id: str = Field(default="", min_length=1)
    gemini_api_key: SecretStr = Field(default=SecretStr(""), min_length=1)
    gemini_model: str = "gemini-3.1-flash-lite"
    threads_access_token: SecretStr = SecretStr("")


def load_app_config(path: Path) -> AppConfig:
    """Parse a TOML configuration file into a trusted application config."""
    with path.open("rb") as config_file:
        return AppConfig.model_validate(tomllib.load(config_file))
