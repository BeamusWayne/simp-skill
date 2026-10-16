# simp-skill · 追爱军师

帮助你理解恋爱语境、写出像自己的消息，并回顾真实互动。当前是 **v2 P0–P3 开发版**：取消感情评分和固定追求阶段，保留具体证据、相反解释与可修正的判断。尚未作为 v2.0 正式发布。

## 使用

把整个仓库目录放入宿主的技能目录或通过宿主支持的 GitHub 技能安装方式安装，保留 SKILL.md、prompts、tools、docs 的相对位置。原生注册方式依宿主而异；`/simp` 是兼容表达，不能保证所有宿主都自动注册斜杠命令。当前已测试 Python 工具，不声明已完成各宿主安装测试。

原仓库的 Claude Code 安装位置仍保留为兼容说明：全局目录 `~/.claude/skills/simp-skill` 或项目目录 `.claude/skills/simp-skill`。验证本开发版本时应选择 `codex/simp-v2-p0-p3` 分支，不要把 main 的旧版与新工具混合。SKILL.md 保留原宿主的 `user-invocable: true` 字段；其他宿主是否接受扩展元数据须分别验证。

直接说“这句话怎么回更像我”“帮我看看这段聊天”，或使用 `/simp analyze`、`message`、`confess`、`progress`、`daily`、`crisis`、`quit`、`timeline`。简单改写无需建档。`mbti` 仅按显式请求讨论用户自述，不自动判型或算匹配分。模式 sweet/strategic/hybrid 仅改变语气。

## 工具快速开始

Python 3.12，基础解析和记忆使用标准库；照片元数据需要 Pillow。

```sh
python -m venv .venv
python -m pip install -r requirements-dev.txt
python tools/chat_parser.py tests/fixtures/v2/direct.json 小美 --json
python tools/skill_writer.py --action init --slug demo --base-dir ./crushes
python tools/chat_parser.py tests/fixtures/v2/direct.json 小美 --track-time --slug demo --base-dir ./crushes --json
python tools/time_tracker.py analyze demo --reply --base-dir ./crushes
python tools/memory.py context demo --base-dir ./crushes
python -m pytest -q
```

先激活创建的虚拟环境，或把上面的 python 换成对应虚拟环境解释器。导入只在显式提供 --track-time 和已有档案时写记忆。名字和路径含空格时按 shell 语法加引号。聊天需确定账号映射，示例文件已提供合成账号。

数据和完整命令见 [聊天格式](docs/CHAT-FORMAT.md)、[记忆规范](docs/MEM-SYS.md)、[迁移与恢复](docs/V2-MIGRATION.md)。旧档案默认只预览，不自动转换；--score/--stage 已废弃。--golden 保留为活跃时段别名。

## 数据与验证范围

工具本身在本地读取文件并输出结果，不调用模型 API。把材料交给宿主模型分析时，数据路径和保存政策取决于该宿主/模型，不能把“本地解析”理解为“全部分析离线”。crushes、评测运行日志和个人材料不应进入版本库；仓库夹具均为合成数据。

P0–P3 包括单元、集成、CLI、迁移中断与完整恢复测试。行为案例与协议见 [evals](evals/README.md)。P4 的持续风格学习和独立 review 工作流、P5 的完整 216 次模型对照及发布验证尚未完成。当前基础表达可参考本次用户样本，实际行动和回应已能分开记录。

旧版历史与基线：`71f64215f50aeb5b619fb34fa44adb9247c85770`。许可见 [LICENSE](LICENSE)。
