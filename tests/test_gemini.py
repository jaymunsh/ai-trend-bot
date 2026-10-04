# pyright: reportPrivateUsage=false
import asyncio
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock

import httpx2
import pytest
from pydantic import HttpUrl

from ai_trend_bot.gemini import GeminiClient, parse_summary
from ai_trend_bot.models import RawItem, SourceKind


@pytest.mark.parametrize("content", [{"parts": [{"text": '{"items":['}]}, None])
def test_generation_detects_output_limit_before_parsing_partial_json(content):
    async def run():
        candidate = {"finishReason": "MAX_TOKENS"}
        if content is not None:
            candidate["content"] = content
        transport = httpx2.MockTransport(lambda request: httpx2.Response(200, json={"candidates": [candidate]}))
        async with httpx2.AsyncClient(transport=transport) as client:
            gemini = GeminiClient(client, "test", "test")
            return await gemini._generate("test", {})

    with pytest.raises(ValueError, match="출력 길이 한도"):
        asyncio.run(run())


def test_parse_summary_when_response_matches_items() -> None:
    # Given
    raw_items = (
        RawItem(
            source="Example",
            source_kind=SourceKind.FEED,
            title="New model",
            text="A faster model was released.",
            url=HttpUrl("https://example.com/model"),
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            priority=80,
        ),
    )
    payload = '{"items":[{"index":0,"title":"새 모델 공개","summary":"더 빠른 모델이 공개됐습니다.","relevance":95}]}'

    # When
    digest = parse_summary(payload, raw_items)

    # Then
    assert digest[0].title == "새 모델 공개"
    assert digest[0].source_label == "Example"


def test_parse_summary_keeps_low_relevance_items() -> None:
    # Given
    raw_items = (
        RawItem(
            source="Example",
            source_kind=SourceKind.FEED,
            title="Office party",
            text="Photos from a company party.",
            url=HttpUrl("https://example.com/party"),
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            priority=80,
        ),
    )
    payload = '{"items":[{"index":0,"title":"사내 행사","summary":"사내 행사 소식입니다.","relevance":20}]}'

    # When
    digest = parse_summary(payload, raw_items)

    # Then
    assert len(digest) == 1
    assert digest[0].title == "사내 행사"


def test_parse_summary_separates_structured_summary_labels() -> None:
    raw_items = (
        RawItem(
            source="Example",
            source_kind=SourceKind.FEED,
            title="New model",
            text="A faster model was released.",
            url=HttpUrl("https://example.com/model"),
            published_at=datetime(2026, 8, 2, tzinfo=UTC),
            priority=80,
        ),
    )
    payload = (
        '{"items":[{"index":0,"title":"새 모델","summary":"핵심: 새 모델 공개. '
        '왜 중요한가: 처리량 개선. 관련 대상: ML 플랫폼 팀.","relevance":90}]}'
    )

    digest = parse_summary(payload, raw_items)

    assert digest[0].summary == ("핵심: 새 모델 공개.\n왜 중요한가: 처리량 개선.\n관련 대상: ML 플랫폼 팀.")


def test_triage_passes_missing_date_as_unknown_to_model():

    raw = RawItem(
        source="Example",
        source_kind=SourceKind.FEED,
        title="Undated",
        text="facts",
        url=HttpUrl("https://example.com/news"),
        published_at=datetime.now(tz=UTC),
        published_at_known=False,
        priority=20,
    )

    async def run():
        async with httpx2.AsyncClient() as client:
            gemini = GeminiClient(client, "test", "test")
            generate = AsyncMock(return_value='{"items":[]}')
            gemini._generate = generate
            await gemini.triage((raw,), editorial="facts", recent_events=())
            return cast("str", generate.call_args.args[0])

    assert '"published_at": null' in asyncio.run(run())


def test_triage_distinguishes_simple_repetition_from_meaningful_followups():
    raw = RawItem(
        source="Example",
        source_kind=SourceKind.FEED,
        title="Followup",
        text="new confirmed price",
        url=HttpUrl("https://example.com/followup"),
        published_at=datetime.now(tz=UTC),
        priority=20,
    )

    async def run():
        async with httpx2.AsyncClient() as client:
            gemini = GeminiClient(client, "test", "test")
            generate = AsyncMock(return_value='{"items":[]}')
            gemini._generate = generate
            await gemini.triage((raw,), editorial="facts", recent_events=())
            return cast("str", generate.call_args.args[0])

    prompt = asyncio.run(run())
    assert "새 사실이 있는 후속 보도는 duplicate_of=null" in prompt
    assert "단순 반복일 때만" in prompt
