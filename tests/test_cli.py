from pathlib import Path

from typer.testing import CliRunner

from ai_trend_bot.cli import app, sent_log_path


def test_check_config_when_sample_is_valid() -> None:
    # Given
    runner = CliRunner()
    config_path = Path("config/sources.toml")

    # When
    result = runner.invoke(app, ["check-config", "--config", str(config_path)])

    # Then
    assert result.exit_code == 0
    assert "설정 파일 정상" in result.stdout


def test_sent_log_path_when_env_is_unset(monkeypatch) -> None:
    # Given
    monkeypatch.delenv("AI_TREND_BOT_SENT_LOG", raising=False)

    # When
    path = sent_log_path()

    # Then
    assert path == Path("data/sent.jsonl")


def test_sent_log_path_when_env_overrides_it(monkeypatch, tmp_path) -> None:
    # Given
    override = tmp_path / "state" / "sent.jsonl"
    monkeypatch.setenv("AI_TREND_BOT_SENT_LOG", str(override))

    # When
    path = sent_log_path()

    # Then
    assert path == override
