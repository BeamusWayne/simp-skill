# Mem-Sys 实现规划书

> 分支：`Mem-Sys` | 创建于 2026-04-12

## 一、现状分析

现有文件结构：
```
crushes/{slug}/
├── profile.md      ← 纯 Markdown 散文，无结构化字段，Claude 读写靠理解
├── strategy.md     ← 同上
├── meta.json       ← 有结构，但字段稀疏（仅 stage、score、mode）
├── memories/chats/ ← 原始聊天记录
└── versions/       ← 手动备份，不自动维护
```

**核心问题**：
1. `profile.md` 没有 YAML frontmatter，Claude 无法可靠提取/更新单个字段
2. 没有"当前状态快照"，每次 `/simp progress` 都要重新推断阶段
3. 没有事件日志，历史演变不可追溯，`/simp quit` 无法看"感情轨迹"
4. `versions/` 是手动备份，不是真正的历史记录

---

## 二、新文件结构

```
crushes/{slug}/
├── profile.md       # 【升级】稳定层 — YAML frontmatter + 叙述体
├── state.md         # 【新增】动态层 — 当前快照，每次会话后覆盖
├── events.jsonl     # 【新增】事件流 — 只追加，永不删除
├── strategy.md      # 【保留】追求策略（不动）
├── meta.json        # 【扩展】元数据，新增索引字段
├── memories/
│   ├── chats/
│   ├── social/
│   └── photos/
└── snapshots/       # 【新增】定期快照目录
    └── YYYY-MM-DD.json
```

**读取优先级**（context window 分配）：

| 文件 | 加载时机 | 预估 tokens |
|------|----------|------------|
| `profile.md` | 每次必读 | ~300 |
| `state.md` | 每次必读 | ~200 |
| `events.jsonl` 最近5条 | progress/analyze/quit | ~150 |
| `strategy.md` | message/confess/analyze | ~400 |
| `events.jsonl` 全部 | 用户明确要求回顾时 | 按需 |

---

## 三、文件 Schema 定义

### 3.1 `profile.md`（稳定层）

```markdown
---
nickname: 小雨
slug: xiaoyu
gender: 女
age: 23
occupation: 设计师
city: 上海
mbti: ENFP
zodiac: 双鱼
personality_type: 感性型
how_met: 同学介绍
created_at: "2026-04-10"
---

## 性格画像
ta 话很多，喜欢用颜文字，情绪外露，容易被细节打动。
见面时会不自觉靠近，但如果感觉被冷落会直接不回消息。

## 最打动ta的方式
具体的画面感 > 泛泛的夸奖。说"你刚才皱眉的样子"比"你很可爱"更有效。

## 用户自身风格
说话偏幽默，短句为主，偶尔用表情包，追求混合模式。

## 注意事项
ta 对"套路感"敏感，一旦感觉被设计会直接拉远距离。
```

**规则**：
- YAML frontmatter 存结构化字段，Claude 更新时用字段名精确修改
- 正文存叙述性内容，只追加，不覆盖
- `personality_type` 枚举值：`感性型 | 理性型 | 傲娇型 | 温柔型`

---

### 3.2 `state.md`（动态层）

```markdown
---
current_stage: 暧昧期
signal_score: 17
last_signal_score: 14
score_trend: up
recommended_mode: 混合
last_updated: "2026-04-12T10:30:00"
milestones_done: 7
---

## 当前状态（一句话）
关系持续升温，ta 开始主动制造见面机会。

## 最近信号（最新3条）
- 🟢 2026-04-11 ta 主动问周末有没有空
- 🟢 2026-04-10 深夜发了消息说"突然想到你"
- 🟡 2026-04-08 回复比往常慢了一些

## 当前策略方向
暧昧期推进：制造1v1心跳时刻，评估表白时机是否成熟。

## 下一步建议
本周制造一次晚间1v1见面，用 /simp message 准备好开场话题。
```

**规则**：
- 每次 `/simp analyze`、`/simp progress` 结束后**全量覆盖**
- `score_trend` 枚举：`up | down | stable`
- `current_stage` 枚举：`破冰期 | 升温期 | 暧昧期 | 表白前 | 表白后-成功 | 表白后-被拒 | 友谊区 | 重启期`

