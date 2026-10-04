# pyright: reportPrivateUsage=false
import asyncio
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx2
import pytest
from pydantic import HttpUrl

import ai_trend_bot.pipeline as module
from ai_trend_bot.config import AppConfig, DeliveryConfig, FeedCategory, FeedSource, ThreadsConfig
from ai_trend_bot.gemini import GenerationLimitError, SummaryMismatchError
from ai_trend_bot.models import DigestItem, RawItem, SourceKind
from ai_trend_bot.pipeline import BotPipeline, PipelineClients, RunOptions
from ai_trend_bot.store import SentLog
from ai_trend_bot.telegram import SEOUL
from ai_trend_bot.triage import Verdict


def raw(index, *, source="Example", hours=0, priority=20, known=True):
    return RawItem(
        source=source,
        source_kind=SourceKind.FEED,
        title=f"News {index}",
        text="facts",
        url=HttpUrl(f"https://example.com/{index}"),
        priority=priority,
        published_at=datetime.now(tz=UTC) - timedelta(hours=hours),
        published_at_known=known,
    )


def config(*feeds):
    return AppConfig(
        delivery=DeliveryConfig(send_times=(time(7, 30), time(13, 30), time(19, 30))),
        threads=ThreadsConfig(enabled=False),
        feeds=feeds,
    )


def feed(name="Example", cap=2):
    return FeedSource(
        name=name, url=HttpUrl("https://example.com/feed"), category=FeedCategory.COMMUNITY, max_items=cap
    )


def pipeline(tmp_path, **clients):
    editorial = tmp_path / "editorial.md"
    editorial.write_text("editorial")
    dependencies = PipelineClients(
        feeds=clients.get("feeds", Mock()),
        gemini=clients.get("gemini", Mock()),
        telegram=clients.get("telegram", Mock()),
        http=clients.get("http", Mock()),
    )
    return BotPipeline(dependencies, SentLog(tmp_path / "sent.jsonl"), editorial)


def test_collect_filters_before_source_cap_and_orders_newest_first(tmp_path):
    sent, old, fresh, unknown, extra = (
        raw(0),
        raw(1, hours=49),
        raw(2, hours=2),
        raw(3, hours=99, known=False),
        raw(4, hours=3),
    )
    bot = pipeline(tmp_path, feeds=SimpleNamespace(fetch=AsyncMock(return_value=(sent, old, extra, fresh, unknown))))
    bot._log.mark((DigestItem(title=sent.title, summary="sent", source_url=sent.url, source_label=sent.source),))
    items, warnings = asyncio.run(bot._collect(config(feed(cap=3))))
    assert [item.key for item in items] == [fresh.key, extra.key, unknown.key]
    assert any("게시일" in warning for warning in warnings)


def test_collect_prefers_official_for_repeated_url_and_isolates_failure(tmp_path):
    official = raw(1, source="Official", priority=80)
    community = raw(1, source="Community", priority=20)

    async def fetch(source):
        if source.name == "Broken":
            message = "bad feed"
            raise ValueError(message)
        return (official,) if source.name == "Official" else (community, raw(2, source="Community"))

    bot = pipeline(tmp_path, feeds=SimpleNamespace(fetch=fetch))
    items, warnings = asyncio.run(bot._collect(config(feed("Official"), feed("Community"), feed("Broken"))))
    assert [item.source for item in items] == ["Official", "Community"]
    assert len(warnings) == 1
    assert "Broken" in warnings[0]


def verdict(index, **changes):
    return Verdict.model_validate(
        {
            "index": index,
            "category": "모델·제품 출시",
            "keep": True,
            "reason": "new facts",
            "event": f"event {index}",
            "rank": index + 1,
        }
        | changes
    )


def test_triage_keeps_merged_sources_through_final_round(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "TRIAGE_BATCH", 2)
    triage = AsyncMock(
        side_effect=[
            (verdict(0), verdict(1, duplicate_of=0)),
            (verdict(0), verdict(1, duplicate_of=0)),
            (verdict(0), verdict(1, duplicate_of=0)),
        ]
    )
    items = tuple(raw(i) for i in range(4))
    bot = pipeline(tmp_path, gemini=SimpleNamespace(triage=triage))
    selection = asyncio.run(bot._triage(items, limit=50))
    assert selection.kept[0].merged == items[1:]


