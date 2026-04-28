# Changelog

所有版本的变更记录。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.6.0] - 2026-04-28

### 新增
- **防耗尽机制**：`prompts/daily_coach.md` 新增 Step 0「防耗尽预检」——根据 `events.jsonl` 最近 7 天的调用频率、焦虑词密度、单日重复次数、评分趋势、长期低位徘徊等 5 类信号判断，命中高风险时短路返回「劝歇」分支，要求用户停一停而不是给出更多追求建议。在用户坚持要继续时礼貌坚持一次再让步并加警告
- `prompts/progress_tracker.md` 风险表新增「用户耗尽风险」一行，并在风险触发时输出预防性提示，引导用户运行 `/simp quit` 重新评估
- `SKILL.md` 运行规则新增第 8 条「防耗尽优先」，将该机制提升为强制运行规则

### 改进
- `CHANGELOG.md`：补回此前漏写的 v1.4.0、v1.5.0 条目（Mem-Sys Phase 2+3、进度可视化、MBTI 系统）
- `README.md` / `README_EN.md`：功能表新增「MBTI 分析」「进度追踪」两行；指令列表新增 `/simp mbti`；档案结构图同步到新的 Mem-Sys 结构（`state.md` / `events.jsonl` / `snapshots/`）；新增「记忆系统工具」CLI 速查段落，并链接 `docs/MEM-SYS.md`

---

## [1.5.0] - 2026-04-24

### 新增
- `prompts/mbti_analyzer.md`：MBTI 分析模块，对应 `/simp mbti` 指令。三段式输出：① 行为维度推断（E/I、N/S、T/F、J/P，每个维度给证据 + 置信度）② 16型专属追求策略（核心需求、推进节奏、雷区、试探方式）③ 双方兼容性分析（共振点、张力点、给到双方的建议）
- `SKILL.md`：指令系统与主菜单新增 `/simp mbti [描述/已知类型]` 入口

### 改进
- `prompts/signal_reader.md` / `prompts/strategy_builder.md`：集成 MBTI 校正层。已知 MBTI 时，信号解读和策略生成自动套用对应 16 型偏好（例如 INTJ 不喜欢黏腻话术，ENFP 需要更高频的情绪共鸣）

---

## [1.4.0] - 2026-04-22

### 新增
- `tools/memory.py`：记忆系统核心模块（Mem-Sys Phase 2）。CLI 支持 `append` / `events` / `context` / `rebuild` / `snapshot` / `timeline`；Python API 暴露 `append_event` / `get_recent_events` / `load_context` / `update_state` / `take_snapshot` / `rebuild_state_from_events`
- `tests/test_memory.py`：记忆系统测试套件
- 档案新结构：每个 `crushes/{slug}/` 自动生成 `state.md`（动态层快照）、`events.jsonl`（不可变事件流）、`snapshots/`（按日存档）
- `SKILL.md`：新增「记忆操作协议」章节，定义每条指令的读写规范（Mem-Sys Phase 3）

### 改进
- `prompts/progress_tracker.md`：进度可视化升级。输出新增阶段进度条（纯文本图示）和热度趋势对比，从 `state.md` + `events.jsonl` 读取历史数据，不再每次重新推断
- `tools/skill_writer.py`：`init_crush()` 同步创建 state.md / events.jsonl / snapshots/，`meta.json` schema 扩展（新增 `nickname`、`event_count`、`last_snapshot`）
- `docs/PRD.md`：补 v1.4 / v1.5 的 Roadmap 状态

---

## [1.3.0] - 2026-04-16

### 新增
- `prompts/message_crafter.md`：加入「AI味检测」模块——七种 AI 味特征识别（句式过工整、用词太正确、缺语气词、四字堆砌、开头模式固定、在讲感情而非某件事、逻辑太完整），生成消息后自动运行，命中时给出具体改写方向而非替用户重写
- `prompts/crisis_handler.md`：新增危机场景 C-11「对方开始了新感情」——含72小时情绪处理期、三问式重新评估、路线A（长线等待）和路线B（适当拉开距离）分支，以及与 C-6（竞争对手出现）的场景区分

### 改进
- `prompts/message_crafter.md`：「消息质检清单」第一条更新为 AI 味检测通过标志，与新模块对齐
- `prompts/crisis_handler.md`：危机类型识别表新增 C-11 条目及触发关键词
- `docs/PRD.md`：Roadmap 更新——将 v1.3 已完成项目标注为已发布，补充「待评估的新方向」一节（约会策划、朋友圈建议、礼物建议、成功后模块、防耗尽检测、反向视角、每周复盘）
- `README.md` / `README_EN.md`：危机处理覆盖范围同步更新，增加 C-11 条目

---

## [1.2.0] - 2026-04-09

### 新增
- `prompts/daily_coach.md`：补全 `/simp daily` 对应的今日建议模块（五种建议类型、周末/工作日差异化、今日心态提醒）
- `prompts/progress_tracker.md`：补全 `/simp progress` 对应的进度追踪模块（阶段评估、热度分历史趋势、里程碑追踪、三条具体行动）
- `prompts/quit_judge.md`：新增放弃判断器 `/simp quit`，帮用户区分真心与执念，输出四种结论（继续 / 调整策略 / 先暂停 / 认真考虑放下）

### 改进
- `SKILL.md`：指令系统新增 `/simp quit`，主菜单新增今日建议和放弃判断器入口
- `README.md` / `README_EN.md`：功能表和指令列表同步更新

---

## [1.1.0] - 2026-04-06

### 新增
- `prompts/confess.md`：补全 `/simp confess` 对应的表白模块 prompt（含时机评估、方式选择、四层表白词结构、表白后预案）
- `tests/test_skill_writer.py`：`skill_writer.py` 的 pytest 测试套件，覆盖全部函数（20 个用例）
- `conftest.py`：pytest 路径配置

### 修复
- `prompts/signal_reader.md`：重构信号评分表，使三个维度满分合计恰好 25 分（原表最高可达 46 分，与 PRD 及 meta.json 约定不一致）
- `tools/skill_writer.py`：`list_crushes` 中评分为 0 时错误显示"未评估"的 bug

### 改进
- `tools/skill_writer.py`：全函数添加类型注解，符合 PEP 8 规范
- `tools/skill_writer.py`：移除 `global BASE_DIR`，改为函数参数传递
- `tools/skill_writer.py`：`print()` 全部替换为 `logging`
- `tools/skill_writer.py`：`update_meta` 新增 `signal_score` 范围校验（-15 ~ 25），拒绝写入无效值

---

## [1.0.0] - 2026-04-05

### 新增
- `SKILL.md`：追爱军师主技能文件，含三模式系统、五阶段追求路线图、完整指令集
- `prompts/intake.md`：心上人档案创建流程
- `prompts/signal_reader.md`：信号解读系统（25 分评分、四维度分析）
- `prompts/message_crafter.md`：情话与消息生成（8 大情境模板）
- `prompts/crisis_handler.md`：危机处理系统（C-1 至 C-10 共 10 种场景）
- `prompts/strategy_builder.md`：个性化追求策略生成
- `prompts/persona_builder.md`：心上人性格建模
- `tools/skill_writer.py`：档案管理工具（创建、备份、回滚、版本历史）
- `tools/chat_parser.py`：微信/QQ 聊天记录解析器（支持多格式）
- `tools/social_parser.py`：社交媒体内容分析
- `tools/photo_analyzer.py`：照片元数据分析（EXIF/约会检测）
- `docs/PRD.md`：产品设计文档（双模式设计决策、伦理边界、Roadmap）
