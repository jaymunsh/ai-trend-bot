from datetime import UTC, datetime

from pydantic import HttpUrl

from ai_trend_bot.models import RawItem, SourceKind
from ai_trend_bot.triage import Category, Verdict, apply_triage


def _item(index: int, source: str = "Example") -> RawItem:
    return RawItem(
        source=source,
        source_kind=SourceKind.FEED,
        title=f"소식 {index}",
        text="본문",
        url=HttpUrl(f"https://example.com/{index}"),
        published_at=datetime(2026, 8, 3, tzinfo=UTC),
        priority=50,
    )


def _verdict(index: int, **overrides: object) -> Verdict:
    base = {
        "index": index,
        "category": Category.RELEASE,
        "keep": True,
        "reason": "사유",
        "event": f"사건 {index}",
        "duplicate_of": None,
        "rank": index + 1,
    }
    return Verdict.model_validate(base | overrides)


def test_tutorial_is_dropped_even_when_model_says_keep() -> None:
    # Given: the model marked a how-to as worth keeping.
    items = (_item(0), _item(1))
    verdicts = (_verdict(0), _verdict(1, category=Category.TUTORIAL, keep=True))

    # When
    selection = apply_triage(items, verdicts, limit=10)

    # Then: category is enforced in code, not left to the model.
    assert [selected.item for selected in selection.kept] == [items[0]]
    assert any("튜토리얼" in dropped.reason for dropped in selection.dropped)


def test_duplicates_merge_into_their_representative() -> None:
    # Given: two outlets covering the item at index 0.
    items = (_item(0, "OpenAI"), _item(1, "TechCrunch"), _item(2, "Ars"))
    verdicts = (_verdict(0), _verdict(1, duplicate_of=0), _verdict(2, duplicate_of=0))

    # When
    selection = apply_triage(items, verdicts, limit=10)

    # Then
    assert len(selection.kept) == 1
    assert selection.kept[0].merged == (items[1], items[2])
    assert all("중복" in dropped.reason for dropped in selection.dropped)


def test_duplicate_of_a_rejected_item_is_not_resurrected() -> None:
    # Given: the representative itself failed the bar.
    items = (_item(0), _item(1))
    verdicts = (_verdict(0, keep=False), _verdict(1, duplicate_of=0))

    # When
    selection = apply_triage(items, verdicts, limit=10)

    # Then
    assert selection.kept == ()
    assert len(selection.dropped) == 2


def test_kept_items_follow_rank_and_respect_the_cap() -> None:
    # Given: ranks deliberately out of input order.
    items = tuple(_item(index) for index in range(4))
    verdicts = (_verdict(0, rank=4), _verdict(1, rank=1), _verdict(2, rank=3), _verdict(3, rank=2))

    # When
    selection = apply_triage(items, verdicts, limit=2)

    # Then
    assert [selected.item for selected in selection.kept] == [items[1], items[3]]
    assert any("상한" in dropped.reason for dropped in selection.dropped)


def test_items_without_a_verdict_are_dropped_not_sent() -> None:
    # Given: the model skipped index 1.
    items = (_item(0), _item(1))

    # When
    selection = apply_triage(items, (_verdict(0),), limit=10)

    # Then: a missing verdict must never mean "send it".
    assert [selected.item for selected in selection.kept] == [items[0]]
    assert selection.dropped[0].item == items[1]
