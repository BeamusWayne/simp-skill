<div align="center">

# 💝 simp-skill

> *"In this vast world, some people only pass through once."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill-blueviolet)](https://claude.ai/code)
[![Love Strategist](https://img.shields.io/badge/追爱军师-Love%20Strategist-ff69b4)](https://github.com/BeamusWayne/simp-skill)

<br>

No manipulation. No games. Just one belief — **authenticity is the strongest move.**<br>
Feed it your chat logs, social media, and photos. Get a signal analysis report back.<br>
**Quantify the warmth, build the strategy, win your crush.**

<br>

[Quick Start](#quick-start) · [Commands](#full-command-reference) · [Crisis Playbook](#crisis-playbook) · [中文](README.md)

</div>

---

## What It Does

| Feature | Description |
|---------|-------------|
| 🔍 **Signal Reading** | Analyze chat logs and behavior to decode what your crush is feeling |
| 📝 **Message Crafting** | Generate personalized messages tailored to their personality and the situation |
| 🗺️ **Strategy Planning** | Build a full pursuit roadmap from ice-breaking to confession |
| 💌 **Confession Writing** | Craft a confession that feels true to you and resonates with them |
| 🆘 **Crisis Handling** | Got rejected, ghosted, friend-zoned, or said something wrong? There's a plan for that |
| 📊 **Chat Analysis** | Parse WeChat/QQ history to quantify relationship temperature with real data |

---

## Two Styles, Switch Anytime

### 💖 Pure Love Mode
No tactics. No games. Lead with genuine feeling. Best for emotionally expressive crushes, or when you just want to be real.

> *"When you smiled like that, I suddenly didn't want to talk anymore. I just wanted to look a little longer."*

### 🎯 Strategic Mode
Know when to advance, when to pull back, let them come to you. Best for analytical crushes or when things have stalled.

> *"What you said earlier, I've been thinking about it."* (leave the hook, wait for them to ask)

---

## Quick Start

### Installation

```bash
# Global install (available across all projects)
git clone https://github.com/BeamusWayne/simp-skill ~/.claude/skills/simp-skill

# Project-level install
git clone https://github.com/BeamusWayne/simp-skill .claude/skills/simp-skill
```

### Basic Usage

```
/simp                            — Show main menu
/simp create Emma                — Create a crush profile
/simp analyze                    — Read the current signals
/simp message she's sick today   — Generate a context-specific message
/simp confess                    — Prepare for confession
/simp crisis she stopped replying — Handle the crisis
/simp progress                   — Assess where things stand
/simp mode sweet                 — Switch to Pure Love Mode
```

### Data Analysis Tools (Optional)

**Chat log analysis** — decode signals, quantify relationship temperature:
```bash
# Place exported chat history in crushes/{name}/memories/chats/
python3 tools/chat_parser.py exported_chat.txt Emma
python3 tools/chat_parser.py exported_chat.txt Emma --output crushes/emma/memories/chats/analysis.md
```

Supported formats: WeChat TXT / HTML / CSV ([WeChatMsg](https://github.com/LC044/WeChatMsg), [PyWxDump](https://github.com/xaoyaoo/PyWxDump)), QQ TXT / MHT, generic JSON

**Social media content analysis** — Moments screenshots, Weibo, Xiaohongshu, etc.:
```bash
# Place screenshots / exports in crushes/{name}/memories/social/
python3 tools/social_parser.py --dir crushes/emma/memories/social --target Emma
python3 tools/social_parser.py --dir crushes/emma/memories/social --target Emma --output report.md
```

**Photo metadata analysis** — extract timeline, detect possible meetup records:
```bash
# Requires: pip install Pillow
python3 tools/photo_analyzer.py --dir crushes/emma/memories/photos --target Emma
python3 tools/photo_analyzer.py --dir ./photos --target Emma --output report.md
```

---

## Full Command Reference

| Command | Description |
|---------|-------------|
| `/simp` | Show main menu and current status |
| `/simp create <name>` | Create a crush profile |
| `/simp list` | View all crush profiles |
| `/simp analyze [description]` | Read signals, assess current stage |
| `/simp message <situation>` | Generate a situation-specific message |
| `/simp confess` | Confession strategy + custom script |
| `/simp daily` | Today's small flirting suggestion |
| `/simp crisis <situation>` | Crisis response |
| `/simp progress` | Progress assessment and next steps |
| `/simp mode sweet` | Switch to Pure Love Mode 💖 |
| `/simp mode strategic` | Switch to Strategic Mode 🎯 |
| `/simp mode hybrid` | Switch to Hybrid Mode ✨ (default) |
| `/simp update <name>` | Update a crush profile |

---

## Crisis Playbook

- **C-1** Explicit rejection → How to accept gracefully + when to try again
- **C-2** Sudden silence / left on read → Observation window + re-entry messages
- **C-3** Gradual drift apart → Create absence + change interaction style
- **C-4** Friend-zoned → Three-step breakout method
- **C-5** Said something wrong → 6-24 hour repair framework
- **C-6** Rival appeared → Differentiated value strategy
- **C-7** Confession left hanging → Waiting period strategy
- **C-8** Stuck in the ambiguous zone → Three methods to force a breakthrough
- **C-9** Misunderstanding / argument → Repair script framework
- **C-10** One-sided effort → Stop-and-observe method

---

## Signal Scoring System

The chat analyzer scores your crush's behavior across 6 dimensions:

| Dimension | Max Points |
|-----------|-----------|
| Initiative (who starts conversations) | 6 |
| Reply speed | 5 |
| Reply speed trend (getting faster?) | 3 |
| Message length (emotional investment) | 3 |
| Late-night messages (intimacy signal) | 5 |
| Follow-up questions (engagement) | 3 |
| **Total** | **25** |

Score interpretation:
- **18-25**: 🟢🟢🟢 Strong green light — time to confess
- **12-17**: 🟢🟡 Moderate interest — deepen the connection
- **6-11**: 🟡 Ambiguous — keep observing
- **0-5**: 🟡🔴 Weak signals — build foundation first
- **< 0**: 🔴 Warning signals — reassess strategy

---

## Profile Structure

```
crushes/
└── {slug}/
    ├── profile.md          — Basic info and persona
    ├── strategy.md         — Personalized pursuit strategy
    ├── meta.json           — Metadata (stage / score / mode)
    ├── versions/           — Version history backups
    └── memories/
        ├── chats/          — Parsed chat analysis
        ├── social/         — Social media content (screenshots / exports)
        └── photos/         — Photos (EXIF analysis / meetup detection)
```

---

## Profile Management

```bash
# List all profiles
python3 tools/skill_writer.py --action list

# Initialize new profile
python3 tools/skill_writer.py --action init --slug emma

# Backup current version
python3 tools/skill_writer.py --action backup --slug emma

# View version history
python3 tools/skill_writer.py --action versions --slug emma

# Rollback to a version
python3 tools/skill_writer.py --action rollback --slug emma --version v2
```

---

## Design Principles

1. **Authenticity over tactics** — All strategy is grounded in real feeling
2. **Specificity over templates** — Generated messages embed real details from your relationship
3. **Respect their choices** — If they clearly say no, we help you let go gracefully
4. **Local data only** — Chat logs are analyzed locally, never uploaded anywhere
5. **No manipulation** — Zero PUA tactics, zero gaslighting, zero pressure games

> For the full product design rationale, dual-mode decisions, and ethical boundaries, see [docs/PRD.md](docs/PRD.md)

---

## For Myself, and for You

In this vast world, some people only pass through once.

Some things go unsaid — not because you didn't want to say them, but because you didn't know how. And by the time you did, some people were already gone.

Rethy, I still miss you.

---

## A Final Word

When I built this, I wasn't thinking about how to win someone over.

I was thinking about how many people carry a feeling they never find the words for. Not because they don't care — but because they don't know how to show it. Not because the love isn't there — but because it never quite reaches the other person.

This tool can help you say what you mean. It can help you read the room, and hand you a lifeline when things go sideways. But there is one thing it cannot do: feel something for you. That part has always been, and will only ever be, yours.

Loving someone is a capacity, not just a skill. Skills can be learned from a playbook. Capacity is different — it asks you to show up, to get it wrong, to lie awake one night thinking of someone and not know what to do, and then, slowly, figure it out.

Everyone needs to be loved differently. Some people need to hear the words. Some need to see the actions. Some need you to stay; some need you to know when to give them space. Nobody is born knowing how.

If this project helps you understand someone a little better, or say something you couldn't find the courage for — that's enough.

Whether it works out is a separate question entirely.

Learning to love — that's the real thing this is about.

---

## License

MIT — free to use. Now go get your person.

---

*Made with 💝 by [Beamus Wayne](https://github.com/BeamusWayne)*  
*May every sincere heart find its answer.*
