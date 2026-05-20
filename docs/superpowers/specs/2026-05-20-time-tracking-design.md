# 时间记录功能设计规格

> 状态：待审核
> 日期：2026-05-20
> 方案：B — 独立互动日志

---

## 一、目标

为 simp-skill 新增时间记录与分析功能，覆盖四个维度：

1. **互动时间线** — 互动频率热力图 + 连续互动天数 + 主动比例
2. **追求时长追踪** — 各阶段停留时长 + 里程碑达成时间 + 基线对比
3. **回复时间分析** — 对方回复速度分布 + 趋势 + 解读
4. **黄金时段建议** — 对方活跃时段分布 + 最佳发消息窗口

---

## 二、数据模型

### 2.1 文件位置

`crushes/{slug}/interactions.jsonl` — 独立于 `events.jsonl`，专门存储互动时间数据。

### 2.2 Schema

每行一条 JSON 记录，只追加不删除：

```jsonl
{"ts":"2026-05-15T22:30:00","v":1,"type":"chat_sent","slug":"xiaoyu","data":{"content_summary":"问她周末有没有空","hour":22,"day_of_week":"thu","is_initiator":true}}
{"ts":"2026-05-15T22:32:00","v":1,"type":"chat_received","slug":"xiaoyu","data":{"content_summary":"有空呀，你有什么安排吗","hour":22,"day_of_week":"thu","is_initiator":false,"reply_delay_min":2}}
{"ts":"2026-05-17T19:00:00","v":1,"type":"meeting","slug":"xiaoyu","data":{"duration_min":180,"location":"外滩咖啡厅","activity":"咖啡+散步","initiator":"me"}}
```

### 2.3 互动类型字典

| type | 来源 | data 必填字段 | data 可选字段 |
|------|------|--------------|-------------|
| `chat_sent` | 自动/手动 | content_summary, hour, day_of_week, is_initiator(true) | platform |
| `chat_received` | 自动/手动 | content_summary, hour, day_of_week, is_initiator(false) | reply_delay_min, platform |
| `meeting` | 手动 | duration_min, activity | location, initiator(me/them/mutual) |
| `call` | 手动 | duration_min | initiator, call_type(voice/video) |
| `online_interaction` | 手动 | platform, interaction_type(like/comment/reply) | content_summary |

### 2.4 设计决策

- `hour` 和 `day_of_week` 写入时计算，避免分析时反复解析 `ts`
- `reply_delay_min` 只记录对方回复你的延迟
- `is_initiator` 对 chat_sent 恒为 true，chat_received 恒为 false；meeting/call 可以是任意一方发起
- `content_summary` 是简短描述而非原文，保护隐私

---

## 三、数据采集

### 3.1 自动采集：扩展 `chat_parser.py`

现有流程：解析聊天 → 生成分析报告
扩展流程：解析聊天 → 生成分析报告 → 提取互动时间数据写入 `interactions.jsonl`

新增逻辑：
- 逐条消息提取 timestamp → 计算 hour、day_of_week
- 相邻消息发送方不同时，计算 reply_delay_min（对方回复你的延迟）
- 自动判断 is_initiator（谁先发起当天第一段对话）
- 按时间戳去重：跳过 `interactions.jsonl` 中已有 `ts` 的记录

新增 CLI 参数：
```bash
python3 tools/chat_parser.py 聊天记录.txt 小美 --track-time
```

### 3.2 手动录入：`time_tracker.py` CLI

```bash
python3 tools/time_tracker.py record xiaomei meeting --duration 180 --activity "咖啡+散步" --location "外滩"
python3 tools/time_tracker.py record xiaomei call --duration 45 --initiator them
python3 tools/time_tracker.py record xiaomei chat_sent --summary "问她周末有没有空" --time "2026-05-15T22:30"
python3 tools/time_tracker.py record xiaomei chat_received --summary "有空呀" --time "2026-05-15T22:32"
```

### 3.3 核心函数签名

