# Changelog

所有版本的变更记录。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

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
