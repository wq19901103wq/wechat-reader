"""Raw WeChat history. Capture and write dependencies load only when requested."""

from .connection import open_wechat_history
from .history import (
    HistoryChat, HistoryCursor, HistoryMessage, HistoryPage, HistoryQuery,
    HistoryReader, MessageRef, MessageTime, SenderEvidence, SourceBinding,
)
from .sqlite_history import WeChatSQLiteHistory

__all__ = [
    "open_wechat_history", "WeChatSQLiteHistory", "HistoryChat", "HistoryCursor",
    "HistoryMessage", "HistoryPage", "HistoryQuery", "HistoryReader", "MessageRef",
    "MessageTime", "SenderEvidence", "SourceBinding",
]
