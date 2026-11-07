"""Local source selection shared by scripts and Python consumers."""

import os
from pathlib import Path

from .history import SourceBinding
from .sqlite_history import WeChatSQLiteHistory


def open_wechat_history(
    db_path: str | Path | None = None, *, account_id: str = "unspecified",
    source_id: str | None = None,
) -> WeChatSQLiteHistory:
    path = Path(db_path or os.environ.get("WECHAT_HISTORY_DB") or
                Path.home() / "wechat-mac-rpa/data/db/chat_history.db").expanduser().resolve()
    return WeChatSQLiteHistory(path, source=SourceBinding(source_id or path.as_uri(), account_id))


def add_history_options(parser):
    parser.add_argument("--history-db", "--db", dest="history_db", type=Path,
                        help="RPA SQLite；默认 WECHAT_HISTORY_DB 或 ~/wechat-mac-rpa/data/db/chat_history.db")
    parser.add_argument("--history-account", "--account", dest="history_account", default="unspecified",
                        help="这份数据库的账号标识；未配置时保留 unspecified")
    parser.add_argument("--history-source", "--source", dest="history_source",
                        help="来源标识；默认数据库文件 URI")


def history_from_args(args):
    return open_wechat_history(args.history_db, account_id=args.history_account,
                               source_id=args.history_source)
