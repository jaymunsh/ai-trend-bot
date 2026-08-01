from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, computed_field


class SourceKind(StrEnum):
    FEED = "feed"
    THREADS_ACCOUNT = "threads_account"
    THREADS_KEYWORD = "threads_keyword"


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
        return sha256(str(self.url).encode()).hexdigest()


class DigestItem(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_url: HttpUrl
    source_label: str = Field(min_length=1)
