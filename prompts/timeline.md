# 互动统计

需要实际统计时读 `docs/CHAT-FORMAT.md`。使用已启用的指定档案：

```sh
python tools/time_tracker.py analyze NAME --base-dir DIR
python tools/time_tracker.py analyze NAME --reply --base-dir DIR
python tools/time_tracker.py analyze NAME --days 30 --now 2026-05-11T00:00:00+08:00 --base-dir DIR
```

默认统计全部已记录互动；指定 days 时只纳入窗口内时区明确的实际发生时间，同时报告排除数。记录时间不替代事件时间；尚未执行的建议不算互动。

回复间隔按相邻交替发言轮次，从上一轮最后一条计算。不是显式 reply_to 的因果断言；长间隔不剔除。报告有效样本、排除原因与方法。缺失数据不记零，不推断没有兴趣。

`--frequency` 展示描述统计；`--milestones` 展示有来源的实际行动与结果；`--golden` 是兼容别名，仅展示源时间里的活跃小时，不承诺最佳联系时段。没有阶段时长基准、速度好坏标签或感情评分。CLI 输出 JSON；自然语言解释按当前问题选择必要数据。
