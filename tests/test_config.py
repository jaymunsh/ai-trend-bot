from pathlib import Path

from pydantic import SecretStr

from ai_trend_bot.config import RuntimeSecrets, load_app_config

VALID_CONFIG = """
[delivery]
timezone = "Asia/Seoul"
send_times = ["07:30", "13:30", "19:30"]
per_source_max = 3

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
    assert config.delivery.per_source_max == 3
    assert config.threads.watch_accounts[0].username == "example"
    assert config.threads.enabled is False


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
