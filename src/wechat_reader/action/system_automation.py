#!/usr/bin/env python3
"""L4 Action - 系统级 UI 自动化抽象

将 cliclick、osascript、AppleScript、screencapture 等 macOS 特定调用
封装为统一接口，使 Bot 层和 Action 层可以面向接口编程，便于 mock、测试和跨平台扩展。
"""

import logging
import subprocess  # nosec B404
from abc import ABC, abstractmethod

from wechat_reader.models.base import Rect

_logger = logging.getLogger("wechat_reader.system_automation")


class SystemAutomation(ABC):
    """系统级 UI 自动化抽象接口。"""

    @abstractmethod
    def activate_app(self, app_name: str) -> bool:
        """激活指定应用并等待其获得焦点。"""
        pass

    @abstractmethod
    def get_frontmost_app(self, app_name: str) -> tuple[bool, str]:
        """检查指定应用是否为当前 frontmost 应用。

        Returns:
            (is_frontmost, info_or_error)
        """
        pass

    @abstractmethod
    def get_window_rect(self, app_name: str) -> tuple[bool, Rect | None, str]:
        """获取指定应用主窗口的位置和大小。

        Returns:
            (success, rect_or_none, error_message)
        """
        pass

    @abstractmethod
    def click_at(self, x: int, y: int) -> bool:
        """在屏幕逻辑坐标 (x, y) 处点击一次。"""
        pass


    @abstractmethod
    def run_applescript(self, script: str, timeout: int = 5) -> tuple[int, str, str]:
        """执行 AppleScript。

        Returns:
            (returncode, stdout, stderr)
        """
        pass



    @abstractmethod
    def capture_screen(
        self,
        rect: Rect,
        output_path: str,
        window_id: int | None = None,
    ) -> tuple[bool, str]:
        """截取指定屏幕区域或窗口并保存到文件。

        Args:
            rect: 截图区域（window_id 为空时使用）
            output_path: 输出文件路径
            window_id: 可选的窗口 ID，优先使用 screencapture -l

        Returns:
            (success, error_message)
        """
        pass


class MacOSSystemAutomation(SystemAutomation):
    """macOS 实现：基于 AppleScript + cliclick + screencapture。"""

    def __init__(self, cliclick_path: str = "/opt/homebrew/bin/cliclick"):
        self.cliclick_path = cliclick_path

    def activate_app(self, app_name: str) -> bool:
        script = f'tell application "{app_name}" to activate'
        try:
            rc, _, stderr = self.run_applescript(script, timeout=3)
            if rc != 0:
                _logger.warning("activate_app(%s) 失败: %s", app_name, stderr)
            return rc == 0
        except (subprocess.SubprocessError, OSError) as e:
            _logger.warning("activate_app(%s) 异常: %s", app_name, e)
            return False

    def get_frontmost_app(self, app_name: str) -> tuple[bool, str]:
        script = f'''
            tell application "System Events"
                tell process "{app_name}"
                    set frontmost to true
                    delay 0.3
                end tell
                set frontApp to name of first application process whose frontmost is true
                return frontApp
            end tell
        '''
        try:
            rc, stdout, stderr = self.run_applescript(script, timeout=5)
            if rc != 0:
                return False, stderr
            front_app = stdout.strip()
            return front_app == app_name, front_app
        except Exception as e:
            return False, str(e)

    def get_window_rect(self, app_name: str) -> tuple[bool, Rect | None, str]:
        """通过 AppleScript 获取应用主窗口的位置和大小。"""
        script = f'''
            tell application "System Events"
                tell process "{app_name}"
                    tell window 1
                        set winPos to position
                        set winSize to size
                        return ((item 1 of winPos) as text) & "," & ((item 2 of winPos) as text) & "," & ((item 1 of winSize) as text) & "," & ((item 2 of winSize) as text)
                    end tell
                end tell
            end tell
        '''
        try:
            rc, stdout, stderr = self.run_applescript(script, timeout=5)
            if rc != 0:
                return False, None, stderr
            parts = stdout.strip().split(",")
            if len(parts) != 4:
                return False, None, f"无法解析窗口坐标: {stdout!r}"
            x, y, w, h = map(int, map(float, parts))
            return True, Rect(x=x, y=y, width=w, height=h), ""
        except Exception as e:
            return False, None, str(e)

    def click_at(self, x: int, y: int) -> bool:
        try:
            subprocess.run(  # nosec
                [self.cliclick_path, f"c:{x},{y}"],
                check=True,
                timeout=5,
            )
            return True
        except (subprocess.SubprocessError, OSError) as e:
            _logger.warning("click_at(%d,%d) 失败: %s", x, y, e)
            return False


    def run_applescript(self, script: str, timeout: int = 5) -> tuple[int, str, str]:
        try:
            r = subprocess.run(  # nosec
                ["osascript", "-e", script],
                timeout=timeout,
                capture_output=True,
            )
            return (
                r.returncode,
                r.stdout.decode("utf-8", errors="replace"),
                r.stderr.decode("utf-8", errors="replace"),
            )
        except Exception as e:
            return -1, "", str(e)



    def capture_screen(
        self,
        rect: Rect,
        output_path: str,
        window_id: int | None = None,
    ) -> tuple[bool, str]:
        """使用 screencapture 截取指定区域或窗口。

        对输出路径做基本校验，防止路径注入。
        """
        _SHELL_META = "&;|`$()"
        if not output_path or "/" not in output_path or any(c in output_path for c in _SHELL_META):
            return False, f"非法截图输出路径: {output_path}"
        if window_id:
            cmd = [
                "screencapture",
                "-l", str(window_id),
                "-o",  # 排除窗口阴影
                "-x", output_path,
            ]
        else:
            cmd = [
                "screencapture",
                "-R", f"{rect.x},{rect.y},{rect.width},{rect.height}",
                "-x", output_path,
            ]
        try:
            subprocess.run(cmd, check=True, timeout=5)  # nosec
            return True, ""
        except Exception as e:
            return False, str(e)


class NoOpSystemAutomation(SystemAutomation):
    """空实现，用于测试或禁用 UI 交互的场景。"""

    def __init__(self, window_rect: Rect | None = None):
        self.window_rect = window_rect or Rect(x=0, y=0, width=1200, height=800)

    def activate_app(self, app_name: str) -> bool:
        return True

    def get_frontmost_app(self, app_name: str) -> tuple[bool, str]:
        return True, app_name

    def get_window_rect(self, app_name: str) -> tuple[bool, Rect | None, str]:
        return True, self.window_rect, ""

    def click_at(self, x: int, y: int) -> bool:
        return True


    def run_applescript(self, script: str, timeout: int = 5) -> tuple[int, str, str]:
        return 0, "", ""



    def capture_screen(
        self,
        rect: Rect,
        output_path: str,
        window_id: int | None = None,
    ) -> tuple[bool, str]:
        return True, ""
