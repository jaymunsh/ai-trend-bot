from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

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
from ai_trend_bot.store import SeenStore
from ai_trend_bot.telegram import TelegramClient, render_digest
from ai_trend_bot.threads import ThreadsClient

app = typer.Typer(help="AI 트렌드 텔레그램 봇 관리 도구")
console = Console()
DEFAULT_CONFIG_PATH: Final = Path("config/sources.toml")
DEFAULT_DB_PATH: Final = Path(".data/seen.sqlite3")


@dataclass(frozen=True, slots=True)
class CliRunSettings:
    config_path: Path
    limit: int
    dry_run: bool


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
            f"하루 최대 {loaded.delivery.daily_max}개",
        ),
    )
    console.print(message)


@app.command("run")
def run_digest(
    config: Annotated[Path, typer.Option("--config", exists=True, dir_okay=False)] = DEFAULT_CONFIG_PATH,
    limit: Annotated[int, typer.Option("--limit", min=1, max=20)] = 6,
    dry_run: Annotated[bool, typer.Option("--dry-run/--send")] = True,
) -> None:
    """Collect, summarize, and optionally send one digest run."""
    settings = CliRunSettings(config_path=config, limit=limit, dry_run=dry_run)
    try:
        result = anyio.run(_execute, settings)
    except httpx2.HTTPStatusError as error:
        console.print(f"[red]외부 API 오류:[/red] HTTP {error.response.status_code}")
        raise typer.Exit(code=1) from error
    except httpx2.RequestError as error:
        console.print("[red]외부 API 네트워크 오류가 발생했습니다.[/red]")
        raise typer.Exit(code=1) from error
    except (ValidationError, SummaryMismatchError) as error:
        console.print(f"[red]응답 처리 오류:[/red] {error}")
        raise typer.Exit(code=1) from error

    for warning in result.warnings:
        console.print(f"[yellow]건너뜀:[/yellow] {warning}")
    if not result.items:
        console.print("[yellow]새로 보낼 항목이 없습니다.[/yellow]")
        return
    if settings.dry_run:
        console.print(render_digest(result.items))
        console.print(f"\n[cyan]드라이런 완료: {len(result.items)}개[/cyan]")
    else:
        console.print(f"[green]텔레그램 발송 완료: {len(result.items)}개[/green]")


async def _execute(settings: CliRunSettings) -> RunResult:
    config = load_app_config(settings.config_path)
    secrets = RuntimeSecrets()
    async with create_async_client() as client:
        clients = PipelineClients(
            feeds=FeedClient(client),
            threads=ThreadsClient(client, secrets.threads_access_token.get_secret_value()),
            gemini=GeminiClient(client, secrets.gemini_api_key.get_secret_value(), secrets.gemini_model),
            telegram=TelegramClient(
                client,
                secrets.telegram_bot_token.get_secret_value(),
                secrets.telegram_chat_id,
            ),
        )
        pipeline = BotPipeline(clients, SeenStore(DEFAULT_DB_PATH))
        return await pipeline.run(config, RunOptions(limit=settings.limit, dry_run=settings.dry_run))
