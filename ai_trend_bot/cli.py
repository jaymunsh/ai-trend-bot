import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Final
from zoneinfo import ZoneInfo

import anyio
import httpx2
import typer
from pydantic import ValidationError
from rich.console import Console

from ai_trend_bot.config import RuntimeSecrets, load_app_config
from ai_trend_bot.feeds import FeedClient
from ai_trend_bot.gemini import GeminiClient, SummaryMismatchError
from ai_trend_bot.http_client import create_async_client
from ai_trend_bot.pipeline import BotPipeline, PipelineClients, RunOptions, RunResult
from ai_trend_bot.scheduling import delivery_target
from ai_trend_bot.store import SentLog
from ai_trend_bot.telegram import TelegramClient, render_digest_chunks

app = typer.Typer(help="AI 트렌드 텔레그램 봇 관리 도구")
console = Console()
DEFAULT_CONFIG_PATH: Final = Path("config/sources.toml")
SENT_LOG_PATH: Final = Path("data/sent.jsonl")
EDITORIAL_PATH: Final = Path("config/editorial.md")


def sent_log_path() -> Path:
    """Where the send log lives. Overridable so a read-only clone can keep state elsewhere."""
    override = os.environ.get("AI_TREND_BOT_SENT_LOG")
    return Path(override) if override else SENT_LOG_PATH


_API_HOST_NAMES: Final = {
    "generativelanguage.googleapis.com": "Gemini",
    "api.telegram.org": "Telegram",
    "graph.threads.net": "Threads",
}


def _api_name(error: httpx2.HTTPError) -> str:
    """Name the external service that failed, so a one-line log says who it was."""
    request = error.request
    return _API_HOST_NAMES.get(request.url.host, request.url.host)


@dataclass(frozen=True, slots=True)
class CliRunSettings:
    config_path: Path
    limit: int
    dry_run: bool
    show_dropped: bool
    scheduled: bool = False
    min_gap_hours: float = 0


@app.callback()
def root() -> None:
    """Manage and run the AI trend digest bot."""


@app.command("check-config")
def check_config(
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = DEFAULT_CONFIG_PATH,
) -> None:
    """Validate sources, monitored accounts, and delivery limits."""
    try:
        loaded = load_app_config(config)
    except FileNotFoundError as error:
        console.print(f"[red]설정 파일을 찾을 수 없습니다:[/red] {config}")
        raise typer.Exit(code=2) from error
    except ValidationError as error:
        console.print(f"[red]설정 파일 오류:[/red]\n{error}")
        raise typer.Exit(code=2) from error

    message = " · ".join(
        (
            "[green]설정 파일 정상[/green]",
            f"관심 계정 {len(loaded.threads.watch_accounts)}개",
            f"키워드 {len(loaded.threads.keywords)}개",
            f"피드 {len(loaded.feeds)}개",
            f"발송 {len(loaded.delivery.send_times)}회",
        ),
    )
    console.print(message)


@app.command("run")
def run_digest(  # noqa: PLR0913 — each parameter is a user-facing CLI option
    *,
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = DEFAULT_CONFIG_PATH,
    limit: Annotated[int, typer.Option("--limit", min=1, max=30)] = 30,
    dry_run: Annotated[bool, typer.Option("--dry-run/--send")] = True,
    show_dropped: Annotated[bool, typer.Option("--show-dropped/--no-show-dropped")] = True,
    min_gap_hours: Annotated[float, typer.Option("--min-gap-hours", min=0)] = 0,
    scheduled: Annotated[
        bool, typer.Option("--scheduled/--immediate", help="준비 후 설정된 발송 시각까지 대기")
    ] = False,
) -> None:
    """Collect, triage, summarize, and optionally send one digest run."""
    if not dry_run and _sent_within(min_gap_hours):
        console.print(f"[yellow]최근 {min_gap_hours:g}시간 안에 발송한 기록이 있어 건너뜁니다.[/yellow]")
        return
    settings = CliRunSettings(
        config_path=config,
        limit=limit,
        dry_run=dry_run,
        show_dropped=show_dropped,
        scheduled=scheduled,
        min_gap_hours=min_gap_hours,
    )
    try:
        result = anyio.run(_execute, settings)
    except httpx2.HTTPStatusError as error:
        console.print(
            f"[red]외부 API 오류:[/red] {_api_name(error)} HTTP {error.response.status_code}"
        )
        raise typer.Exit(code=1) from error
    except httpx2.RequestError as error:
        console.print(f"[red]외부 API 네트워크 오류:[/red] {_api_name(error)}")
        raise typer.Exit(code=1) from error
    except (ValueError, SummaryMismatchError) as error:
        console.print(f"[red]응답 처리 오류:[/red] {error}")
        raise typer.Exit(code=1) from error

    _report(settings, result)


