# 个人用插件

AstrBot 私人实用插件，包含分群关键词语音、土味情话、群友史聊天记录构造、角色资料库搜索、戳一戳响应、关键词表情回应、`/lishi` 调试检查命令、历史消息读取与 LLM 输出后处理等功能。

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

## AI 主动语音发送工具

插件可向大模型暴露 `send_voice_to_user` 工具，让 AI 在需要时把短文本合成为语音并发送到当前会话。该工具参考 `li_qwen3_tts_api` 的 `POST /generate` 接口实现：配置里的 `audio_id` 会作为 `reference_id` 传给 TTS 服务，生成结果会下载到 AstrBot 插件数据目录后再作为本地语音发送。

在插件配置页的 `ai_voice` 中配置：

- `enable_ai_voice_tool`：是否启用该工具，默认关闭。
- `api_base_url`：TTS API 服务地址，例如 `http://127.0.0.1:8000`。
- `audio_id`：音频/参考音色 ID，对应参考项目返回的 `reference_id`。
- `token`：TTS API 鉴权 token，请直接填写 token 内容，不需要 `Bearer` 前缀；日志只显示是否已配置，不输出 token 本体。
- `language`：默认语言提示，可留空，也可填写服务端支持的 `Chinese`、`Japanese`、`zh`、`ja` 等。
- `max_text_chars`：单次语音合成文本长度上限，建议保持较短，避免语音过长。

启用且配置完整后，模型会看到 `send_voice_to_user(text, language)` 工具。工具成功发送语音后会提醒模型本轮不要再用普通文本重复同一段内容。

## 账号下线邮件通知

插件会检测 AIOCQHTTP 上报的 `bot_offline` 下线通知，例如“你的账号当前登录已失效，请重新登录。”。命中后可通过 QQ 邮箱 SMTP 自动发送告警邮件。

在插件配置页的 `offline_email_alert` 中配置：

- `enable_offline_email_alert`：是否启用账号下线邮件通知，默认关闭。
- `sender`：QQ 邮箱发件人地址。
- `QQ_password`：QQ 邮箱 SMTP 授权码，不是 QQ 登录密码。
- `receiver`：告警邮件收件人地址。

当前只负责检测和发邮件。若 AstrBot 会话白名单在插件处理前拦截该 notice，需要后续把对应下线通知会话放入白名单。

## 下线 Webhook 发送端与接收端

插件内置下线 Webhook 发送端和接收端，二者可以独立开关。发送端在检测到 AIOCQHTTP `bot_offline` notice 后推送签名 JSON；接收端收到合法签名后，按接收规则向指定机器人会话主动发送提醒。

发送端配置 `offline_webhook_senders`，支持多条目标：

- `enabled`：启用本发送目标。
- `webhook_url`：接收端地址，例如 `http://127.0.0.1:8765/astrbot-util/offline`。
- `secret`：共享密钥，发送端和接收规则必须一致。
- `timeout_seconds` / `retry_count`：请求超时和失败重试次数。

接收端服务配置 `offline_webhook_receiver`：

- `enable_offline_webhook_receiver`：启用 HTTP 接收服务。
- `listen_host` / `listen_port`：监听地址和端口。
- `path`：接收路径，默认 `/astrbot-util/offline`。

接收规则配置 `offline_webhook_receive_rules`，支持多条规则：

- `secret`：用于校验发送端 HMAC-SHA256 签名。
- `platform_id` / `message_type` / `session_id`：主动发送提醒的目标会话。
- `message_template`：提醒消息模板。
- `at_targets`：可填写 QQ 号或 `all`，在提醒前追加 @。

模板变量：`{event}`、`{self_id}`、`{user_id}`、`{platform}`、`{message}`、`{notice_type}`、`{post_type}`、`{source_time}`、`{timestamp}`、`{rule}`、`{session}`。

## 角色资料库搜索工具

插件会把 `cs/output` 中的角色扮演资料构建为 SQLite 本地资料库，并提供给大模型工具 `search_roleplay_knowledge` 搜索使用。

数据位置：

- 源资料：插件目录下的 `cs/output`。
- SQLite 数据库：插件目录下的 `roleplay_knowledge/roleplay_knowledge.sqlite3`，该文件纳入 git 管理。

插件启动时会从 `cs/output` 按插件内相对路径重建数据库，方便你直接修改 markdown 源资料后重启生效。

在插件配置页的 `roleplay_knowledge` 中配置：

