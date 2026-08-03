from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field

from ai_trend_bot.models import RawItem


class Category(StrEnum):
    """What kind of thing an item is.

    Chosen over a 0-100 score because model output clusters in a narrow band,
    which makes any threshold an arbitrary cut.
    """

    RELEASE = "모델·제품 출시"
    RESEARCH = "연구 결과"
    POLICY = "정책·산업·자금"
    TOOL = "도구·오픈소스"
    TUTORIAL = "튜토리얼·사용법"
    PROMO = "홍보·사례소개"
    OTHER = "기타"


DROPPED_CATEGORIES: Final = frozenset({Category.TUTORIAL, Category.PROMO, Category.OTHER})


class Verdict(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    index: int = Field(ge=0)
    category: Category
    keep: bool
    reason: str = Field(min_length=1)
    event: str = Field(min_length=1)
    duplicate_of: int | None = None
    rank: int = Field(ge=1)


class VerdictBatch(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[Verdict, ...]


@dataclass(frozen=True, slots=True)
class Selected:
    item: RawItem
    verdict: Verdict
    merged: tuple[RawItem, ...] = ()


@dataclass(frozen=True, slots=True)
class Dropped:
    item: RawItem
    reason: str


@dataclass(frozen=True, slots=True)
class Selection:
    kept: tuple[Selected, ...]
    dropped: tuple[Dropped, ...]


def apply_triage(items: Sequence[RawItem], verdicts: Sequence[Verdict], *, limit: int) -> Selection:
    """Turn per-item verdicts into what gets sent, and why everything else did not.

    Dropped items carry their reason so a dry run can show what the bar rejected;
    a bar you cannot inspect is a bar you cannot tune.
    """
    by_index = {verdict.index: verdict for verdict in verdicts if 0 <= verdict.index < len(items)}
    keep_order = [
        index
        for index, verdict in sorted(by_index.items(), key=lambda entry: entry[1].rank)
        if verdict.keep and verdict.category not in DROPPED_CATEGORIES and verdict.duplicate_of is None
    ]
    keepable = set(keep_order)

    merged: dict[int, list[RawItem]] = {}
    dropped: list[Dropped] = []
    for index, item in enumerate(items):
        if index in keepable:
            continue
        verdict = by_index.get(index)
        if verdict is None:
            dropped.append(Dropped(item, "선별 결과 없음"))
        elif verdict.duplicate_of in keepable:
            merged.setdefault(verdict.duplicate_of, []).append(item)
            dropped.append(Dropped(item, f"중복: {by_index[verdict.duplicate_of].event}"))
        else:
            dropped.append(Dropped(item, f"[{verdict.category}] {verdict.reason}"))

    dropped.extend(Dropped(items[index], f"상한 {limit}건 초과") for index in keep_order[limit:])

    kept = tuple(Selected(items[index], by_index[index], tuple(merged.get(index, ()))) for index in keep_order[:limit])
    return Selection(kept=kept, dropped=tuple(dropped))
