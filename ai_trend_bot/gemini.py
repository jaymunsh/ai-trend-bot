import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, final

import httpx2
from pydantic import BaseModel, ConfigDict, Field

from ai_trend_bot.models import DigestItem, RawItem


class SummaryItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    relevance: int = Field(ge=0, le=100)


class SummaryBatch(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[SummaryItem, ...]


class GeminiPart(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    text: str


class GeminiContent(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    parts: tuple[GeminiPart, ...]


class GeminiCandidate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    content: GeminiContent


class GeminiResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    candidates: tuple[GeminiCandidate, ...]


@dataclass(frozen=True, slots=True)
class SummaryMismatchError(Exception):
    expected_count: int
    actual_count: int

    def __str__(self) -> str:
        return f"Gemini summary count mismatch: expected {self.expected_count}, got {self.actual_count}"


def parse_summary(payload: str, raw_items: Sequence[RawItem]) -> tuple[DigestItem, ...]:
    batch = SummaryBatch.model_validate_json(payload)
    by_index = {item.index: item for item in batch.items}
    if len(by_index) != len(raw_items) or any(index not in by_index for index in range(len(raw_items))):
        raise SummaryMismatchError(expected_count=len(raw_items), actual_count=len(by_index))
    return tuple(
        DigestItem(
            title=by_index[index].title,
            summary=by_index[index].summary,
            source_url=raw.url,
            source_label=raw.source,
        )
        for index, raw in enumerate(raw_items)
    )


@final
class GeminiClient:
    def __init__(self, client: httpx2.AsyncClient, api_key: str, model: str) -> None:
        self._client = client
        self._api_key = api_key
        self._model = model

    async def summarize(self, items: Sequence[RawItem]) -> tuple[DigestItem, ...]:
        input_items = [
            {"index": index, "title": item.title, "content": item.text, "source": item.source}
            for index, item in enumerate(items)
        ]
        prompt = (
            "다음 AI 관련 항목을 한국어로 번역·요약하세요. 과장 없이 핵심 사실과 의미를 2~3문장으로 쓰고, "
            "제목은 간결하게 작성하세요. AI 기술·모델·제품·연구·산업에 미치는 중요도를 relevance 0~100으로 "
            "평가하되 이는 참고값일 뿐이므로 모든 입력 항목을 빠짐없이 반환하세요. 입력의 index를 그대로 유지하고 "
            "JSON만 반환하세요.\n"
            f"입력: {json.dumps(input_items, ensure_ascii=False)}"
        )
        response = await self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            params={"key": self._api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": SummaryBatch.model_json_schema(),
                },
            },
        )
        response.raise_for_status()
        parsed = GeminiResponse.model_validate(response.json())
        if not parsed.candidates or not parsed.candidates[0].content.parts:
            raise SummaryMismatchError(expected_count=len(items), actual_count=0)
        return parse_summary(parsed.candidates[0].content.parts[0].text, items)
