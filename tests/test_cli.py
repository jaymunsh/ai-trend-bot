from pathlib import Path

from typer.testing import CliRunner

from ai_trend_bot.cli import app


def test_check_config_when_sample_is_valid() -> None:
    # Given
    runner = CliRunner()
    config_path = Path("config/sources.toml")

    # When
    result = runner.invoke(app, ["check-config", "--config", str(config_path)])

    # Then
    assert result.exit_code == 0
    assert "설정 파일 정상" in result.stdout