- `enable_roleplay_knowledge_tool`：是否向大模型注入角色资料库搜索工具，默认关闭。
- `max_results`：每次搜索最多返回的资料条数。
- `max_chars_per_result`：每条资料最多返回的字符数，避免一次塞入过长资料。
- `deduplicate_turns`：最近多少轮对话内不重复返回同一份资料文档，默认 `5`，填 `0` 可关闭去重。

开启 `enable_roleplay_knowledge_tool` 后，工具会保留在人设工具集中并注入本轮大模型请求；关闭时会在请求发送前移除。

插件启动时会在日志中打印角色资料库路径、SQLite 文件是否存在、文件大小、源资料目录是否存在、源 Markdown 数量和 `ema` / `hiro` 文档数量；每次工具搜索会打印 query、拆分关键词、候选数量、去重数量、评分数量、返回数量和返回文档来源，方便排查数据库未加载或检索条件异常。若运行环境缺少 `cs/output` 源资料，插件会跳过重建并保留随包 SQLite 数据库，避免把资料库清空。

资料库会按当前配置文件名称自动区分：

- `ni`：使用艾玛资料库，包含 12 份“艾玛对他人认知”资料和 1 份公共背景词典，不包含艾玛自身设定。
- 其他配置：默认使用希罗资料库，包含 12 份“希罗对他人认知”资料和 1 份公共背景词典，不包含希罗自身设定。

12 份“对他人认知”资料入库时会合并 roleplay skill 中的对应角色片段：艾玛库合并 `ema-roleplay` 的角色条目与 cast-style 摘要；希罗库合并 `hiro-roleplay` 的角色 dossier 与 cast-style 摘要。公共背景词典保持为单独公共资料。

该工具适合让模型按角色名、别名、关系、语气、背景名词等关键词检索资料，再结合当前对话生成回复。多个关键词会按“任一关键词命中后再按分数排序”返回结果，避免泛词把具体角色资料过滤掉。工具说明中内置 13 名主要角色关键词：樱羽艾玛、二阶堂希罗、紫藤亚里沙、夏目安安、城崎诺亚、莲见蕾雅、佐伯米莉亚、宝生玛格、黑部奈叶香、橘雪莉、远野汉娜、泽渡可可、冰上梅露露。

## 群友史

- `/群友史 QQ号 消息内容 | QQ号 消息内容 | ...`：按输入构造合并转发聊天记录。
- `/群友史帮助`：查看格式说明。

每个消息段之间使用 `|` 分隔，每个消息段必须是 `QQ号 消息内容`。如果在某个消息段中附带图片，图片会被放入对应 QQ 的合并转发节点中。

节点昵称通过当前 AIOCQHTTP 适配器的 `get_stranger_info` 获取，不再访问第三方昵称接口。

可在插件配置页的 `group_history.enable_group_history_feature` 中开启或关闭该功能，默认开启。关闭后 `/群友史` 会提示功能已关闭，不再生成合并转发聊天记录。

## LLM 输出后处理

插件会在模型回复发送前对纯文本结果做自然分段，必要时逐句发送，或按 `stream_output` 配置改用合并转发打包发送。

当合并转发节点数量超过平台单次上限时，插件会自动按每批最多 100 个节点拆成多条合并转发发送，避免长回复因节点数量过多而整体发送失败。

## 变更说明

- 关键词命中后从配置的本地语音目录发送语音。
- 新增 NullDox 风格的 `/土味情话 [QQ号|@用户]` 指令。
- 新增 `/点歌` 音乐搜索与点歌功能。
- 新增 `/网易云登录` 扫码登录功能，可自动持久化保存网易云 Cookie。
- 新增 AI 主动语音发送工具，可调用外部 TTS API 生成并发送语音。
- 新增 AIOCQHTTP 账号下线邮件通知功能。
- 新增下线 Webhook 发送端与接收端，可在多个 AstrBot 实例之间推送下线提醒。
- 新增角色资料库搜索工具，可按 ni/其他配置自动选择艾玛或希罗资料库。
- 新增 `群友史` 构造聊天记录功能，输出为合并转发节点。
- 输出流重整的合并转发发送会自动按 100 个节点分批。
- 已移除语音生成命令。
- 已移除骰子指令处理。

## 开发计划

功能状态、依赖条件和验收标准见 [TODO.md](TODO.md)。

随机群友土味情话功能的实现约定见 [LOVE_MESSAGE_DESIGN.md](LOVE_MESSAGE_DESIGN.md)。

网易云音乐 API 服务失效时的服务器排查与手动重启步骤见 [docs/网易云音乐服务重启.md](docs/网易云音乐服务重启.md)。
