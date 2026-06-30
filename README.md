# 个人用插件

AstrBot 私人实用插件，包含分群关键词语音、土味情话、群友史聊天记录构造、戳一戳响应、关键词表情回应、`/lishi` 调试检查命令、历史消息读取与 LLM 输出后处理等功能。

## 分群关键词语音

在 AstrBot 插件配置页面的 `group_keyword_voices` 中添加群聊规则。

每条规则包含：

- `group_id`：生效的 QQ 群号。
- `enabled`：本群独立开关，关闭后保留配置但不检测。
- `keywords`：触发关键词列表，消息包含任一关键词时触发。
- `audio_directory`：存放语音文件的单个本地目录路径。

该功能没有全局配置。未加入配置列表的群聊、私聊、关闭开关的群聊均不会触发。

同一个群号可以添加多条规则，每条规则使用不同的关键词和语音目录。插件按配置顺序检查该群的全部规则；一条消息同时命中多条规则时，只发送第一条有效规则的语音。

配置 Aizo 语音时，将触发词填写到 `keywords`，并在 `audio_directory` 填写存放语音文件的目录。英文关键词匹配不区分大小写。

目录只需配置一个。插件不会扫描子目录，会按文件名排序并发送目录中的第一个 `mp3`、`wav`、`amr`、`silk`、`ogg` 或 `m4a` 文件。目录不存在或没有有效语音文件时不会发送，日志会记录目录路径。

AstrBot 当前配置界面没有目录选择器，因此 `audio_directory` 使用文本路径。请填写 AstrBot 运行环境能够访问的本地绝对路径。

从 v1.3.0 升级时，需要将原来的 `audio_path` 改为 `audio_directory`。

## 土味情话

- `/土味情话`：向命令发送者发送随机情话。
- `/土味情话 <QQ号>`：向指定 QQ 发送随机情话。
- `/土味情话 @群友`：向最后一个有效的非机器人 `@` 目标发送随机情话。

情话从内置的 `core/love_messages.txt` 随机选择，并按词库原文发送，不再自动补充“喵”语气。该功能不需要分群配置。

词库路径通过插件 `main.py` 的绝对位置解析，不依赖 AstrBot 的启动工作目录。

## 音乐搜索与点歌

- `/点歌 歌名`：通过网易云音乐 API 搜索歌曲，并返回候选列表。
- `/music 歌名`、`/听歌 歌名`、`/网易云 歌名`：`/点歌` 的别名。
- `/网易云登录`、`/音乐登录`、`/点歌登录`：直接发送网易云音乐扫码登录二维码，扫码确认后自动持久化保存 Cookie。
- 搜索后回复列表编号：发送歌曲信息、封面和语音播放消息。

音乐搜索需要先在插件配置页填写 `music_search.api_base_url`。该配置不提供公开默认服务地址；如果只填写 `host:port`，插件会自动补全为 `http://host:port`。

可通过 `music_search.enable_music_search_feature` 开启或关闭该功能；关闭后 `/点歌` 会提示功能已关闭。`quality` 控制优先音质，音频链接不可用时会依次尝试 `exhigh`、`higher`、`standard`。

需要使用 VIP 账号访问会员音乐时，发送 `/网易云登录` 并用网易云音乐 App 扫码确认。登录成功后插件会把接口返回的 Cookie 持久化保存到 AstrBot 插件数据目录 `data/plugin_data/astrbot_plugin_util/netease_login/cookie.json`，重启后会自动读取，后续点歌会自动携带该登录态。`music_search.cookie` 仍可手动填写作为备用配置。Cookie 属于账号凭据，请只在可信环境中使用登录指令。

## 账号下线邮件通知

插件会检测 AIOCQHTTP 上报的 `bot_offline` 下线通知，例如“你的账号当前登录已失效，请重新登录。”。命中后可通过 QQ 邮箱 SMTP 自动发送告警邮件。

在插件配置页的 `offline_email_alert` 中配置：

- `enable_offline_email_alert`：是否启用账号下线邮件通知，默认关闭。
- `sender`：QQ 邮箱发件人地址。
- `QQ_password`：QQ 邮箱 SMTP 授权码，不是 QQ 登录密码。
- `receiver`：告警邮件收件人地址。

当前只负责检测和发邮件。若 AstrBot 会话白名单在插件处理前拦截该 notice，需要后续把对应下线通知会话放入白名单。

## 下线邮件检测端