def test_single_triage_round_reports_cap_and_empty_final_never_calls_model(tmp_path, monkeypatch):
    triage = AsyncMock(return_value=(verdict(0), verdict(1)))
    bot = pipeline(tmp_path, gemini=SimpleNamespace(triage=triage))
    selection = asyncio.run(bot._triage((raw(0), raw(1)), limit=1))
    assert len(selection.kept) == 1
    assert any("상한" in dropped.reason for dropped in selection.dropped)
    monkeypatch.setattr(module, "TRIAGE_BATCH", 1)
    triage = AsyncMock(return_value=(verdict(0, keep=False),))
    bot = pipeline(tmp_path, gemini=SimpleNamespace(triage=triage))
    assert asyncio.run(bot._triage((raw(0), raw(1)), limit=50)).kept == ()
    assert triage.await_count == 2


def test_thirty_summaries_use_one_request_and_keep_order(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    items = tuple(raw(i) for i in range(30))

    async def summarize(batch):
        return tuple(
            DigestItem(title=item.title, summary="one factual sentence", source_url=item.url, source_label=item.source)
            for item in batch
        )

    summaries = AsyncMock(side_effect=summarize)
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=tuple(verdict(i) for i in range(30))), summarize=summaries
        ),
        http=None,
    )
    bot._collect = AsyncMock(return_value=(items, []))
    result = asyncio.run(bot.run(config(), RunOptions(limit=30, dry_run=True)))
    assert tuple(item.source_url for item in result.items) == tuple(item.url for item in items)
    assert summaries.await_count == 1


def test_summary_splits_only_after_confirmed_output_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    items = tuple(raw(i) for i in range(25))
    batch_sizes: list[int] = []

    async def summarize(batch):
        batch_sizes.append(len(batch))
        if len(batch) > 10:
            message = "output limit"
            raise GenerationLimitError(message)
        return tuple(
            DigestItem(title=item.title, summary="facts", source_url=item.url, source_label=item.source)
            for item in batch
        )

    summaries = AsyncMock(side_effect=summarize)
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=tuple(verdict(i) for i in range(25))), summarize=summaries
        ),
    )
    bot._collect = AsyncMock(return_value=(items, []))
    result = asyncio.run(bot.run(config(), RunOptions(limit=30, dry_run=True)))
    assert batch_sizes == [25, 10, 10, 5]
    assert tuple(item.source_url for item in result.items) == tuple(item.url for item in items)


@pytest.mark.parametrize("count", [1, 10])
def test_small_output_limited_summary_is_not_repeated(tmp_path, monkeypatch, count):
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    summaries = AsyncMock(side_effect=GenerationLimitError("output limit"))
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=tuple(verdict(i) for i in range(count))), summarize=summaries
        ),
    )
    bot._collect = AsyncMock(return_value=(tuple(raw(i) for i in range(count)), []))
    with pytest.raises(GenerationLimitError):
        asyncio.run(bot.run(config(), RunOptions(limit=30, dry_run=True)))
    assert summaries.await_count == 1


def test_failed_fallback_does_not_send_or_record_partial_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    items = tuple(raw(i) for i in range(15))
    first_batch = tuple(
        DigestItem(title=item.title, summary="facts", source_url=item.url, source_label=item.source)
        for item in items[:10]
    )
    summaries = AsyncMock(side_effect=[GenerationLimitError("output limit"), first_batch, ValueError("bad response")])
    send = Mock()
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=tuple(verdict(i) for i in range(15))), summarize=summaries
        ),
        telegram=SimpleNamespace(send=send),
    )
    bot._collect = AsyncMock(return_value=(items, []))
    with pytest.raises(ValueError, match="bad response"):
        asyncio.run(bot.run(config(), RunOptions(limit=30, dry_run=False)))
    send.assert_not_called()
    assert not (tmp_path / "sent.jsonl").exists()


@pytest.mark.parametrize(
    "error",
    [
        SummaryMismatchError(expected_count=15, actual_count=14),
        httpx2.HTTPStatusError(
            "quota exhausted",
            request=httpx2.Request("POST", "https://example.com/generate"),
            response=httpx2.Response(429),
        ),
    ],
)
def test_quota_or_incomplete_summary_does_not_trigger_split_requests(tmp_path, monkeypatch, error):
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    summaries = AsyncMock(side_effect=error)
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=tuple(verdict(i) for i in range(15))), summarize=summaries
        ),
    )
    bot._collect = AsyncMock(return_value=(tuple(raw(i) for i in range(15)), []))
    with pytest.raises(type(error)):
        asyncio.run(bot.run(config(), RunOptions(limit=30, dry_run=True)))
    assert summaries.await_count == 1


