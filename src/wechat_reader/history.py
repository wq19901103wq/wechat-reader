"""Shared history types. Source/account binding is supplied by the caller."""

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class SourceBinding:
    source_id: str
    account_id: str


@dataclass(frozen=True)
class HistoryChat:
    source: SourceBinding
    chat_id: str
    display_name: str
    chat_type: str
    last_active_at: float | None


@dataclass(frozen=True)
class MessageRef:
    source: SourceBinding
    chat_id: str
    message_id: str


@dataclass(frozen=True)
class SenderEvidence:
    source_sender_id: str
    display_name: str | None
    identity_basis: Literal["source_id", "display_name_placeholder", "unknown"]
    is_self: bool | None


@dataclass(frozen=True)
class MessageTime:
    # RPA's create_time may be a fallback or observation time.
    recorded_at: float
    first_observed_at: float | None
    sent_at: float | None = None


@dataclass(frozen=True)
class HistoryMessage:
    ref: MessageRef
    sender: SenderEvidence
    time: MessageTime
    content: str | None
    message_type: str
    image_description: str | None
    is_revoked: bool
    source_file: str | None
    source_content_hash: str


@dataclass(frozen=True)
class HistoryQuery:
    chat_ids: tuple[str, ...] = ()  # empty means all chats in this source
    start_recorded_at: float | None = None  # inclusive, epoch seconds
    end_recorded_at: float | None = None  # exclusive, epoch seconds
    include_revoked: bool = False
    limit: int = 100
    contains: str | None = None
    newest_first: bool = False


@dataclass(frozen=True)
class HistoryCursor:
    """Continue the same query by (recorded_at, row_id); not a change offset."""

    recorded_at: float
    row_id: int


@dataclass(frozen=True)
class HistoryPage:
    source: SourceBinding
    messages: tuple[HistoryMessage, ...]
    next_cursor: HistoryCursor | None
    retrieved_at: float
    coverage: Literal["unknown"] = "unknown"


class HistoryReader(Protocol):
    def list_chats(self, *, name: str | None = None, limit: int = 100) -> tuple[HistoryChat, ...]: ...

    def get_chat(self, chat_id: str) -> HistoryChat: ...

    def recent(self, chat_id: str, *, limit: int = 50) -> tuple[HistoryMessage, ...]: ...

    def query(
        self, query: HistoryQuery, *, cursor: HistoryCursor | None = None
    ) -> HistoryPage: ...
