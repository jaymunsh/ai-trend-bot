from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field


class SourceKind(StrEnum):
    FEED = "feed"
    THREADS_ACCOUNT = "threads_account"
    THREADS_KEYWORD = "threads_keyword"


def item_key(url: HttpUrl) -> str:
    """Stable identity for an item, shared by its raw and digested forms."""
    return sha256(str(url).encode()).hexdigest()


class RawItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    source_kind: SourceKind
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    url: HttpUrl
    published_at: datetime
    priority: int = Field(ge=1, le=100)
    external_id: str | None = None

    @computed_field
    @property
    def key(self) -> str:
        return item_key(self.url)


class DigestItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_url: HttpUrl
    source_label: str = Field(min_length=1)
    category: str = ""
    # One-line description of the underlying event, recorded so later runs can
    # recognise follow-up coverage that has a different URL.
    event: str = ""
    # (label, url) for other outlets that covered the same event.
    also: tuple[tuple[str, str], ...] = ()

    @computed_field
    @property
    def key(self) -> str:
        return item_key(self.source_url)
