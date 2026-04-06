#!/usr/bin/env python3
"""
simp-skill · Skill Writer
管理心上人档案的创建、列表和版本控制

用法：
  python3 skill_writer.py --action list
  python3 skill_writer.py --action init --slug xiaomei
  python3 skill_writer.py --action backup --slug xiaomei
  python3 skill_writer.py --action rollback --slug xiaomei --version v1
"""

import json
import logging
import shutil
import argparse
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_BASE_DIR = Path("crushes")
SIGNAL_SCORE_MIN = -15
SIGNAL_SCORE_MAX = 25


def init_crush(slug: str, base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """初始化心上人档案目录结构"""
    crush_dir = base_dir / slug

    dirs = [
        crush_dir,
        crush_dir / "memories" / "chats",
        crush_dir / "memories" / "social",
        crush_dir / "memories" / "photos",
        crush_dir / "versions",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    now = datetime.now()

    profile_path = crush_dir / "profile.md"
    if not profile_path.exists():
        profile_path.write_text(
            f"# 心上人档案\n\n"
            f"> 创建于 {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"## 基本信息\n\n"
            f"- 昵称：[待填写]\n"
            f"- 年龄：[待填写]\n"
            f"- 性别：[待填写]\n"
            f"- 职业：[待填写]\n"
            f"- 城市：[待填写]\n\n"
            f"## 性格画像\n\n"
            f"- MBTI：[待填写]\n"
            f"- 星座：[待填写]\n"
            f"- 性格类型：[感性型/理性型/傲娇型/温柔型]\n"
            f"- 主要特征：[待填写]\n\n"
            f"## 关系现状\n\n"
            f"- 认识方式：[待填写]\n"
            f"- 当前关系：[待填写]\n"
            f"- 当前阶段：[破冰期/升温期/暧昧期/表白前]\n"
            f"- 互动频率：[待填写]\n\n"
            f"## 绿灯信号记录\n\n"
            f"[在这里记录观察到的积极信号]\n\n"
            f"## 更新日志\n\n"
            f"- {now.strftime('%Y-%m-%d')}：档案创建\n",
            encoding="utf-8",
        )

    strategy_path = crush_dir / "strategy.md"
    if not strategy_path.exists():
        strategy_path.write_text(
            f"# 追求策略\n\n"
            f"> 由 simp-skill 生成  |  最后更新：{now.strftime('%Y-%m-%d')}\n\n"
            f"## 当前阶段\n\n"
            f"[待评估]\n\n"
            f"## 推荐模式\n\n"
            f"[纯情模式/策略模式/混合模式]\n\n"
            f"## 本阶段重点\n\n"
            f"[待生成]\n\n"
            f"## 近期行动计划\n\n"
            f"[待生成]\n",
            encoding="utf-8",
        )

    meta_path = crush_dir / "meta.json"
    if not meta_path.exists():
        meta = {
            "slug": slug,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "version": "v1",
            "current_stage": "未知",
            "signal_score": None,
            "mode": "hybrid",
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("✅ 档案目录创建成功：%s/", crush_dir)
    logger.info("   ├── profile.md     （心上人基本信息）")
    logger.info("   ├── strategy.md    （追求策略）")
    logger.info("   ├── meta.json      （元数据）")
    logger.info("   └── memories/")
    logger.info("       ├── chats/     （放聊天记录）")
    logger.info("       ├── social/    （放社交媒体截图）")
    logger.info("       └── photos/    （放照片）")
    logger.info("")
    logger.info("下一步：")
    logger.info("  1. 编辑 %s/profile.md 填写心上人信息", crush_dir)
    logger.info("  2. 运行 /simp analyze 开始分析信号")
    logger.info("  3. 把聊天记录放到 %s/memories/chats/ 并运行 chat_parser.py", crush_dir)


def list_crushes(base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """列出所有心上人档案"""
    if not base_dir.exists():
        logger.info("还没有任何心上人档案。运行 /simp create <名字> 开始吧！")
        return

    crushes = [d for d in base_dir.iterdir() if d.is_dir()]
    if not crushes:
        logger.info("还没有任何心上人档案。运行 /simp create <名字> 开始吧！")
        return

    logger.info("💝 心上人档案列表（共 %d 个）", len(crushes))
    logger.info("")
    for crush_dir in sorted(crushes):
        meta_path = crush_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            score = meta.get("signal_score")
            score_str = f"{score}/25" if score is not None else "未评估"
            stage = meta.get("current_stage", "未知")
            updated = meta.get("updated_at", "")[:10]
            logger.info("  📁 %s", crush_dir.name)
            logger.info("     阶段：%s | 信号评分：%s | 最后更新：%s", stage, score_str, updated)
        else:
            logger.info("  📁 %s", crush_dir.name)
        logger.info("")


def backup_crush(slug: str, base_dir: Path = DEFAULT_BASE_DIR) -> str:
    """备份当前版本，返回版本名称；档案不存在时返回空字符串"""
    crush_dir = base_dir / slug
    if not crush_dir.exists():
        logger.error("❌ 档案不存在：%s", slug)
        return ""

    meta_path = crush_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    current_version = meta.get("version", "v1")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_name = f"{current_version}_{timestamp}"

    version_dir = crush_dir / "versions" / version_name
    version_dir.mkdir(parents=True, exist_ok=True)

    for filename in ["profile.md", "strategy.md", "meta.json"]:
        src = crush_dir / filename
        if src.exists():
            shutil.copy2(src, version_dir / filename)

    v_num = int(current_version[1:]) + 1
    new_version = f"v{v_num}"
    updated_meta = {**meta, "version": new_version, "updated_at": datetime.now().isoformat()}
    meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("✅ 已备份版本 %s → %s", current_version, version_name)
    logger.info("   当前版本升级为 %s", new_version)
    return version_name


def rollback_crush(slug: str, version: str, base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """回滚到指定版本"""
    crush_dir = base_dir / slug
    versions_dir = crush_dir / "versions"

    if not versions_dir.exists():
        logger.error("❌ 没有找到版本历史")
        return

    matching = [d for d in versions_dir.iterdir() if d.name.startswith(version)]
    if not matching:
        available = [d.name for d in versions_dir.iterdir()]
        logger.error("❌ 版本 %s 不存在", version)
        logger.error("   可用版本：%s", ", ".join(available))
        return

    backup_crush(slug, base_dir)

    target_dir = sorted(matching)[-1]
    for filename in ["profile.md", "strategy.md", "meta.json"]:
        src = target_dir / filename
        if src.exists():
            shutil.copy2(src, crush_dir / filename)

    logger.info("✅ 已回滚到版本 %s", target_dir.name)


def list_versions(slug: str, base_dir: Path = DEFAULT_BASE_DIR) -> None:
    """列出版本历史"""
    crush_dir = base_dir / slug
    versions_dir = crush_dir / "versions"

    if not versions_dir.exists() or not list(versions_dir.iterdir()):
        logger.info("档案 %s 没有版本历史", slug)
        return

    versions = sorted(versions_dir.iterdir())
    logger.info("📚 %s 的版本历史（共 %d 个版本）", slug, len(versions))
    for v in versions:
        meta_path = v / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stage = meta.get("current_stage", "")
            score = meta.get("signal_score", "")
            logger.info("  - %s  阶段：%s  评分：%s", v.name, stage, score)
        else:
            logger.info("  - %s", v.name)


def update_meta(slug: str, base_dir: Path = DEFAULT_BASE_DIR, **kwargs: object) -> None:
    """更新档案元数据"""
    crush_dir = base_dir / slug
    meta_path = crush_dir / "meta.json"
    if not meta_path.exists():
        logger.error("❌ 档案不存在：%s", slug)
        return

    if "signal_score" in kwargs:
        score = kwargs["signal_score"]
        if score is not None and not (SIGNAL_SCORE_MIN <= int(score) <= SIGNAL_SCORE_MAX):
            logger.error(
                "❌ 信号评分必须在 %d-%d 之间，当前值：%s",
                SIGNAL_SCORE_MIN,
                SIGNAL_SCORE_MAX,
                score,
            )
            return

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    updated_meta = {**meta, **kwargs, "updated_at": datetime.now().isoformat()}
    meta_path.write_text(json.dumps(updated_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("✅ 档案元数据已更新")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="simp-skill · 档案管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["list", "init", "backup", "rollback", "versions", "update-meta"],
        help="操作类型",
    )
    parser.add_argument("--slug", help="心上人档案名（拼音或英文）")
    parser.add_argument("--version", help="版本号（rollback 时使用）")
    parser.add_argument("--stage", help="更新当前阶段")
    parser.add_argument("--score", type=int, help=f"更新信号评分（{SIGNAL_SCORE_MIN}~{SIGNAL_SCORE_MAX}）")
    parser.add_argument("--mode", choices=["sweet", "strategic", "hybrid"], help="更新追求模式")
    parser.add_argument("--base-dir", default="crushes", help="档案根目录（默认：crushes/）")

    args = parser.parse_args()
    base_dir = Path(args.base_dir)

    if args.action == "list":
        list_crushes(base_dir)
    elif args.action == "init":
        if not args.slug:
            logger.error("❌ 请提供 --slug 参数")
            return
        init_crush(args.slug, base_dir)
    elif args.action == "backup":
        if not args.slug:
            logger.error("❌ 请提供 --slug 参数")
            return
        backup_crush(args.slug, base_dir)
    elif args.action == "rollback":
        if not args.slug or not args.version:
            logger.error("❌ 请提供 --slug 和 --version 参数")
            return
        rollback_crush(args.slug, args.version, base_dir)
    elif args.action == "versions":
        if not args.slug:
            logger.error("❌ 请提供 --slug 参数")
            return
        list_versions(args.slug, base_dir)
    elif args.action == "update-meta":
        if not args.slug:
            logger.error("❌ 请提供 --slug 参数")
            return
        kwargs: dict[str, object] = {}
        if args.stage:
            kwargs["current_stage"] = args.stage
        if args.score is not None:
            kwargs["signal_score"] = args.score
        if args.mode:
            kwargs["mode"] = args.mode
        update_meta(args.slug, base_dir, **kwargs)


if __name__ == "__main__":
    main()