def _report(settings: CliRunSettings, result: RunResult) -> None:
    for warning in result.warnings:
        console.print(f"[yellow]경고:[/yellow] {warning}")
    if result.skipped:
        return
    # 발송 회차에도 찍는다. 드라이런은 다른 시각의 다른 후보 집합을 보므로,
    # "이 브리핑이 무엇을 버렸는가"에는 그 회차 자신만 답할 수 있다.
    if settings.show_dropped:
        console.print(f"\n[dim]── 탈락 {len(result.dropped)}건 ──[/dim]")
        for drop in result.dropped:
            console.print(f"· {drop.item.title[:60]} — {drop.reason}", style="dim", markup=False)
    if not result.items:
        console.print(f"\n[yellow]후보 {result.candidates}건 중 기준을 통과한 항목이 없습니다.[/yellow]")
        return
    if settings.dry_run:
        console.print()
        for message, _ in render_digest_chunks(result.items, result.header):
            console.print(message, markup=False)
        console.print(f"\n[cyan]드라이런 완료: 후보 {result.candidates}건 → 발송 대상 {len(result.items)}건[/cyan]")
    else:
        console.print(f"[green]텔레그램 발송 완료: 후보 {result.candidates}건 → {len(result.items)}건[/green]")


def _sent_within(hours: float) -> bool:
    """Whether a digest already went out inside the window.

    Backup crons exist because GitHub drops scheduled runs, but candidates are
    "everything unsent", not "new since the last run" — so an unguarded backup
    picks the next best few and sends a second full briefing every time.
    """
    if hours <= 0:
        return False
    last = SentLog(sent_log_path()).last_sent_at()
    return last is not None and datetime.now(tz=UTC) - last < timedelta(hours=hours)


async def _execute(settings: CliRunSettings) -> RunResult:
    config = load_app_config(settings.config_path)
    target = (
        delivery_target(datetime.now(tz=ZoneInfo(config.delivery.timezone)), config.delivery.send_times)
        if settings.scheduled and not settings.dry_run
        else None
    )
    secrets = RuntimeSecrets()
    async with create_async_client() as client:
        clients = PipelineClients(
            feeds=FeedClient(client),
            http=client,
            gemini=GeminiClient(client, secrets.gemini_api_key.get_secret_value(), secrets.gemini_model),
            telegram=TelegramClient(
                client,
                secrets.telegram_bot_token.get_secret_value(),
                secrets.telegram_chat_id,
            ),
        )
        pipeline = BotPipeline(clients, SentLog(sent_log_path()), EDITORIAL_PATH)
        return await pipeline.run(
            config,
            RunOptions(
                limit=settings.limit, dry_run=settings.dry_run, send_at=target, min_gap_hours=settings.min_gap_hours
            ),
        )


@app.command("archive-log")
def archive_log() -> None:
    """Move past delivery months to permanent archives without sending anything."""
    path = sent_log_path()
    SentLog(path).rotate()
    console.print(f"[green]월별 기록 정리 완료:[/green] {path.parent / 'archive'}")
