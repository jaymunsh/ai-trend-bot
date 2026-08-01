from ai_trend_bot.store import SeenStore


def test_seen_store_when_key_is_marked(tmp_path) -> None:
    # Given
    store = SeenStore(tmp_path / "seen.sqlite3")

    # When
    store.mark(("item-1",))

    # Then
    assert store.unseen(("item-1", "item-2")) == ("item-2",)
