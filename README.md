<div align="center">

# 💝 simp-skill

> *"茫茫人海，一旦错过就不再。"*

> *simp，是那个敢于真心喜欢一个人的人。这里教的，是把真心说出口的能力。*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![追爱军师](https://img.shields.io/badge/追爱军师-Love%20Strategist-ff69b4)](https://github.com/BeamusWayne/simp-skill)

<br>

不教套路，不玩 PUA，只相信一件事——**真心，是最强的攻略。**<br>
提供聊天记录、社交媒体截图、照片，生成信号分析报告。<br>
**量化感情温度，定制追求策略，把心上人追到手。**

<br>

[快速开始](#快速开始) · [指令列表](#指令完整列表) · [危机处理](#危机处理覆盖范围) · [更新日志](CHANGELOG.md) · [English](README_EN.md)

</div>

---

## 它能帮你做什么


| 功能           | 描述                      |
| ------------ | ----------------------- |
| 🔍 **信号解读**  | 帮你分析聊天记录，判断对方发出了什么信号    |
| 📝 **情话生成**  | 根据对象性格和当前情境，生成专属情话      |
| 🗺️ **策略规划** | 制定从破冰到表白的完整追求路线图        |
| 💌 **表白定制**  | 帮你准备让对方难忘的表白词           |
| 🆘 **危机处理**  | 被拒/冷落/翻车/友谊区，每种危机都有应对方案 |
| 📊 **聊天分析**  | 自动分析微信/QQ聊天记录，量化感情温度    |
| 🍃 **放弃判断**  | 帮你看清是真心还是执念，该继续还是该放下   |


---

## 两种风格，随时切换

### 💖 纯情模式

不算计，不套路，用真实的情感打动对方。适合感性的心上人，或者你就是想真诚地表达自己。

> *"你笑的时候，我突然就不想说话了，只想多看一会儿。"*

### 🎯 策略模式

懂得何时推进、何时留白，让对方主动靠近。适合理性的心上人，或者暧昧陷入僵局。

> *"你刚才说的那件事，让我想了很久。"（留悬念，等对方追问）*

---

## 快速开始

### 安装

```bash
# 全局安装（所有项目可用）
git clone https://github.com/BeamusWayne/simp-skill ~/.claude/skills/simp-skill

# 或项目级安装
git clone https://github.com/BeamusWayne/simp-skill .claude/skills/simp-skill
```

### 基本使用

```
/simp                          — 显示主菜单
/simp create 小美               — 建立心上人档案，开始追求旅程
/simp analyze                  — 解读最近的信号
/simp message 她今天生病了        — 生成情境专属消息
/simp confess                  — 准备表白
/simp crisis 突然不回我消息了      — 危机处理
/simp progress                 — 评估当前进度
/simp mode sweet               — 切换到纯情模式
```

### 使用数据分析工具（可选）

**聊天记录分析**（解读信号、量化感情温度）：

```bash
# 把微信/QQ聊天记录导出后放到 crushes/{名字}/memories/chats/
python3 tools/chat_parser.py 导出的聊天记录.txt 小美
python3 tools/chat_parser.py 导出的聊天记录.txt 小美 --output crushes/xiaomei/memories/chats/analysis.md
```

支持格式：微信 TXT / HTML / CSV（[WeChatMsg](https://github.com/LC044/WeChatMsg)、[PyWxDump](https://github.com/xaoyaoo/PyWxDump)）、QQ TXT / MHT、通用 JSON

**社交媒体内容分析**（朋友圈截图、微博、小红书等）：

```bash
# 把截图/导出文件放到 crushes/{名字}/memories/social/
python3 tools/social_parser.py --dir crushes/xiaomei/memories/social --target 小美
python3 tools/social_parser.py --dir crushes/xiaomei/memories/social --target 小美 --output report.md
```

**照片元数据分析**（提取拍摄时间线，检测可能的约会记录）：

```bash
# 需要先安装：pip install Pillow
python3 tools/photo_analyzer.py --dir crushes/xiaomei/memories/photos --target 小美
python3 tools/photo_analyzer.py --dir ./photos --target 小美 --output report.md
```

---

## 指令完整列表


| 指令                     | 说明            |
| ---------------------- | ------------- |
| `/simp`                | 显示主菜单和当前状态    |
| `/simp create <名字>`    | 建立心上人档案       |
| `/simp list`           | 查看所有心上人档案     |
| `/simp analyze [描述]`   | 解读信号，判断当前阶段   |
| `/simp message <情境>`   | 生成情境专属消息/情话   |
| `/simp confess`        | 表白策略 + 表白词定制  |
| `/simp daily`          | 今日撩人小建议       |
| `/simp crisis <情况>`    | 危机处理          |
| `/simp progress`       | 进度评估与下一步建议    |
| `/simp quit`           | 放弃判断器         |
| `/simp mode sweet`     | 切换到纯情模式 💖    |
| `/simp mode strategic` | 切换到策略模式 🎯    |
| `/simp mode hybrid`    | 切换到混合模式 ✨（默认） |
| `/simp update <名字>`    | 更新心上人档案       |


---

## 危机处理覆盖范围

- **C-1** 明确被拒 → 如何优雅接受 + 何时可以重启
- **C-2** 突然冷落/已读不回 → 观察期 + 重新出现话术
- **C-3** 渐渐疏远 → 制造缺席感 + 改变互动方式
- **C-4** 进入友谊区 → 三步破围法
- **C-5** 说错话翻车 → 6-24小时内修复方案
- **C-6** 竞争对手出现 → 差异化价值策略
- **C-7** 表白被挂起 → 等待期策略
- **C-8** 暧昧期停滞 → 破局三法
- **C-9** 误会/争吵 → 修复话术框架
- **C-10** 单方面付出 → 停止主动观察法
- **C-11** 对方开始了新感情 → 72小时情绪处理 + 两条路线选择

---

## 档案结构

```
crushes/
└── {slug}/
    ├── profile.md          — 心上人基本信息与画像
    ├── strategy.md         — 个性化追求策略
    ├── meta.json           — 档案元数据（阶段/评分/模式）
    ├── versions/           — 历史版本备份
    └── memories/
        ├── chats/          — 聊天记录分析结果
        ├── social/         — 社交媒体内容（截图/导出）
        └── photos/         — 照片（EXIF分析/约会检测）
```

---

## 档案管理工具

```bash
# 列出所有档案
python3 tools/skill_writer.py --action list

# 初始化新档案
python3 tools/skill_writer.py --action init --slug xiaomei

# 备份当前版本
python3 tools/skill_writer.py --action backup --slug xiaomei

# 查看版本历史
python3 tools/skill_writer.py --action versions --slug xiaomei

# 回滚到某个版本
python3 tools/skill_writer.py --action rollback --slug xiaomei --version v2
```

---

## 设计原则

1. **真心优于套路** — 所有策略的底层是真实的感情
2. **专属感优于模板** — 生成的情话嵌入你们之间真实的细节
3. **尊重对方意愿** — 如果对方明确拒绝，帮助优雅放手，不强行继续
4. **数据本地化** — 所有分析在本地进行，聊天记录不上传任何服务器
5. **不教 PUA** — 任何操控类、让对方不安全感的话术，一律不用

> 完整的产品设计逻辑、双模式设计决策、伦理边界定义，见 [docs/PRD.md](docs/PRD.md)

---

## 写给自己，也献给你

茫茫人海，一旦错过就不再。

有些话，不是不想说，是不知道怎么说。等到知道了，有些人已经不在了。

Rethy，我还是很想你。

---

## 写在最后

写这个的时候，我想的不是怎么追到一个人。

我想的是，有多少人心里明明装着一个人，却不知道怎么开口。不是不在乎，是不会表达。不是不爱，是爱的方式对方感受不到。

这个工具能帮你说出你想说的话，能帮你看懂一些信号，能在你翻车的时候递给你一个台阶。但有一件事它做不到：替你喜欢那个人。那件事，从来都只能是你。

爱人是一种能力，但不只是一种技能。技能可以靠方法复刻，能力不一样——它需要你真的进场，真的犯错，真的在某个夜里想起一个人，不知道该怎么办，然后慢慢学会。

每个人希望被爱的方式不一样。有人需要你说出来，有人需要你做到。有人需要你在，有人需要你懂得走开。这件事没有人天生就会。

如果这个项目能帮你多了解一个人一点，帮你多表达一点——那就够了。

追没追到，是另一回事。学着去爱，才是这件事真正的结果。

---

## 许可证

MIT License — 自由使用，记得去追你的心上人。

---

*Made with 💝 by [Beamus Wayne](https://github.com/BeamusWayne)*  
*愿每一份真心都有回应。*