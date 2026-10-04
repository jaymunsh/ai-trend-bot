import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock

import anyio

from ai_trend_bot.scheduling import SEOUL, delivery_target, wait_until

SLOTS = (time(7, 30), time(13, 30), time(19, 30))


def test_delivery_target_at_preparation_start_and_late_start():
    for hour in (7, 13, 19):
        assert delivery_target(datetime(2026, 10, 4, hour, 15, tzinfo=SEOUL), SLOTS) == datetime(
            2026, 10, 4, hour, 30, tzinfo=SEOUL
        )
    assert delivery_target(datetime(2026, 10, 4, 7, 35, tzinfo=SEOUL), SLOTS) == datetime(
        2026, 10, 4, 7, 30, tzinfo=SEOUL
    )
    assert delivery_target(datetime(2026, 10, 4, 0, 0, tzinfo=SEOUL), SLOTS) == datetime(
        2026, 10, 4, 7, 30, tzinfo=SEOUL
    )
    assert delivery_target(datetime(2026, 10, 4, 23, 0, tzinfo=SEOUL), SLOTS) == datetime(
        2026, 10, 5, 7, 30, tzinfo=SEOUL
    )


def test_wait_until_waits_only_remaining_time_and_skips_late_completion(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr(anyio, "sleep", sleep)
    target = datetime(2026, 10, 4, 13, 30, tzinfo=SEOUL)
    asyncio.run(wait_until(target, now=datetime(2026, 10, 4, 13, 8, tzinfo=SEOUL)))
    sleep.assert_awaited_once_with(22 * 60)
    sleep.reset_mock()
    asyncio.run(wait_until(target, now=datetime(2026, 10, 4, 13, 31, tzinfo=SEOUL)))
    sleep.assert_not_awaited()