---

### 3.3 `events.jsonl`（事件流）

每行一个独立 JSON 对象，严格只追加：

```jsonl
{"ts":"2026-04-10T14:00:00","v":1,"type":"profile_created","slug":"xiaoyu","data":{"nickname":"小雨","personality_type":"感性型"}}
{"ts":"2026-04-11T20:30:00","v":1,"type":"signal_recorded","slug":"xiaoyu","data":{"direction":"green","content":"深夜主动发消息说突然想到你","score_delta":3}}
{"ts":"2026-04-12T10:30:00","v":1,"type":"stage_changed","slug":"xiaoyu","data":{"from":"升温期","to":"暧昧期","trigger":"连续3天主动联系 + 深夜消息"}}
{"ts":"2026-04-12T10:30:00","v":1,"type":"analysis_done","slug":"xiaoyu","data":{"score":17,"stage":"暧昧期","summary":"ta 主动性明显增强，信号偏绿"}}
```

**事件类型字典**：

| type | 触发指令 | data 必填字段 |
|------|---------|--------------|
| `profile_created` | `/simp create` | nickname, personality_type |
| `profile_updated` | `/simp update` | field, old_value, new_value |
| `stage_changed` | analyze/progress | from, to, trigger |
| `signal_recorded` | `/simp analyze` | direction(green/red/neutral), content, score_delta |
| `analysis_done` | `/simp analyze` | score, stage, summary |
| `progress_evaluated` | `/simp progress` | score, stage, milestones_done, next_actions |
| `strategy_updated` | 阶段变化时 | old_stage, new_stage, reason |
| `crisis_handled` | `/simp crisis` | crisis_type, resolution |
| `quit_evaluated` | `/simp quit` | verdict(continue/reconsider/let_go), reason |
| `confess_prepared` | `/simp confess` | method, readiness_score |

---

### 3.4 `meta.json`（扩展）

```json
{
  "slug": "xiaoyu",
  "nickname": "小雨",
  "created_at": "2026-04-10T14:00:00",
  "updated_at": "2026-04-12T10:30:00",
  "version": "v1",
  "current_stage": "暧昧期",
  "signal_score": 17,
  "mode": "hybrid",
  "event_count": 4,
  "last_snapshot": "2026-04-12"
}
```

新增字段：`nickname`（用于 list 展示）、`event_count`（快速统计）、`last_snapshot`

---

## 四、每条指令的 Memory Protocol

```
指令               读取                    写入
─────────────────────────────────────────────────────────
/simp create      无                      profile.md(新建)
                                          state.md(空模板)
                                          events.jsonl(新建)
                                          meta.json(新建)

/simp analyze     profile.md              state.md(覆盖)
                  state.md                events.jsonl(追加:
                                           signal_recorded
                                           analysis_done
                                           stage_changed 若变化)

/simp message     profile.md              无
                  state.md
                  strategy.md

/simp progress    profile.md              state.md(覆盖)
                  state.md                events.jsonl(追加:
                  events.jsonl 最近5条      progress_evaluated)
                                          meta.json(更新score/stage)

/simp update      profile.md              profile.md(更新frontmatter)
                                          events.jsonl(追加:
                                           profile_updated)

/simp confess     profile.md              events.jsonl(追加:
                  state.md                 confess_prepared)
                  strategy.md

/simp crisis      profile.md              state.md(更新状态)
                  state.md                events.jsonl(追加:
                                           crisis_handled)

/simp daily       state.md 仅此           无

/simp quit        profile.md              events.jsonl(追加:
                  state.md                 quit_evaluated)
                  events.jsonl 全部

/simp list        meta.json(所有slug)     无
```

---

## 五、新增 Python 工具：`tools/memory.py`

### 5.1 模块职责

`memory.py` 是记忆系统的唯一入口，`skill_writer.py` 调用它，Claude 通过 shell 调用它。

### 5.2 CLI 接口

```bash
# 追加事件
python3 tools/memory.py append <slug> <event_type> '<json_data>'

# 读取最近N条事件
python3 tools/memory.py events <slug> --last 5

# 读取当前上下文（profile.md + state.md 合并输出）
python3 tools/memory.py context <slug>

# 从事件流重建 state.md
python3 tools/memory.py rebuild <slug>

# 生成日快照
python3 tools/memory.py snapshot <slug>

# 查看事件时间线
python3 tools/memory.py timeline <slug>
```

