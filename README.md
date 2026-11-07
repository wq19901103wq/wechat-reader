# wechat-reader

共用微信原始消息组件，可单独构建、安装和使用，不依赖个人助理、DH、MAC 或 RPA Bot。代码从 `wechat-mac-rpa` 的采集与原始库模块抽出，沿用其 MIT 许可，见 [LICENSE](LICENSE)。主项目的其他代码不因此改变许可。

包含截图、Vision／可选视觉模型 OCR、布局解析、可见未读会话切换、消息规范化与去重、原始 SQLite 保存／恢复，以及只读历史查询。聊天理解、人物记忆、自动回复、发送消息和 push 均由消费者负责。

## 安装与只读查询

在本目录运行，Python 3.10+：

```sh
python -m pip install -e .
wechat-reader --db /path/to/chat_history.db --account my-wechat chats --limit 20
wechat-reader --db /path/to/chat_history.db recent --chat CHAT_ID --limit 50
wechat-reader --db /path/to/chat_history.db messages --contains '方案' --limit 20
```

也可运行 `python -m wechat_reader`。查询仅用标准库，以 SQLite `mode=ro` 打开兼容原始库，不创建不存在的来源，不改表和原文。查询默认沿用 `WECHAT_HISTORY_DB`，其次 `~/wechat-mac-rpa/data/db/chat_history.db`；采集必须显式传 `--db`。

```python
from wechat_reader import HistoryQuery, open_wechat_history

history = open_wechat_history("/path/to/chat_history.db", account_id="my-wechat")
page = history.query(HistoryQuery(limit=100))
next_page = history.query(HistoryQuery(limit=100), cursor=page.next_cursor) if page.next_cursor else None
```

分页游标是 `(recorded_at, row_id)`，不是修改日志或增量变更 offset。来源标识默认数据库文件 URI，可用 `source_id`／`--source` 指定。每份库对应一个微信账号，账号绑定由调用方提供，未配置为 `unspecified`；组件不自行猜测账号或真实身份。OCR 昵称占位与原始发送者 ID 会区分，观测时间不会当成已确认的发送时间。

## 独立采集

macOS 上在本目录安装额外依赖；本机需有已登录、可见的微信窗口、屏幕录制与辅助功能权限，以及 `/opt/homebrew/bin/cliclick`：

```sh
python -m pip install -e '.[capture]'
wechat-reader --db ./data/chat_history.db collect --once
wechat-reader --db ./data/chat_history.db collect --interval 5
wechat-reader --db ./data/chat_history.db collect --chat-name '示例会话'
wechat-reader --db ./data/chat_history.db collect --env-file /path/to/private.env
```

`--once` 只保存当前会话，不切换；持续采集默认会切换左侧可见列表中的未读会话，`--current-only` 关闭切换。`--chat-name` 可多次指定，仅保存和切入这些会话。它不遍历全部历史、不滚动补录，也不保证捕获屏幕之外或运行前的全部消息；打开会话会改变微信的已读状态。标题不明、窗口未就绪或保存失败时停止并返回错误，不执行登录恢复或自动发送。

沿用原有 OCR 流程与阈值：本地 Vision 负责布局，配置 `DASHSCOPE_API_KEY` 后将变化的截图送往既有视觉模型识别标题与消息，静态画面复用缓存。初次识别依赖视觉模型；缺少配置或识别失败时可能无法确认标题，采集会停止。可用 `--env-file` 读取本机已有配置，只加载 `DASHSCOPE_API_KEY` 与 `DASHSCOPE_BASE_URL`，已有环境变量优先。这里的视觉模型只识别截图，不生成业务记忆。没有更改 OCR 提示词。

## macOS 日常运行

通过用户 LaunchAgent 在已登录的桌面会话运行，系统 LaunchDaemon／无桌面会话的 SSH 进程不能替代它。先用临时库实采一次，再备份现有原始库、安装日常任务；不要同时运行旧采集 Bot。使用已安装本包及 capture 依赖的解释器执行安装脚本：

