from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock

from pydantic import HttpUrl
from typer.testing import CliRunner

from ai_trend_bot import cli
from ai_trend_bot.cli import CliRunSettings, app, console, sent_log_path
from ai_trend_bot.models import RawItem, SourceKind
from ai_trend_bot.pipeline import RunResult
from ai_trend_bot.triage import Dropped


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


def test_report_shows_dropped_when_sending() -> None:
    """탈락 목록은 발송 회차에도 찍혀야 한다.

    드라이런은 다른 시각의 다른 후보 집합을 본다. 그 회차가 실제로 무엇을 버렸는지는
    그 회차의 출력에만 남으므로, 여기가 막히면 며칠치 기준 튜닝 근거가 통째로 사라진다.
    """
    # Given
    item = RawItem(
        source="AWS Machine Learning",
        source_kind=SourceKind.FEED,
        title="How SomeCorp digitizes policies with Bedrock",
        text="도입 사례",
        url=HttpUrl("https://example.com/a"),
        published_at=datetime(2026, 8, 8, tzinfo=UTC),
        priority=50,
    )
    settings = CliRunSettings(config_path=Path("config/sources.toml"), limit=30, dry_run=False, show_dropped=True)
    result = RunResult(
        items=(),
        warnings=(),
        dropped=(Dropped(item, "[홍보·사례소개] 특정 기업의 도입 사례 홍보입니다."),),
        candidates=244,
    )

    # When
    with console.capture() as captured:
        cli._report(settings, result)  # pyright: ignore[reportPrivateUsage]

    # Then
    output = captured.get()
    assert "탈락 1건" in output
    assert "How SomeCorp digitizes policies" in output


def test_cli_defaults_to_thirty_and_rejects_larger_limits(monkeypatch):

    execute = AsyncMock(return_value=RunResult(items=(), warnings=()))
    monkeypatch.setattr(cli, "_execute", execute)
    runner = CliRunner()
    assert runner.invoke(app, ["run", "--dry-run"]).exit_code == 0
    settings = cast("CliRunSettings", execute.call_args.args[0])
    assert settings.limit == 30
    assert runner.invoke(app, ["run", "--dry-run", "--limit", "30"]).exit_code == 0
    assert runner.invoke(app, ["run", "--dry-run", "--limit", "31"]).exit_code == 2