`offline_mail_monitors` 可以配置多个邮箱检测端。每个检测端会周期性通过 IMAP 获取指定邮箱的新邮件；如果新邮件主题或正文命中下线告警关键词，就使用指定机器人向指定会话主动发送提醒。

每条配置包含：

- `name`：检测端名称，用于日志和持久化状态。
- `enabled`：本检测端独立开关。
- `platform_id`：负责发送提醒的机器人平台 ID，例如 `li`、`ni`。
- `message_type`：目标会话类型，群聊填 `GroupMessage`，私聊填 `FriendMessage`。
- `session_id`：目标会话 ID，群聊填群号，私聊填 QQ 号。
- `imap_host` / `imap_port`：检测邮箱的 IMAP SSL 服务地址和端口，QQ 邮箱通常是 `imap.qq.com` / `993`。
- `username` / `password`：检测邮箱账号和邮箱授权码。
- `folder`：检测邮箱文件夹，通常为 `INBOX`。
- `interval_seconds`：检测间隔秒数。
- `subject_keywords` / `body_keywords`：识别下线告警邮件的主题和正文关键词。
- `max_fetch_count`：单次最多检查的新邮件数量。
- `message_template`：主动提醒消息模板。
- `at_targets`：主动提醒前追加的 @ 目标列表，填写 QQ 号可 @ 指定用户，填写 `all` 可 @ 全体成员。

`message_template` 支持以下变量：

- `{monitor}`：检测端名称。
- `{mailbox}`：检测邮箱账号。
- `{uid}`：邮件 UID。
- `{subject}`：邮件主题。
- `{from_addr}`：邮件发件人。
- `{date}`：邮件日期。
- `{body_preview}`：邮件正文预览。
- `{platform_id}`、`{message_type}`、`{session_id}`、`{session}`：目标会话信息。

插件会把每个检测端已处理的最新 UID 保存到 AstrBot 插件数据目录 `data/plugin_data/astrbot_plugin_util/offline_mail_monitor_state.json`。首次启动某条检测端配置时只记录当前邮箱最新 UID，不会推送历史邮件；之后只处理新邮件。

可用测试脚本发送能触发检测端的下线邮件：

```powershell
cd E:\pythonDma\git\AstrBot\data\plugins\astrbot_plugin_util
uv run python scripts\send_test_email.py --offline-alert
```

脚本默认读取 `cs\QQ_mailbox\text.yaml` 中的 `sender`、`QQ_password` 和 `receiver`。

检测端运行时会在日志中输出脱敏后的 IMAP 配置摘要、初始化 UID、每轮轮询的 `last_uid` / 新邮件数 / 命中告警数 / 状态更新信息。邮箱授权码不会写入日志。

## 群友史

- `/群友史 QQ号 消息内容 | QQ号 消息内容 | ...`：按输入构造合并转发聊天记录。
- `/群友史帮助`：查看格式说明。

每个消息段之间使用 `|` 分隔，每个消息段必须是 `QQ号 消息内容`。如果在某个消息段中附带图片，图片会被放入对应 QQ 的合并转发节点中。

节点昵称通过当前 AIOCQHTTP 适配器的 `get_stranger_info` 获取，不再访问第三方昵称接口。

可在插件配置页的 `group_history.enable_group_history_feature` 中开启或关闭该功能，默认开启。关闭后 `/群友史` 会提示功能已关闭，不再生成合并转发聊天记录。

## 变更说明

- 关键词命中后从配置的本地语音目录发送语音。
- 新增 NullDox 风格的 `/土味情话 [QQ号|@用户]` 指令。
- 新增 `/点歌` 音乐搜索与点歌功能。
- 新增 `/网易云登录` 扫码登录功能，可自动持久化保存网易云 Cookie。
- 新增 AIOCQHTTP 账号下线邮件通知功能。
- 新增邮箱下线检测端，可通过 IMAP 检测下线告警邮件并主动发送提醒。
- 新增 `群友史` 构造聊天记录功能，输出为合并转发节点。
- 已移除语音生成命令。
- 已移除骰子指令处理。

## 开发计划

功能状态、依赖条件和验收标准见 [TODO.md](TODO.md)。

随机群友土味情话功能的实现约定见 [LOVE_MESSAGE_DESIGN.md](LOVE_MESSAGE_DESIGN.md)。

网易云音乐 API 服务失效时的服务器排查与手动重启步骤见 [docs/网易云音乐服务重启.md](docs/网易云音乐服务重启.md)。