def test_scheduled_run_waits_after_summaries_and_records_only_delivered_chunks(tmp_path, monkeypatch):

    order = []
    items = (raw(0), raw(1))

    async def summarize(batch):
        order.append("summarize")
        return tuple(
            DigestItem(title=item.title, summary="facts", source_url=item.url, source_label=item.source)
            for item in batch
        )

    async def wait(_target):
        order.append("wait")

    async def send(digest, _header):
        order.append("send")
        yield (digest[0],)
        message = "second message failed"
        raise ValueError(message)

    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    monkeypatch.setattr(module, "wait_until", wait)
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(triage=AsyncMock(return_value=(verdict(0), verdict(1))), summarize=summarize),
        telegram=SimpleNamespace(send=send),
        http=None,
    )
    bot._collect = AsyncMock(return_value=(items, []))
    with pytest.raises(ValueError, match="second message"):
        asyncio.run(
            bot.run(config(), RunOptions(limit=50, dry_run=False, send_at=datetime(2026, 10, 4, 7, 30, tzinfo=SEOUL)))
        )
    assert order == ["summarize", "wait", "send"]
    assert SentLog(tmp_path / "sent.jsonl").unseen(tuple(item.key for item in items)) == (items[1].key,)


def test_scheduled_dry_run_never_waits_or_records(tmp_path, monkeypatch):

    item = raw(0)
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))
    wait = AsyncMock()
    monkeypatch.setattr(module, "wait_until", wait)
    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=(verdict(0),)),
            summarize=AsyncMock(
                return_value=(
                    DigestItem(title=item.title, summary="facts", source_url=item.url, source_label=item.source),
                )
            ),
        ),
        http=None,
    )
    bot._collect = AsyncMock(return_value=((item,), []))
    result = asyncio.run(
        bot.run(config(), RunOptions(limit=50, dry_run=True, send_at=datetime(2026, 10, 4, 7, 30, tzinfo=SEOUL)))
    )
    assert len(result.items) == 1
    wait.assert_not_awaited()
    assert not (tmp_path / "sent.jsonl").exists()


def test_send_guard_rechecks_history_after_preparation(tmp_path, monkeypatch):
    item = raw(0)
    monkeypatch.setattr(module, "fetch_body", AsyncMock(side_effect=lambda client, item: item))

    async def wait(_target):
        SentLog(tmp_path / "sent.jsonl").mark(
            (
                DigestItem(
                    title="Manual send",
                    summary="facts",
                    source_url=HttpUrl("https://example.com/manual"),
                    source_label="Example",
                ),
            )
        )

    monkeypatch.setattr(module, "wait_until", wait)

    send = Mock()

    bot = pipeline(
        tmp_path,
        gemini=SimpleNamespace(
            triage=AsyncMock(return_value=(verdict(0),)),
            summarize=AsyncMock(
                return_value=(
                    DigestItem(title=item.title, summary="facts", source_url=item.url, source_label=item.source),
                )
            ),
        ),
        telegram=SimpleNamespace(send=send),
        http=None,
    )
    bot._collect = AsyncMock(return_value=((item,), []))
    result = asyncio.run(
        bot.run(
            config(),
            RunOptions(limit=50, dry_run=False, send_at=datetime(2026, 10, 4, 7, 30, tzinfo=SEOUL), min_gap_hours=3),
        )
    )
    assert result.skipped
    send.assert_not_called()
    assert SentLog(tmp_path / "sent.jsonl").unseen((item.key,)) == (item.key,)


def test_repeated_url_can_use_another_source_when_preferred_source_is_full(tmp_path):
    latest = raw(1, source="Official", priority=80)
    repeated = raw(2, source="Official", hours=1, priority=80)
    alternate = repeated.model_copy(update={"source": "Community", "priority": 20})

    async def fetch(source):
        return (latest, repeated) if source.name == "Official" else (alternate,)

    bot = pipeline(tmp_path, feeds=SimpleNamespace(fetch=fetch))
    items, _ = asyncio.run(bot._collect(config(feed("Official", cap=1), feed("Community", cap=1))))
    assert tuple(item.key for item in items) == (latest.key, repeated.key)
    assert items[1].source == "Community"
