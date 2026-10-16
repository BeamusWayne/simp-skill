# 建档与更新

仅在用户要建档、更新档案，或当前问题确实缺少关键信息时使用。昵称/slug、当前目标与用户愿意给出的背景即可起步；年龄、职业、MBTI、收入和完整聊天史均非必填。

先确认当前操作对象，避免同名档案串人；用户已指定就直接使用。明确建档授权后运行 `python tools/skill_writer.py --action init --slug NAME --base-dir DIR`。此操作只创建本地结构，不自动复制聊天或照片。未建档的消息辅助继续用临时上下文。

用户确认的背景记 user_report，表达偏好记 preference，模型猜测记 assessment。更新事实使用 supersedes 指向旧记录，不能直接覆盖投影。具体协议及 JSON 示例见 `docs/MEM-SYS.md`。

更改 nickname、mode、goal 可用 `skill_writer.py --action update-meta` 的对应参数；`--score`、`--stage` 已废弃。用户说“我们已开始交往”是有来源的用户报告，不转换成固定阶段数值。
