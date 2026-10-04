from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import anyio

SEOUL: Final = ZoneInfo("Asia/Seoul")
# Late-start tolerance is independent of how early cron starts preparation.
LATE_START_GRACE_MINUTES: Final = 30


def delivery_target(now: datetime, slots: Sequence[time]) -> datetime:
    """Pin a scheduled run to its delivery slot before doing any preparation.

    A startup up to 30 minutes late still belongs to the missed slot. Otherwise
    choose the next slot, including the next day. Manual runs need no target.
    """
    if not slots:
        msg = "발송 시간이 하나 이상 필요합니다."
        raise ValueError(msg)
    today = sorted(datetime.combine(now.date(), slot, tzinfo=now.tzinfo) for slot in slots)
    late = [slot for slot in today if slot <= now <= slot + timedelta(minutes=LATE_START_GRACE_MINUTES)]
    if late:
        return late[-1]
    return next((slot for slot in today if slot > now), today[0] + timedelta(days=1))


async def wait_until(target: datetime, *, now: datetime | None = None) -> None:
    """Keep the prepared digest in this process; send immediately if already late."""
    remaining = (target - (now or datetime.now(tz=UTC))).total_seconds()
    if remaining > 0:
        await anyio.sleep(remaining)
