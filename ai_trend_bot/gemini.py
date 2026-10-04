import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Final, final

import anyio
import httpx2
from pydantic import BaseModel, ConfigDict, Field

from ai_trend_bot.models import DigestItem, RawItem
from ai_trend_bot.triage import Verdict, VerdictBatch

GENERATION_TIMEOUT: Final = 300.0
# The transport retries connection failures but not HTTP statuses, and a single
# transient 503 would otherwise cost a whole digest run.
RETRY_STATUSES: Final = frozenset({429, 500, 502, 503, 504})
RETRY_DELAYS: Final = (5.0, 20.0, 60.0)


class SummaryItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


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


def _format_summary(summary: str) -> str:
    formatted = summary
    for label in ("왜 중요한가:", "관련 대상:", "확인할 점:", "실무 포인트:"):
        formatted = formatted.replace(f" {label}", f"\n{label}")
    return formatted


def parse_summary(payload: str, raw_items: Sequence[RawItem]) -> tuple[DigestItem, ...]:
    batch = SummaryBatch.model_validate_json(payload)
    by_index = {item.index: item for item in batch.items}
    if len(by_index) != len(raw_items) or any(index not in by_index for index in range(len(raw_items))):
        raise SummaryMismatchError(expected_count=len(raw_items), actual_count=len(by_index))
    return tuple(
        DigestItem(
            title=by_index[index].title,
            summary=_format_summary(by_index[index].summary),
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

    async def _post(self, prompt: str, schema: dict[str, object]) -> httpx2.Response:
        return await self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            params={"key": self._api_key},
            # Triaging a few hundred candidates emits tens of thousands of tokens, well past
            # the client default. Kept local so a slow feed still fails fast.
            timeout=GENERATION_TIMEOUT,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                },
            },
        )

    async def _generate(self, prompt: str, schema: dict[str, object]) -> str:
        response = await self._post(prompt, schema)
        for delay in RETRY_DELAYS:
            if response.status_code not in RETRY_STATUSES:
                break
            await anyio.sleep(delay)
            response = await self._post(prompt, schema)
        response.raise_for_status()
        parsed = GeminiResponse.model_validate(response.json())
        if not parsed.candidates or not parsed.candidates[0].content.parts:
            return ""
        return parsed.candidates[0].content.parts[0].text

    async def triage(
        self,
        items: Sequence[RawItem],
        *,
        editorial: str,
        recent_events: Sequence[str],
        guidance: str = "",
    ) -> tuple[Verdict, ...]:
        """Classify, deduplicate and rank candidates in one pass.

        Ranking is comparative rather than an absolute score: the model is far more
        consistent answering "which of these matters more" than "rate this 0-100".
        """
        input_items = [
            {
                "index": index,
                "title": item.title,
                "source": item.source,
                "excerpt": item.text[:400],
                "published_at": item.published_at.isoformat() if item.published_at_known else None,
            }
            for index, item in enumerate(items)
        ]
        prompt = (
            "당신은 AI 소식 브리핑의 편집자입니다. 아래 편집 방침에 따라 후보를 심사하세요.\n\n"
            "published_at이 null이면 게시일 미상·오류입니다. 오늘 발표라고 추정하지 마세요.\n"
            f"=== 편집 방침 ===\n{editorial}\n\n"
            "=== 최근 2주간 이미 보낸 사건 ===\n"
            f"{chr(10).join(recent_events) or '(없음)'}\n\n"
            "각 후보에 대해 다음을 판정하세요.\n"
            "- category: 항목의 종류.\n"
            "- event: 이 항목이 다루는 사건을 한 문장으로. 같은 사건이면 같은 표현을 쓰세요.\n"
            "- duplicate_of: 같은 사건을 새 사실 없이 다룬 단순 반복일 때만 대표 후보의 index. "
            "새 사실이 있는 후속 보도는 duplicate_of=null로 반환하세요. "
            "다른 회사의 별개 발표도 null입니다. "
            "가장 원본에 가깝고 정보가 많은 쪽을 대표로 남기세요.\n"
            "- keep: 편집 방침에 비추어 보낼 가치가 있으면 true. "
            "위 '이미 보낸 사건'을 새로운 사실 없이 반복하면 false. "
            "후속 보도라도 새 수치·확정된 결정·가격·출시일·추가 피해 등 판단을 바꾸는 새 사실이 있으면 "
            "통과시킬 수 있습니다. 서로 다른 회사의 별개 발표는 주제가 비슷해도 같은 사건이 아닙니다.\n"
            "- reason: 판정 이유를 한 문장으로. 탈락시킨 경우 특히 구체적으로.\n"
            "- rank: 중요한 순서대로 1부터. 서로 비교해서 매기세요.\n\n"
            f"{guidance}"
            "모든 입력 항목을 빠짐없이 반환하고 입력의 index를 그대로 유지하세요. JSON만 반환하세요.\n"
            f"입력: {json.dumps(input_items, ensure_ascii=False)}"
        )
        payload = await self._generate(prompt, VerdictBatch.model_json_schema())
        if not payload:
            return ()
        return VerdictBatch.model_validate_json(payload).items

    async def summarize(self, items: Sequence[RawItem]) -> tuple[DigestItem, ...]:
        input_items = [
            {"index": index, "title": item.title, "content": item.text, "source": item.source}
            for index, item in enumerate(items)
        ]
        prompt = (
            "다음 AI 관련 항목을 한국어로 번역·요약하세요. 입력 content는 기사 원문입니다. "
            "제목만 바꿔 쓰지 말고 원문에서 구체적인 사실을 끌어내세요. "
            "summary는 모바일에서 대략 2~3줄로 읽을 분량의 짧은 1~2문장으로 작성하세요. "
            "확인된 핵심 사실을 가급적 90~120자로 요약하되, 중요한 조건이 빠진다면 조금 길어도 됩니다. "
            "문장 중간에 임의의 줄바꿈은 넣지 마세요. "
            "제품명·수치·기능·가격·일정 등 구체적인 변화와 조건을 우선하되 중요한 제한을 생략하지 마세요. "
            "'핵심:', '왜 중요한가:', '관련 대상:', '영향:' 같은 항목명이나 독자 구분은 쓰지 마세요. "
            "'활용하세요', '검토하세요' 같은 근거 없는 일반론도 쓰지 마세요. "
            "'획기적', '비약적', '대폭' 같은 과장 표현을 쓰지 말고 입력에 없는 성과나 전망을 추측하지 마세요. "
            "제목은 회사·제품과 실제 변화가 바로 보이도록 가급적 30자 이내로 간결하게 작성하세요. "
            "모든 입력 항목을 빠짐없이 반환하고 입력의 index를 그대로 유지한 뒤 "
            "JSON만 반환하세요.\n"
            f"입력: {json.dumps(input_items, ensure_ascii=False)}"
        )
        payload = await self._generate(prompt, SummaryBatch.model_json_schema())
        if not payload:
            raise SummaryMismatchError(expected_count=len(items), actual_count=0)
        return parse_summary(payload, items)