```sh
python scripts/install_launchagent.py --db /path/to/ignored/preflight.db \
  --runtime-dir /path/to/ignored/service --env-file /path/to/private.env --preflight --apply
launchctl print gui/$(id -u)/com.wechat-reader.collector.preflight
launchctl bootout gui/$(id -u)/com.wechat-reader.collector.preflight

python scripts/install_launchagent.py --db /path/to/chat_history.db \
  --runtime-dir /path/to/ignored/service --env-file /path/to/private.env --apply
launchctl print gui/$(id -u)/com.wechat-reader.collector
```

省略 `--apply` 仅生成可检查的 plist；其中只保存配置文件路径，不含密钥。正式任务安装到用户 `~/Library/LaunchAgents/`，登录后自启、退出后按 30 秒节流恢复，日志在 runtime 目录。锁屏／注销、微信退出或未登录会中断采集；需要桌面可用、屏幕录制与辅助功能权限。停止当前任务用 `launchctl bootout gui/$(id -u)/com.wechat-reader.collector`；取消后续登录自启还需移走该用户的 `com.wechat-reader.collector.plist`。安装器不会停止其他任务、启动自动回复或更改助理与 push 配置。

默认不额外留存截图；`--save-screenshots` 保存到数据库旁的 `screenshots/`，沿用一天保留策略。截图含整个窗口，采集范围筛选只限制消息记录。数据库、截图、日志、凭据和环境文件由宿主放进被 Git 忽略的数据目录，包内不携带这些数据。

直接保存已识别的消息只需 `pip install -e '.[store]'`，使用 `wechat_reader.store.RawMessageStore(db_path)`。`merge_tick()` 返回会话状态和本轮新消息；`save()` 默认严格确认写入，失败保留待保存状态并抛错。

## 与消费者共用

- 个人助理：`inputs/wechat.py` 将只读历史转成 `RawRecord`，理解仍由 `memory/` 完成。
- RPA：旧 `src.capture`、`src.perception`、`src.db` 等入口转到本包；`GlobalStore` 继承原始存储，在 RPA 内维护未回复选择、回复标记和待确认发送队列。
- 兼容现有 SQLite 表、消息标识与回复列，不要求清库或重建。共享消息模型保留旧回复字段用于互操作，采集器不读取这些字段作决策，也不写入回复状态。

独立采集循环与新版 RPA 的完整 tick 共用同一用户的 UI 文件锁，跨数据库也互斥。一次只运行一个采集所有者；个人助理可以同时只读查询。旧的已启动 Bot 尚未加载这把锁，切换前先停止旧采集，再使用安装了本包的新版消费者；本次拆分不自动切换服务。文件锁只保护已接入的入口，不控制外部手动操作或其他自动化工具。

RPA 原有发送和剪贴板能力仍留在 RPA；共享包只含采集所需的截图与点击。安装查询包不会加载 SQLAlchemy、PyObjC 或视觉模型客户端。

## 仓库与版本

本仓库是微信原始采集、保存和读取的唯一源码归属；个人助理 `personal-context` 和 `wechat-mac-rpa` 通过 Python 依赖消费同一固定提交。聊天理解归个人助理记忆层，回复生成归 `digital-human`，发送与回复状态归 RPA；不使用整个 RPA 的 submodule，也不向消费者复制本包源码。

组件尚未发布到 PyPI。私有 GitHub 仓库需要读取权限，先用 `gh auth login` 和 `gh auth setup-git` 配置 HTTPS 访问；消费者依赖中的提交号必须同步更新。查询安装不带 extras，采集消费者使用 `[capture]`。本地开发可在本仓库执行 `python -m pip install -e '.[capture]'`；已安装的 wheel 不依赖源码目录位置，整理仓库不需要重启采集服务。

RPA 的 GitHub Actions 使用仅能读取本库的 `WECHAT_READER_TOKEN` 仓库 secret；私有依赖对无权访问的用户和外部 fork 不可用。不要把 token、数据库或登录态放入源码、依赖 URL 或提交历史。MIT 许可与原贡献者署名保留在 [LICENSE](LICENSE)。
