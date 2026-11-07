"""Thin read-only adapter for wechat-mac-rpa's existing SQLite history."""

from contextlib import closing
from pathlib import Path
import sqlite3
import time

from .history import (
    HistoryChat, HistoryCursor, HistoryMessage, HistoryPage, HistoryQuery, MessageRef,
    MessageTime, SenderEvidence, SourceBinding,
)


class WeChatSQLiteHistory:
    def __init__(self, db_path: str | Path, *, source: SourceBinding):
        self._db_path = Path(db_path).expanduser().resolve()
        self._source = source

    def list_chats(self, *, name: str | None = None, limit: int = 100) -> tuple[HistoryChat, ...]:
        with closing(sqlite3.connect(self._db_path.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM chatrooms WHERE (? IS NULL OR instr(display_name, ?) > 0) "
                "ORDER BY last_active_at DESC, id DESC LIMIT ?", (name, name, limit),
            ).fetchall()
        return tuple(self._chat(row) for row in rows)

    def get_chat(self, chat_id: str) -> HistoryChat:
        with closing(sqlite3.connect(self._db_path.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM chatrooms WHERE chatroom_id = ?", (chat_id,)).fetchone()
        if row is None:
            raise KeyError(chat_id)
        return self._chat(row)

    def recent(self, chat_id: str, *, limit: int = 50) -> tuple[HistoryMessage, ...]:
        page = self.query(HistoryQuery(chat_ids=(chat_id,), limit=limit, newest_first=True))
        return tuple(reversed(page.messages))

    def query(
        self, query: HistoryQuery, *, cursor: HistoryCursor | None = None
    ) -> HistoryPage:
        predicates = ["1 = 1"]
        params: list[object] = []
        if query.chat_ids:
            predicates.append("c.chatroom_id IN (" + ",".join("?" for _ in query.chat_ids) + ")")
            params.extend(query.chat_ids)
        if query.contains is not None:
            predicates.append("instr(COALESCE(m.content, '') || '\n' || "
                              "COALESCE(m.image_description, ''), ?) > 0")
            params.append(query.contains)
        if query.start_recorded_at is not None:
            predicates.append("m.create_time >= ?")
            params.append(query.start_recorded_at)
        if query.end_recorded_at is not None:
            predicates.append("m.create_time < ?")
            params.append(query.end_recorded_at)
        if not query.include_revoked:
            predicates.append("m.is_revoked IS NOT 1")
        if cursor is not None:
            comparison = "<" if query.newest_first else ">"
            predicates.append(f"(m.create_time, m.id) {comparison} (?, ?)")
            params.extend((cursor.recorded_at, cursor.row_id))
        params.append(query.limit + 1)

        order = "DESC" if query.newest_first else "ASC"
        sql = """
            SELECT m.id, m.wxid, m.sender_display_name, m.is_self, m.content,
                   m.message_type, m.image_description, m.is_revoked,
                   m.create_time, m.observed_at, m.source_file, m.content_hash,
                   c.chatroom_id AS source_chat_id
            FROM messages AS m JOIN chatrooms AS c ON c.id = m.chatroom_id
            WHERE """ + " AND ".join(predicates) + """
            ORDER BY m.create_time """ + order + ", m.id " + order + " LIMIT ?"
        with closing(sqlite3.connect(self._db_path.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(sql, params).fetchall()

        selected = rows[:query.limit]
        next_cursor = None
        if len(rows) > query.limit:
            last = selected[-1]
            next_cursor = HistoryCursor(last["create_time"], last["id"])
        return HistoryPage(
            self._source, tuple(self._message(row) for row in selected),
            next_cursor, time.time(),
        )

    def _chat(self, row: sqlite3.Row) -> HistoryChat:
        return HistoryChat(self._source, row["chatroom_id"], row["display_name"],
                           row["chat_type"], row["last_active_at"])

    def _message(self, row: sqlite3.Row) -> HistoryMessage:
        sender_id = row["wxid"] or ""
        identity_basis = (
            "display_name_placeholder" if sender_id.startswith("_sender_")
            else "source_id" if sender_id else "unknown"
        )
        return HistoryMessage(
            ref=MessageRef(self._source, row["source_chat_id"], str(row["id"])),
            sender=SenderEvidence(
                sender_id, row["sender_display_name"], identity_basis,
                None if row["is_self"] is None else bool(row["is_self"]),
            ),
            time=MessageTime(row["create_time"], row["observed_at"]),
            content=row["content"],
            message_type=row["message_type"],
            image_description=row["image_description"],
            is_revoked=bool(row["is_revoked"]),
            source_file=row["source_file"],
            source_content_hash=row["content_hash"],
        )
