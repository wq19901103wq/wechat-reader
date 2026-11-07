"""Independent JSON query and collection entry point."""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import sys

from .connection import add_history_options, history_from_args
from .history import HistoryCursor, HistoryQuery


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="微信原始消息：独立采集、保存与只读查询")
    add_history_options(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    chats = commands.add_parser("chats")
    chats.add_argument("--name")
    chats.add_argument("--limit", type=positive_int, default=100)
    recent = commands.add_parser("recent")
    recent.add_argument("--chat", required=True)
    recent.add_argument("--limit", type=positive_int, default=50)
    messages = commands.add_parser("messages")
    messages.add_argument("--chat", action="append", default=[])
    messages.add_argument("--contains")
    messages.add_argument("--start", type=float)
    messages.add_argument("--end", type=float)
    messages.add_argument("--newest-first", action="store_true")
    messages.add_argument("--include-revoked", action="store_true")
    messages.add_argument("--cursor", nargs=2, metavar=("RECORDED_AT", "ROW_ID"))
    messages.add_argument("--limit", type=positive_int, default=100)
    collect = commands.add_parser("collect", help="macOS 截图/OCR；不加载回复或记忆")
    collect.add_argument("--once", action="store_true", help="仅采集当前会话一次，不切换会话")
    collect.add_argument("--chat-name", action="append", default=[], help="仅保存这些名称的会话")
    collect.add_argument("--current-only", action="store_true", help="持续采集当前界面，不自动切未读会话")
    collect.add_argument("--save-screenshots", action="store_true")
    collect.add_argument("--env-file", type=Path,
                         help="从本机配置文件读取 DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL；已有环境变量优先")
    collect.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args(argv)
    if args.command == "collect":
        if args.history_db is None:
            parser.error("collect requires an explicit --db before the subcommand")
        if args.interval <= 0:
            parser.error("--interval must be positive")
        if sys.platform != "darwin":
            parser.error("UI capture requires macOS; queries also work on Linux")
        from .collector import WeChatCollector
        try:
            if args.env_file is not None:
                from dotenv import dotenv_values
                with args.env_file.expanduser().open(encoding="utf-8") as source:
                    values = dotenv_values(stream=source, interpolate=False)
                for key in ("DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"):
                    if values.get(key):
                        os.environ.setdefault(key, values[key])
            collector = WeChatCollector.from_default(
                args.history_db, chat_names=args.chat_name,
                switch_unread=not args.current_only, save_screenshots=args.save_screenshots)
            if args.once:
                emit(asdict(collector.collect_once()))
            else:
                collector.run(interval=args.interval, on_result=lambda r: emit(asdict(r)))
        except KeyboardInterrupt:
            return 130
        except (RuntimeError, OSError, ImportError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    try:
        history = history_from_args(args)
        if args.command == "chats":
            result = [asdict(c) for c in history.list_chats(name=args.name, limit=args.limit)]
        elif args.command == "recent":
            result = [asdict(m) for m in history.recent(args.chat, limit=args.limit)]
        else:
            cursor = HistoryCursor(float(args.cursor[0]), int(args.cursor[1])) if args.cursor else None
            result = asdict(history.query(HistoryQuery(
                chat_ids=tuple(args.chat), contains=args.contains,
                start_recorded_at=args.start, end_recorded_at=args.end,
                newest_first=args.newest_first, include_revoked=args.include_revoked,
                limit=args.limit), cursor=cursor))
        emit(result)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
