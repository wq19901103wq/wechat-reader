"""A single UI owner per macOS user, shared by collector and RPA ticks."""

import fcntl
from functools import wraps
import logging
import os
from pathlib import Path
import time


class CaptureBusy(RuntimeError):
    pass


class CaptureLease:
    def __init__(self, *, blocking=False):
        self.blocking = blocking

    def __enter__(self):
        # Fixed across database paths, virtual environments and launchd TMPDIR values.
        path = Path("/tmp") / f"wechat-reader-{os.getuid()}.capture.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self._file = os.fdopen(fd, "r+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB))
        except BlockingIOError as exc:
            self._file.close()
            raise CaptureBusy("WeChat UI is already owned by another collector or RPA tick") from exc
        return self

    def __exit__(self, *args):
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()


def exclusive_capture(func):
    """Wait for the current capture, then own UI through the entire Bot tick."""
    @wraps(func)
    def wrapped(*args, **kwargs):
        started = time.monotonic()
        with CaptureLease(blocking=True):
            waited = time.monotonic() - started
            if waited >= 1:
                logging.getLogger(__name__).info("[Perf][CaptureLease] waited=%.3fs", waited)
            return func(*args, **kwargs)
    return wrapped