### 5.3 核心函数签名

```python
def append_event(
    slug: str,
    event_type: str,
    data: dict,
    base_dir: Path = DEFAULT_BASE_DIR
) -> None:
    """追加一条事件到 events.jsonl，同时更新 meta.json 的 event_count"""

def get_recent_events(
    slug: str,
    n: int = 5,
    event_types: list[str] | None = None,
    base_dir: Path = DEFAULT_BASE_DIR
) -> list[dict]:
    """返回最近 N 条事件，可按 type 过滤"""

def load_context(
    slug: str,
    include_strategy: bool = False,
    base_dir: Path = DEFAULT_BASE_DIR
) -> str:
    """拼装 profile.md + state.md，供 Claude 直接注入 context"""

def update_state(
    slug: str,
    frontmatter_updates: dict,
    sections: dict[str, str],
    base_dir: Path = DEFAULT_BASE_DIR
) -> None:
    """全量覆盖 state.md，frontmatter_updates 更新 YAML 字段"""

def take_snapshot(
    slug: str,
    base_dir: Path = DEFAULT_BASE_DIR
) -> Path:
    """将 meta.json + state.md frontmatter 合并写入 snapshots/YYYY-MM-DD.json"""

def rebuild_state_from_events(
    slug: str,
    base_dir: Path = DEFAULT_BASE_DIR
) -> dict:
    """从 events.jsonl 重放，返回推断的当前状态（用于校验或恢复）"""
```

---

## 六、`skill_writer.py` 改动

`init_crush()` 新增三步：

1. 在 `profile.md` 模板顶部加 YAML frontmatter
2. 创建 `state.md`（空模板）
3. 创建 `events.jsonl`（空文件）
4. 创建 `snapshots/` 目录
5. `meta.json` 新增 `nickname`、`event_count: 0`、`last_snapshot: null` 字段

`backup_crush()` 扩展：同步备份 `state.md`（events.jsonl 不备份，它是不可变历史）。

`update_meta()` 扩展：支持更新 `nickname`、`event_count`、`last_snapshot`。

---

## 七、`SKILL.md` 改动（Phase 3）

在「运行规则」之前新增「记忆操作协议」章节，定义每条指令的读写规则。

---

## 八、实施步骤

### Phase 1：Schema 落地（基础）✅
- [x] 更新 `init_crush()` — 新增 `state.md`、`events.jsonl`、`snapshots/` 的创建
- [x] 更新 `profile.md` 模板 — 加 YAML frontmatter
- [x] 扩展 `meta.json` schema — 新增字段
- [x] 更新测试

### Phase 2：memory.py 工具 ✅
- [x] 实现 `append_event()`
- [x] 实现 `get_recent_events()`
- [x] 实现 `update_state()`
- [x] 实现 `load_context()`
- [x] 实现 `take_snapshot()`
- [x] 实现 `rebuild_state_from_events()`
- [x] CLI 入口
- [ ] 完整测试覆盖

### Phase 3：SKILL.md 集成 ✅
- [x] 新增「记忆操作协议」章节
- [x] 每条指令补充 Memory Protocol 说明
- [x] `progress_tracker.md` 更新读取路径

### Phase 4：迁移工具
- [ ] `tools/migrate.py` — 为已有 `profile.md` 添加 YAML frontmatter
- [ ] 从现有 `meta.json` 生成初始 `events.jsonl`

---

## 九、测试计划

```
tests/
├── test_skill_writer.py   # 已有，补充新字段断言
├── test_memory.py         # 新增（Phase 2）
└── test_migrate.py        # 新增（Phase 4）
```

---

## 十、一句话原则备忘

| 文件 | 一句话规则 |
|------|-----------|
| `profile.md` | 只增不减，YAML 字段可更新，正文只追加 |
| `state.md` | 代表"现在"，每次全量覆盖 |
| `events.jsonl` | 代表"历史"，只追加，永不删除 |
| `strategy.md` | 阶段变化时更新，其他时候只读 |
| `snapshots/` | 每日自动生成，用于跨会话快速恢复 |
