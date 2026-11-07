"""Capture visible messages without loading memory, reply generators or senders."""

from dataclasses import dataclass
import time

from .capture_lease import CaptureLease
from .utils.chat_utils import _normalize_chat_name


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class CollectionResult:
    chat_name: str
    new_messages: int
    saved: bool
    switched: bool = False


class WeChatCollector:
    def __init__(self, store, perception, *, chat_names=(), switch_unread=True,
                 save_screenshots=False, clicker_factory=None):
        self.store = store
        self.perception = perception
        self.chat_names = {_normalize_chat_name(name) for name in chat_names}
        self.switch_unread = switch_unread
        self.save_screenshots = save_screenshots
        self.clicker_factory = clicker_factory

    @classmethod
    def from_default(cls, db_path, **kwargs):
        from .layout.profile import PROFILE_WECHAT_MAC_1760X1280
        from .perception.smart_pipeline import SmartPerceptionPipeline
        from .store import RawMessageStore
        return cls(RawMessageStore(db_path),
                   SmartPerceptionPipeline(PROFILE_WECHAT_MAC_1760X1280), **kwargs)

    def _clicker(self, result):
        if result.window_rect is None:
            raise CaptureError("Missing window coordinates; cannot switch chats")
        factory = self.clicker_factory
        if factory is None:
            from .action.chat_list_clicker import ChatListClicker
            factory = ChatListClicker
        return factory(result.window_rect, result.scale_factor)

    def _tick(self, *, switch_unread):
        result = self.perception.perceive()
        if result is None:
            raise CaptureError("No WeChat screenshot; check login, window and screen recording permission")
        name = _normalize_chat_name(result.chat_name or "")
        if result.is_service_account_list or name in {"服务号", "订阅号", "公众号"}:
            if not switch_unread:
                raise CaptureError("Current window is a service-account list, not a chat")
            if not self._clicker(result).click_back_button():
                raise CaptureError("Could not return from the service-account list")
            return CollectionResult("", 0, False, True)
        if not name:
            raise CaptureError("Unidentified chat; refused to assign messages or click another chat")

        in_scope = not self.chat_names or name in self.chat_names
        new = []
        if in_scope:
            _, new = self.store.merge_tick(name, result.messages, result.is_group)
            self.store.save()
            # Even a non-strict legacy store cannot report a failed write as saved.
            if self.store._chat_repo is None or self.store._dirty:
                raise CaptureError("Raw history was not saved; stopped before switching chats")
            if self.save_screenshots and result.screenshot_path:
                self.store.save_screenshot(result.screenshot_path)

        switched = False
        if switch_unread:
            candidates = [item for item in result.chat_list_items
                          if item.unread_count and item.unread_count != "0"
                          and _normalize_chat_name(item.nickname) != name
                          and (not self.chat_names or _normalize_chat_name(item.nickname) in self.chat_names)]
            if candidates:
                switched = self._clicker(result).click_item(candidates[0])
                if not switched:
                    raise CaptureError("Could not switch to an unread chat")
        return CollectionResult(name, len(new), in_scope, switched)

    def collect_once(self):
        """Capture and persist the current chat without navigating away."""
        with CaptureLease():
            return self._tick(switch_unread=False)

    def run(self, *, interval=5.0, on_result=None, max_ticks=None):
        if interval <= 0 or (max_ticks is not None and max_ticks < 1):
            raise ValueError("interval and max_ticks must be positive")
        with CaptureLease():
            count = 0
            while True:
                started = time.monotonic()
                result = self._tick(switch_unread=self.switch_unread)
                if on_result:
                    on_result(result)
                count += 1
                if max_ticks is not None and count >= max_ticks:
                    return
                time.sleep(max(0, interval - (time.monotonic() - started)))
