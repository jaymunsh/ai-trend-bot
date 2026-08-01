from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from ai_trend_bot.config import RuntimeSecrets, load_app_config

VALID_CONFIG = """
[delivery]
timezone = "Asia/Seoul"
send_times = ["08:17", "14:17", "20:17"]
daily_max = 45
run_limits = [15, 15, 15]

[threads]
enabled = false
keywords = ["AI agent", "LLM"]
keyword_daily_max = 4

[[threads.watch_accounts]]
username = "example"
priority = 100
collect_replies = false

[[feeds]]
name = "Example AI"
url = "https://example.com/feed.xml"
category = "official"
"""


def test_load_app_config_when_file_is_valid(tmp_path: Path) -> None:
    # Given
    config_path = tmp_path / "sources.toml"
    config_path.write_text(VALID_CONFIG, encoding="utf-8")

    # When
    config = load_app_config(config_path)

    # Then
    assert config.delivery.daily_max == 45
    assert config.delivery.run_limits == (15, 15, 15)
    assert config.threads.watch_accounts[0].username == "example"
    assert config.threads.enabled is False


def test_load_app_config_when_daily_limit_exceeds_cap(tmp_path: Path) -> None:
    # Given
    config_path = tmp_path / "sources.toml"
    config_path.write_text(VALID_CONFIG.replace("daily_max = 45", "daily_max = 61"), encoding="utf-8")

    # When / Then
    with pytest.raises(ValidationError):
        load_app_config(config_path)


def test_runtime_secrets_when_values_are_complete() -> None:
    # Given
    telegram_token = SecretStr("telegram-token")
    gemini_key = SecretStr("gemini-key")
    threads_token = SecretStr("threads-token")

    # When
    secrets = RuntimeSecrets(
        telegram_bot_token=telegram_token,
        telegram_chat_id="12345",
        gemini_api_key=gemini_key,
        threads_access_token=threads_token,
    )

    # Then
    assert secrets.telegram_chat_id == "12345"
    assert secrets.threads_access_token.get_secret_value() == "threads-token"