```python
def record_interaction(
    slug: str,
    interaction_type: str,
    data: dict[str, Any],
    ts: datetime | None = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> None:
    """写入 interactions.jsonl，缺省 ts 取 now()，自动计算 hour/day_of_week，同步更新 meta.json"""

def get_interactions(
    slug: str,
    days: int | None = None,
    types: list[str] | None = None,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    """按时间范围和类型过滤读取互动记录"""

def get_reply_times(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> list[dict[str, Any]]:
    """只返回有 reply_delay_min 的 chat_received 记录"""

def get_interaction_frequency(
    slug: str,
    days: int = 30,
    base_dir: Path = DEFAULT_BASE_DIR,
) -> dict[str, Any]:
    """按 hour / day_of_week 聚合互动频率分布"""
```

### 3.4 去重策略

按时间戳去重。写入前检查最后一条记录的 `ts`：
- 相同 `ts` + 相同 `type` → 跳过
- `chat_parser.py` 重新解析时从最后一条已有的 `ts` 之后继续写入

---

## 四、分析功能

### 4.1 互动时间线

终端 ASCII 热力图 + 互动统计（总次数、连续天数、主动比例）。Markdown 导出用 Mermaid 图渲染。

分析函数：`analyze_timeline(slug, days=30)`

### 4.2 追求时长追踪

各阶段停留时长 + 进度条 + 与内置基线对比 + 关键里程碑达成时间。

基线数据：内置参考值（基于社交心理学文献），写入 `time_tracker.py` 常量。

分析函数：`analyze_milestones(slug, events_jsonl, interactions_jsonl)`

### 4.3 回复时间分析

对方回复速度分布（≤5min / 5-15min / 15-60min / 1-4h / >4h / 无回复）+ 按周趋势 + 解读。

分析函数：`analyze_reply_times(slug, days=30)`

### 4.4 黄金时段建议

对方活跃时段分布 + 最佳发送窗口 + 周末 vs 工作日差异。

分析函数：`analyze_golden_hours(slug, days=30)`

### 4.5 聚合入口

`/simp timeline` 指令，支持按维度单独查看：

```
/simp timeline              — 完整时间分析报告
/simp timeline --frequency  — 互动频率热力图
/simp timeline --milestones — 追求时长追踪
/simp timeline --reply      — 回复时间分析
/simp timeline --golden     — 黄金时段建议
/simp timeline --output report.md  — 导出 Markdown 报告
```

---

## 五、与现有系统的集成

### 5.1 现有指令增强

| 现有指令 | 增强点 | 数据来源 |
|---------|--------|---------|
| `/simp progress` | 新增「互动节奏」段落 | `interactions.jsonl` |
| `/simp daily` | 附加最佳发送时段 | 黄金时段分析 |
| `/simp analyze` | 信号解读参考回复速度趋势 | 回复时间分析 |
| `/simp create` | 创建空的 `interactions.jsonl` | — |

### 5.2 SKILL.md 变更

指令表格新增 `/simp timeline` 行。记忆操作协议表格新增对应行。更新 `/simp create` 写入列。

### 5.3 prompts 变更

- **新增** `prompts/timeline.md`：`/simp timeline` 的 prompt 模板
- **修改** `prompts/progress_tracker.md`：读取 `interactions.jsonl`，输出增强
- **修改** `prompts/daily_coach.md`：引用黄金时段

### 5.4 meta.json 新增字段

```json
{
  "interaction_count": 23,
  "last_interaction": "2026-05-18T09:20:00",
  "consecutive_days": 3
}
```

由 `record_interaction()` 同步更新。`/simp list` 可直接展示互动概况。

---

## 六、文件变更清单

| 操作 | 文件 | 改动范围 |
|------|------|---------|
| 新建 | `tools/time_tracker.py` | 全新文件，~300 行 |
| 新建 | `prompts/timeline.md` | 全新 prompt，~150 行 |
| 新建 | `tests/test_time_tracker.py` | 测试文件 |
| 修改 | `tools/chat_parser.py` | 新增 `--track-time` 参数 + 互动时间提取逻辑 |
| 修改 | `tools/skill_writer.py` | `init_crush()` 新增创建 `interactions.jsonl` |
| 修改 | `SKILL.md` | 新增指令 + 更新操作协议 |
| 修改 | `prompts/progress_tracker.md` | 读取 `interactions.jsonl` + 输出增强 |
| 修改 | `prompts/daily_coach.md` | 引用黄金时段 |
| 修改 | `README.md` | 新增功能说明 |
