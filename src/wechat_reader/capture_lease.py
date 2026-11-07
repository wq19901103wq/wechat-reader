"""A single UI owner per macOS user, shared by collector and RPA ticks."""

import fcntl
from functools import wraps
import logging
import os
from pathlib import Path


class CaptureBusy(RuntimeError):
    pass


class CaptureLease:
    def __enter__(self):
        # Fixed across database paths, virtual environments and launchd TMPDIR values.
        path = Path("/tmp") / f"wechat-reader-{os.getuid()}.capture.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self._file = os.fdopen(fd, "r+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._file.close()
            raise CaptureBusy("WeChat UI is already owned by another collector or RPA tick") from exc
        return self

    def __exit__(self, *args):
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()


def exclusive_capture(func):
    """Skip a Bot tick before it touches UI if a collector owns the window."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        lease = CaptureLease()
        try:
            lease.__enter__()
        except CaptureBusy:
            logging.getLogger(__name__).warning("WeChat UI busy; skipped RPA tick")
            return None
        try:
            return func(*args, **kwargs)
        finally:
            lease.__exit__(None, None, None)
    return wrapped
