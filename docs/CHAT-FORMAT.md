# 聊天与材料格式 v2

当前适配已测试的布局，不声称支持所有平台的全部导出变体。所有文本以 UTF-8/UTF-8 BOM 读取；未知编码显式报错。

| 格式 | 布局 |
| --- | --- |
| 微信 TXT | 时间行 `YYYY-MM-DD HH:MM:SS`、发送者行、可多行正文 |
| QQ TXT | 时间与 `昵称(数字账号)` 同行，随后正文；数字账号须另行映射角色 |
| 微信 HTML | `div.message` 中 `span.time`、`span.sender`、`div.content`；当前适配双引号 class |
| QQ MHT | MIME HTML 部分，或裸 HTML；时间、昵称与数字账号布局 |
| CSV | `time,sender,content`，或下面列出的字段名；保留引号内多行 |
| JSON / JSONL | 数组、带 messages 数组的对象，或逐行对象；损坏 JSONL 行报告位置 |

最小可靠单聊示例：

```json
{"accountId":"u","peerId":"t","conversationId":"chat-1","conversationType":"direct","messages":[{"localId":"1","isSend":1,"time":"2026-05-10T10:00:00+08:00","content":"周末见？"},{"localId":"2","isSend":0,"content":"好啊","quote":{"id":"1","content":"周末见？"}}]}
```

`accountId` 只有在确认它是用户账号后使用。可通过 CLI 覆盖。`isSend` 支持 0/1、布尔及字符串 0/1；不把群聊的所有接收者视为同一人。稳定 senderId 存在时优先使用；与 isSend 冲突则标 unknown，保留诊断。

字段别名：时间 sent_at/timestamp/time/createTime/CreateTime；正文 content/text/msg/StrContent；账号 sender_id/senderId/fromId/SenderId；显示名 sender/from/nickName/NickName/displayName；消息 ID message_id/localId/msgId/id。引用 quoted_message_id/quotedMessageId/quoteId 或 quote.id/localId；回复 reply_to_id/replyToId。未解析引用保留原文及 unresolved_reference。

```sh
python tools/chat_parser.py export.json 小美 --json --output normalized.json
python tools/chat_parser.py export.csv 小美 --user-id u --target-id t --conversation-id chat-1 --conversation-type direct --json
python tools/chat_parser.py group.json 小美 --user-id u --conversation-type group --participants roles.json --json
```

roles.json 是精确账号映射，例如 `{"u":"user","t":"target","x":"third_party"}`。支持 system 与 unknown。无账号时仅做会话内的精确昵称映射，标 display_name_only_identity，模型仍须核对关键身份；不同文件不会凭相同昵称跨文件合并。昵称有歧义时提供账号或保留 unknown。

输出 schema_version=2，包括 message_id、conversation_id、sender_id、role、sender、source_order、sent_at、time_status、content、message_type、reply_to_id、quoted_message_id、quoted_text、source_refs、parse_status、issues、conversation_type、id_method。source_refs 包含文件绝对路径、SHA-256、行号/记录位置。顶层给出 parser_version、输入数量、去重数和 diagnostics。未知字段/不匹配布局不伪造完整覆盖；MHT/HTML 适配不等于通用网页解析器。

原始 ID 按账号和会话命名空间处理。没有会话身份时用文件哈希隔离；没有消息 ID 时用文件哈希加位置。重复同文件稳定去重；只有可靠原始 ID 才能合并重叠文件。相同 ID 下正文、发送者、时间或引用冲突会报错。没有可靠 ID 的跨文件相同内容保留，不能视为已去重。

时间不默认采用运行电脑的时区。epoch 为 UTC；带偏移量时间可绝对比较；无偏移量标 timezone_unknown，只能按同会话源时钟估算；date_only/missing/invalid 不参与间隔。两个无时区值不保证实际处于同一时区，报告对此保留标记。

回复间隔：按源顺序相邻交替发言，从上一轮最后一条到下一条估算，不保证它是实际回应。群聊、未知会话、未知参与者、不可比较时钟和逆序时间排除并计数；长间隔不截断。偶数中位数取中间两项均值。会话发起数按 60 分钟间隔切分，仅表示片段中的会话起点，并非真实第一次联系。活跃小时是源时钟分布，不是最佳发送时段。无分数和情感标签。

解析默认不写记忆。用户已启用档案时，显式加 `--track-time --slug NAME --base-dir DIR` 导入。报告写到档案外；原始材料不自动复制，用户需自行保留原路径，`migrate_v2.py NAME --check --base-dir DIR` 可核验来源哈希。

社交工具保留原帖字段及来源，文本截断显式标记，图片仅登记未 OCR。照片工具只读取 EXIF 和拍摄聚类；缺少 GPS 时不推断地点，设备型号不能确认作者，聚类不能证明双方见面。
