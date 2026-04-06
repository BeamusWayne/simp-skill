# simp-skill · 产品化落地方案

> 从 Claude Code Skill → 独立 WebApp MVP
> 版本：v0.1 Draft
> 日期：2026-04-06

---

## 一、总体思路

把 simp-skill 从「一套 prompt + 脚本」变成「一个任何人打开浏览器就能用的产品」。

核心策略：**Skill 即后端大脑，前端做体验层，API 做粘合剂。**

你现有的资产分三层，产品化时各有去处：

| 现有资产 | 位置 | 产品化后的角色 |
|---------|------|--------------|
| SKILL.md + prompts/*.md | Prompt 层 | → 后端 System Prompt，按功能拆成 API 路由 |
| tools/*.py | 数据处理层 | → 后端微服务 / Serverless Function |
| crushes/ 目录结构 | 存储层 | → 数据库 Schema |

---

## 二、推荐技术栈

### 前端（选其一）

| 方案 | 优势 | 适合场景 |
|------|------|---------|
| **Next.js (React)** | 生态最大，SSR/SSG 支持好，Vercel 一键部署 | 想做 H5 / Web App |
| **Nuxt (Vue)** | 中文社区活跃，上手快 | 团队熟悉 Vue |
| **微信小程序 (Taro/uni-app)** | 微信生态天然匹配，分享获客成本低 | 主攻国内市场 |

**建议**：先做 H5（Next.js），用 Capacitor 或 Taro 包一层小程序壳。一套代码两端跑。

### 后端

| 组件 | 技术选择 | 理由 |
|------|---------|------|
| API 框架 | **FastAPI (Python)** | 你的工具链全是 Python，复用零成本 |
| LLM 层 | Claude API (Anthropic SDK) | 你的 prompt 就是为 Claude 写的 |
| 数据库 | **Supabase (PostgreSQL + Auth + Storage)** | 免费起步，自带用户系统和文件存储 |
| 缓存 | Redis (Upstash) | 会话上下文缓存，免费额度够 MVP |
| 部署 | Railway / Fly.io / 国内可用阿里云函数计算 | 便宜，Python 友好 |

### 基础设施

```
┌──────────────────────────────────────────────────────┐
│                    前端 (Next.js / 小程序)              │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ 对话界面  │  │ 档案面板  │  │ 信号仪表盘 │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
└───────┼──────────────┼──────────────┼─────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────────────────────────────────────────────┐
│                    API 网关 (FastAPI)                  │
│                                                      │
│  /api/chat        → Prompt Orchestrator              │
│  /api/analyze     → Signal Reader + chat_parser.py   │
│  /api/message     → Message Crafter                  │
│  /api/crush       → Profile CRUD                     │
│  /api/crisis      → Crisis Handler                   │
│  /api/confess     → Strategy Builder                 │
│                                                      │
│  中间件：Auth / Rate Limit / Usage Tracking           │
└──────────────┬─────────────────┬─────────────────────┘
               │                 │
        ┌──────┴──────┐   ┌─────┴──────┐
        │ Claude API  │   │  Supabase  │
        │ (LLM 推理)  │   │  (DB/Auth) │
        └─────────────┘   └────────────┘
```

---

## 三、Prompt → API 映射表

你现有的 6 个 prompt 文件，每个对应一个 API 端点：

| Prompt 文件 | API 路由 | 前端触发方式 | 说明 |
|-------------|---------|------------|------|
| `intake.md` | `POST /api/crush` | "建立档案"按钮 → 多步表单 | 引导式问答，前端做表单化 |
| `signal_reader.md` | `POST /api/analyze` | "分析信号"按钮 → 上传聊天记录或文字描述 | 调用 chat_parser.py 预处理后喂给 Claude |
| `message_crafter.md` | `POST /api/message` | "帮我写消息"按钮 → 情境选择器 | 最高频功能，前端做情境卡片 |
| `strategy_builder.md` | `POST /api/strategy` | "制定策略"按钮 → 档案关联 | 依赖档案数据，后端自动注入上下文 |
| `crisis_handler.md` | `POST /api/crisis` | "紧急求助"按钮 → 危机类型选择 | 需要快速响应，用 streaming |
| `persona_builder.md` | 内部调用 | 不直接暴露 | 被 strategy/message 内部引用 |

### Prompt Orchestrator 核心逻辑

```python
# prompt_orchestrator.py — 核心路由逻辑

import anthropic
from pathlib import Path

client = anthropic.Anthropic()

# 加载 prompt 模板
PROMPTS = {}
for f in Path("prompts").glob("*.md"):
    PROMPTS[f.stem] = f.read_text()

SKILL_SYSTEM = Path("SKILL.md").read_text()

def build_system_prompt(module: str, crush_profile: dict | None = None) -> str:
    """
    组装 system prompt：
    基础人设 (SKILL.md) + 功能模块 prompt + 档案上下文
    """
    parts = [SKILL_SYSTEM, PROMPTS[module]]

    if crush_profile:
        parts.append(f"\n\n## 当前心上人档案\n{format_profile(crush_profile)}")

    return "\n\n---\n\n".join(parts)


async def run(module: str, user_message: str, crush_id: str | None = None):
    """统一调用入口"""
    profile = await db.get_crush(crush_id) if crush_id else None
    system = build_system_prompt(module, profile)

    response = client.messages.create(
        model="claude-sonnet-4-5-20241022",  # MVP 用 Sonnet 控成本
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_message}],
        stream=True,
    )
    return response
```

---

## 四、数据库设计

把你现有的 `crushes/` 文件结构转成关系型数据库：

```sql
-- 用户表
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    nickname    TEXT,
    style       JSONB,          -- 用户说话风格偏好
    mode        TEXT DEFAULT 'hybrid'  -- sweet / strategic / hybrid
);

-- 心上人档案（对应 profile.md + meta.json）
CREATE TABLE crushes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    slug            TEXT NOT NULL,
    nickname        TEXT NOT NULL,

    -- 基本信息
    age             INT,
    gender          TEXT,
    occupation      TEXT,
    city            TEXT,

    -- 性格画像
    personality     TEXT,           -- 感性型/理性型/傲娇型/温柔型
    mbti            TEXT,
    zodiac          TEXT,
    hobbies         TEXT[],
    quirks          TEXT,
    what_you_love   TEXT,

    -- 关系现状
    how_met         TEXT,
    relationship    TEXT,
    current_stage   TEXT,           -- icebreak/warming/ambiguous/pre-confess/post-confess
    interaction_mode TEXT,
    who_initiates   TEXT,
    knows_feelings  BOOLEAN DEFAULT FALSE,

    -- 评分
    signal_score    INT DEFAULT 0,  -- -15 ~ 25
    score_history   JSONB DEFAULT '[]',

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(user_id, slug)
);

-- 信号分析记录（对应 memories/chats/）
CREATE TABLE signal_analyses (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crush_id    UUID REFERENCES crushes(id),
    source_type TEXT,            -- chat_upload / manual_describe / social
    raw_input   TEXT,            -- 用户输入的原文或上传文件路径

    -- 评分结果（三维度 + 总分）
    score_message    INT,        -- 消息互动维度 /10
    score_offline    INT,        -- 线下互动维度 /8
    score_emotional  INT,        -- 情感投入维度 /7
    total_score      INT,        -- 合计 /25

    stage_judgment   TEXT,       -- AI 判断的当前阶段
    key_signals      JSONB,      -- 关键信号列表
    advice           TEXT,       -- 下一步建议

    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 对话历史（用于上下文延续）
CREATE TABLE conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    crush_id    UUID REFERENCES crushes(id),
    module      TEXT,            -- analyze / message / crisis / ...
    messages    JSONB,           -- [{role, content, timestamp}]
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- 生成的消息收藏
CREATE TABLE saved_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crush_id    UUID REFERENCES crushes(id),
    context     TEXT,            -- 生成时的情境描述
    message     TEXT,            -- 生成的情话/消息
    used        BOOLEAN DEFAULT FALSE,  -- 用户是否标记"已发送"
    feedback    TEXT,            -- 效果反馈：好/一般/翻车
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 五、chat_parser.py 的产品化改造

你的 chat_parser.py 是最有技术壁垒的部分（支持 6 种格式解析），产品化需要做几件事：

### 5.1 改造为 API 服务

```python
# api/routes/analyze.py

from fastapi import APIRouter, UploadFile, File, Form
from tools.chat_parser import detect_format, parse_file, analyze_signals

router = APIRouter()

@router.post("/api/analyze/upload")
async def analyze_chat_upload(
    file: UploadFile = File(...),
    crush_id: str = Form(...),
    target_name: str = Form(...),
):
    """上传聊天记录文件 → 解析 → 信号分析 → 返回报告"""

    # 1. 保存临时文件
    temp_path = save_temp(file)

    # 2. 探测格式 & 解析（复用你现有的逻辑）
    fmt = detect_format(temp_path)
    messages = parse_file(temp_path, fmt)

    # 3. 运行评分（复用 analyze_signals）
    score_result = analyze_signals(messages, target_name)

    # 4. 把评分结果 + 原始消息摘要喂给 Claude 生成完整报告
    report = await prompt_orchestrator.run(
        module="signal_reader",
        user_message=format_score_for_claude(score_result),
        crush_id=crush_id,
    )

    # 5. 存入数据库
    await db.save_analysis(crush_id, score_result, report)

    return {"score": score_result, "report": report}
```

### 5.2 前端聊天记录上传体验

```
用户操作流程：
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│  选择心上人   │ ──→ │ 拖拽/选择文件  │ ──→ │ 实时解析进度条  │
│  (下拉菜单)  │     │  支持格式提示  │     │  "正在读取..."  │
└─────────────┘     └──────────────┘     └───────┬───────┘
                                                  │
                    ┌──────────────┐     ┌────────▼────────┐
                    │  行动建议卡片  │ ←── │  雷达图 + 评分卡  │
                    │  "下一步..."  │     │  绿灯/黄灯/红灯  │
                    └──────────────┘     └─────────────────┘
```

---

## 六、前端核心页面设计

### 页面结构

```
/                   → 首页（引导注册 / 快速体验）
/app                → 主界面（对话 + 侧边栏）
/app/crush/:id      → 心上人档案详情
/app/crush/:id/signals  → 信号分析历史 & 趋势图
/app/crush/:id/messages → 已生成消息收藏
/app/crisis         → 紧急求助入口
```

### 核心交互：对话式 + 卡片式混合

不要做成纯聊天窗口（那和直接用 Claude 没区别），也不要做成纯表单（太冷冰冰）。

**混合 UI 的意思是**：对话框是主体，但 AI 回复里可以嵌入结构化卡片——

```
┌─────────────────────────────────────────┐
│  💝 追爱军师                              │
├─────────────────────────────────────────┤
│                                         │
│  [用户] 帮我分析一下最近和她的聊天          │
│                                         │
│  [AI] 我看了你上传的最近 30 天聊天记录，    │
│       分析结果如下：                       │
│                                         │
│  ┌─────────────────────────────┐        │
│  │  📊 信号评分：18/25          │        │
│  │                             │        │
│  │  [雷达图：6维度可视化]        │        │
│  │                             │        │
│  │  🟢 主动性 5/6              │        │
│  │  🟢 深夜信号 4/5            │        │
│  │  🟡 回复趋势 2/3            │        │
│  │  ...                        │        │
│  │                             │        │
│  │  📍 当前阶段：暧昧期         │        │
│  │  📈 趋势：比上次 +3          │        │
│  └─────────────────────────────┘        │
│                                         │
│  [AI] 好消息，她对你的兴趣度在上升……        │
│       建议你这周可以……                     │
│                                         │
│  ┌──────┐ ┌──────────┐ ┌──────┐        │
│  │帮我写 │ │ 制定策略  │ │详细  │        │
│  │消息  │ │          │ │报告  │        │
│  └──────┘ └──────────┘ └──────┘        │
│                                         │
│  [输入框..............................] │
│  [📎 上传聊天记录]  [🎯 切换模式]         │
└─────────────────────────────────────────┘
```

---

## 七、MVP 功能优先级

### P0 · 第一周交付（核心体验）

1. **用户注册/登录**（Supabase Auth，支持微信 OAuth 或邮箱）
2. **创建心上人档案**（intake.md → 多步引导表单）
3. **情话/消息生成**（message_crafter.md → 情境选择 + 流式输出）
4. **基础对话**（SKILL.md 作为 system prompt 的通用聊天）

### P1 · 第二周交付（差异化功能）

5. **聊天记录上传分析**（chat_parser.py + signal_reader.md）
6. **信号评分雷达图**（可视化，用 Recharts / ECharts）
7. **危机处理**（crisis_handler.md → 危机类型选择器）
8. **消息收藏 & 反馈**（标记"已发送"、记录效果）

### P2 · 第三周交付（留存功能）

9. **追求进度时间线**（阶段变化 + 评分趋势折线图）
10. **每日建议推送**（/simp daily → 定时任务 + 通知）
11. **策略详情面板**（strategy_builder.md → 可视化路线图）
12. **模式切换**（纯情/策略/混合 → 影响所有生成结果）

### P3 · 第四周交付（商业化准备）

13. **用量限制 & 付费墙**（免费 5 次/天，付费无限）
14. **多档案管理**
15. **分享功能**（信号报告可生成海报图分享）
16. **数据导出**

---

## 八、成本估算（MVP 阶段）

| 项目 | 月成本 | 说明 |
|------|--------|------|
| Claude API (Sonnet) | ~$50-200 | 取决于用户量，100 DAU 约 $50 |
| Supabase | $0 (Free tier) | 50K 行数据 + 500MB 存储 |
| 部署 (Railway) | $5-20 | 按用量计费 |
| 域名 | ~$10/年 | |
| **合计** | **~$60-230/月** | 100 DAU 估算 |

### 成本优化策略

- **Sonnet 而非 Opus**：MVP 阶段用 Sonnet 够了，情话生成质量差异不大
- **Prompt 缓存**：SKILL.md + prompt 模板是固定的，用 Claude 的 prompt caching 可省 ~80% 输入 token 成本
- **评分逻辑代码化**：chat_parser.py 的评分逻辑不需要过 LLM，只有最终报告生成用 Claude
- **前端缓存**：同一档案的策略建议短期内不需要重新生成

---

## 九、项目目录结构（建议）

```
simp-app/
├── frontend/                   # Next.js 前端
│   ├── app/
│   │   ├── page.tsx           # 落地页
│   │   ├── app/
│   │   │   ├── page.tsx       # 主对话界面
│   │   │   ├── crush/
│   │   │   │   └── [id]/
│   │   │   │       ├── page.tsx      # 档案详情
│   │   │   │       ├── signals.tsx   # 信号分析
│   │   │   │       └── messages.tsx  # 消息收藏
│   │   │   └── crisis/
│   │   │       └── page.tsx   # 危机处理
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ChatWindow.tsx     # 对话窗口
│   │   ├── SignalRadar.tsx    # 雷达图
│   │   ├── ScoreCard.tsx      # 评分卡片
│   │   ├── CrushCard.tsx      # 档案卡片
│   │   ├── MessageBubble.tsx  # 消息气泡（支持嵌入卡片）
│   │   ├── ModeSwitch.tsx     # 模式切换器
│   │   └── FileUpload.tsx     # 聊天记录上传
│   └── lib/
│       ├── api.ts             # API 客户端
│       └── types.ts           # TypeScript 类型
│
├── backend/                    # FastAPI 后端
│   ├── main.py                # 入口
│   ├── config.py              # 配置（API keys, DB URL）
│   ├── routes/
│   │   ├── chat.py            # /api/chat — 通用对话
│   │   ├── crush.py           # /api/crush — 档案 CRUD
│   │   ├── analyze.py         # /api/analyze — 信号分析
│   │   ├── message.py         # /api/message — 消息生成
│   │   ├── crisis.py          # /api/crisis — 危机处理
│   │   └── auth.py            # /api/auth — 认证
│   ├── services/
│   │   ├── orchestrator.py    # Prompt 路由 & 组装
│   │   ├── chat_parser.py     # ← 直接复用你的 chat_parser.py
│   │   ├── social_parser.py   # ← 直接复用
│   │   ├── photo_analyzer.py  # ← 直接复用
│   │   └── scorer.py          # 信号评分逻辑（从 chat_parser 提取）
│   ├── models/
│   │   └── schemas.py         # Pydantic 数据模型
│   ├── prompts/               # ← 直接复用你的 prompts/ 目录
│   │   ├── intake.md
│   │   ├── signal_reader.md
│   │   ├── message_crafter.md
│   │   ├── strategy_builder.md
│   │   ├── crisis_handler.md
│   │   └── persona_builder.md
│   └── SKILL.md               # ← 直接复用，作为 base system prompt
│
├── supabase/
│   └── migrations/
│       └── 001_init.sql       # 数据库建表 SQL
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 十、第一步：从哪里开始

如果今天就要动手，建议按这个顺序：

**Day 1-2：后端骨架**
1. 用 FastAPI 搭起 `/api/message` 端点
2. 把 SKILL.md + message_crafter.md 组装成 system prompt
3. 接通 Claude API，验证流式输出能跑通
4. 这是整个产品最核心的一条链路

**Day 3-4：前端最小界面**
1. Next.js 搭起来，做一个单页对话窗口
2. 接 `/api/message`，实现：选情境 → 输入描述 → 流式显示生成的消息
3. 加一个"一键复制"按钮
4. 到这步就已经能用了

**Day 5-7：档案系统**
1. 接 Supabase，建表
2. 实现档案创建表单（intake.md 的表单化）
3. 让 `/api/message` 调用时自动注入档案上下文

**Day 8-10：聊天分析**
1. 把 chat_parser.py 封装成 `/api/analyze/upload`
2. 前端做文件上传 + 解析进度
3. 信号评分雷达图

**Day 11-14：打磨 & 上线**
1. 用户认证
2. 用量限制
3. 移动端适配
4. 部署上线

---

## 十一、关键风险 & 应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Claude API 成本失控 | 烧钱 | Sonnet + prompt caching + 前端缓存 + 每日用量限制 |
| Prompt 被逆向 | 知识产权泄露 | 核心 prompt 不在前端出现；评分逻辑代码化 |
| 隐私争议 | 用户信任危机 | 聊天记录仅用于即时分析，不存储原文，只存评分结果 |
| Claude API 国内访问 | 可用性 | 用中转代理或考虑 DeepSeek/通义千问 做国内版备用 |
| "AI 味" 太重 | 用户觉得假 | message_crafter 已有反 AI 味设计，前端加"改写"二次编辑功能 |

---

## 十二、未来扩展方向（验证 PMF 后再做）

- **微信聊天记录一键导入**：对接 WeChatMsg / PyWxDump 的导出格式
- **对话练习模式**：PRD v1.2 计划的功能，基于 crush 档案模拟对话
- **朋友圈文案建议**：基于 social_parser 的分析，建议发什么朋友圈能吸引 crush
- **匿名社区**：追求成功/失败故事分享（脱敏），做增长飞轮
- **MBTI 情话引擎**：PRD 远期计划，16 种人格的定制化情话

---

*落地方案 v0.1 · 追爱军师即将从命令行走向世界*
