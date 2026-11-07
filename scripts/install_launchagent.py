"""Stage or install the collector in a logged-in macOS desktop session."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys


LABEL = "com.wechat-reader.collector"


def service_plist(args):
    runtime = args.runtime_dir.expanduser().resolve()
    label = LABEL + (".preflight" if args.preflight else "")
    command = [sys.executable, "-B", "-u", "-m", "wechat_reader", "--db",
               str(args.db.expanduser().resolve()), "collect"]
    if args.preflight:
        command.append("--once")
    else:
        command.extend(["--interval", str(args.interval)])
    if args.current_only:
        command.append("--current-only")
    if args.env_file:
        command.extend(["--env-file", str(args.env_file.expanduser().resolve())])
    log = runtime / ("preflight" if args.preflight else "collector")
    return dict(Label=label, ProgramArguments=command, WorkingDirectory=str(runtime),
                RunAtLoad=True, KeepAlive=not args.preflight,
                LimitLoadToSessionType="Aqua", ThrottleInterval=30, ExitTimeOut=15,
                EnvironmentVariables=dict(PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"),
                StandardOutPath=str(log.with_suffix(".out.log")),
                StandardErrorPath=str(log.with_suffix(".err.log")))


def main():
    parser = argparse.ArgumentParser(description="生成微信采集 LaunchAgent；--apply 才加载")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True, help="被 Git 忽略的日志与配置目录")
    parser.add_argument("--env-file", type=Path, help="仅传配置路径，不将凭据写入 plist")
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--current-only", action="store_true")
    parser.add_argument("--preflight", action="store_true", help="在桌面会话只采当前窗口一次，不安装登录自启")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be positive")
    if args.apply and sys.platform != "darwin":
        parser.error("--apply requires macOS")
    if args.env_file and not args.env_file.expanduser().is_file():
        parser.error("--env-file does not exist")

    runtime = args.runtime_dir.expanduser().resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    job = service_plist(args)
    staged = runtime / (job["Label"] + ".plist")
    staged.write_bytes(plistlib.dumps(job))
    print(f"Staged: {staged}", flush=True)
    if not args.apply:
        return

    domain = f"gui/{os.getuid()}"
    target = f"{domain}/{job['Label']}"
    loaded = subprocess.run(["launchctl", "print", target], capture_output=True).returncode == 0
    if loaded:
        raise RuntimeError(f"{target} is already loaded; bootout that job before replacing it")
    destination = staged
    if not args.preflight:
        destination = Path.home() / "Library/LaunchAgents" / staged.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            shutil.copy2(destination, runtime / f"{job['Label']}.{stamp}.bak")
        shutil.copyfile(staged, destination)
    subprocess.run(["launchctl", "enable", target], check=True)
    subprocess.run(["launchctl", "bootstrap", domain, str(destination)], check=True)
    print(f"Loaded: {target}", flush=True)


if __name__ == "__main__":
    main()
