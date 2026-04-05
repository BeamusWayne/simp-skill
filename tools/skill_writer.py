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
import shutil
import argparse
from datetime import datetime
from pathlib import Path


BASE_DIR = Path("crushes")


def init_crush(slug: str) -> None:
    """初始化心上人档案目录结构"""
    crush_dir = BASE_DIR / slug

    dirs = [
        crush_dir,
        crush_dir / "memories" / "chats",
        crush_dir / "memories" / "social",
        crush_dir / "memories" / "photos",
        crush_dir / "versions",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 创建初始 profile.md 模板
    profile_path = crush_dir / "profile.md"
    if not profile_path.exists():
        profile_path.write_text(
            f"# 心上人档案\n\n"
            f"> 创建于 {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
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
            f"- {datetime.now().strftime('%Y-%m-%d')}：档案创建\n",
            encoding="utf-8"
        )

    # 创建初始 strategy.md 模板
    strategy_path = crush_dir / "strategy.md"
    if not strategy_path.exists():
        strategy_path.write_text(
            f"# 追求策略\n\n"
            f"> 由 simp-skill 生成  |  最后更新：{datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"## 当前阶段\n\n"
            f"[待评估]\n\n"
            f"## 推荐模式\n\n"
            f"[纯情模式/策略模式/混合模式]\n\n"
            f"## 本阶段重点\n\n"
            f"[待生成]\n\n"
            f"## 近期行动计划\n\n"
            f"[待生成]\n",
            encoding="utf-8"
        )

    # 创建 meta.json
    meta_path = crush_dir / "meta.json"
    if not meta_path.exists():
        meta = {
            "slug": slug,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "version": "v1",
            "current_stage": "未知",
            "signal_score": None,
            "mode": "hybrid",
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 档案目录创建成功：{crush_dir}/")
    print(f"   ├── profile.md     （心上人基本信息）")
    print(f"   ├── strategy.md    （追求策略）")
    print(f"   ├── meta.json      （元数据）")
    print(f"   └── memories/")
    print(f"       ├── chats/     （放聊天记录）")
    print(f"       ├── social/    （放社交媒体截图）")
    print(f"       └── photos/    （放照片）")
    print()
    print(f"下一步：")
    print(f"  1. 编辑 {crush_dir}/profile.md 填写心上人信息")
    print(f"  2. 运行 /simp analyze 开始分析信号")
    print(f"  3. 把聊天记录放到 {crush_dir}/memories/chats/ 并运行 chat_parser.py")


def list_crushes() -> None:
    """列出所有心上人档案"""
    if not BASE_DIR.exists():
        print("还没有任何心上人档案。运行 /simp create <名字> 开始吧！")
        return

    crushes = [d for d in BASE_DIR.iterdir() if d.is_dir()]
    if not crushes:
        print("还没有任何心上人档案。运行 /simp create <名字> 开始吧！")
        return

    print(f"💝 心上人档案列表（共 {len(crushes)} 个）")
    print()
    for crush_dir in sorted(crushes):
        meta_path = crush_dir / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            score = meta.get("signal_score")
            score_str = f"  信号评分：{score}/25" if score else "  信号评分：未评估"
            stage = meta.get("current_stage", "未知")
            updated = meta.get("updated_at", "")[:10]
            print(f"  📁 {crush_dir.name}")
            print(f"     阶段：{stage} | {score_str} | 最后更新：{updated}")
        else:
            print(f"  📁 {crush_dir.name}")
        print()


def backup_crush(slug: str) -> str:
    """备份当前版本"""
    crush_dir = BASE_DIR / slug
    if not crush_dir.exists():
        print(f"❌ 档案不存在：{slug}")
        return ""

    meta_path = crush_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    current_version = meta.get("version", "v1")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_name = f"{current_version}_{timestamp}"

    version_dir = crush_dir / "versions" / version_name
    version_dir.mkdir(parents=True, exist_ok=True)

    # 备份核心文件
    for filename in ["profile.md", "strategy.md", "meta.json"]:
        src = crush_dir / filename
        if src.exists():
            shutil.copy2(src, version_dir / filename)

    # 升级版本号
    v_num = int(current_version[1:]) + 1
    new_version = f"v{v_num}"
    meta["version"] = new_version
    meta["updated_at"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 已备份版本 {current_version} → {version_name}")
    print(f"   当前版本升级为 {new_version}")
    return version_name


def rollback_crush(slug: str, version: str) -> None:
    """回滚到指定版本"""
    crush_dir = BASE_DIR / slug
    versions_dir = crush_dir / "versions"

    if not versions_dir.exists():
        print(f"❌ 没有找到版本历史")
        return

    # 找到目标版本
    matching = [d for d in versions_dir.iterdir() if d.name.startswith(version)]
    if not matching:
        available = [d.name for d in versions_dir.iterdir()]
        print(f"❌ 版本 {version} 不存在")
        print(f"   可用版本：{', '.join(available)}")
        return

    # 先备份当前版本
    backup_crush(slug)

    # 恢复目标版本
    target_dir = sorted(matching)[-1]  # 取最新的那个
    for filename in ["profile.md", "strategy.md", "meta.json"]:
        src = target_dir / filename
        if src.exists():
            shutil.copy2(src, crush_dir / filename)

    print(f"✅ 已回滚到版本 {target_dir.name}")


def list_versions(slug: str) -> None:
    """列出版本历史"""
    crush_dir = BASE_DIR / slug
    versions_dir = crush_dir / "versions"

    if not versions_dir.exists() or not list(versions_dir.iterdir()):
        print(f"档案 {slug} 没有版本历史")
        return

    versions = sorted(versions_dir.iterdir())
    print(f"📚 {slug} 的版本历史（共 {len(versions)} 个版本）")
    for v in versions:
        meta_path = v / "meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stage = meta.get("current_stage", "")
            score = meta.get("signal_score", "")
            print(f"  - {v.name}  阶段：{stage}  评分：{score}")
        else:
            print(f"  - {v.name}")


def update_meta(slug: str, **kwargs) -> None:
    """更新档案元数据"""
    crush_dir = BASE_DIR / slug
    meta_path = crush_dir / "meta.json"
    if not meta_path.exists():
        print(f"❌ 档案不存在：{slug}")
        return

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.update(kwargs)
    meta["updated_at"] = datetime.now().isoformat()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 档案元数据已更新")


def main():
    parser = argparse.ArgumentParser(
        description="simp-skill · 档案管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--action", required=True,
                        choices=["list", "init", "backup", "rollback", "versions", "update-meta"],
                        help="操作类型")
    parser.add_argument("--slug", help="心上人档案名（拼音或英文）")
    parser.add_argument("--version", help="版本号（rollback 时使用）")
    parser.add_argument("--stage", help="更新当前阶段")
    parser.add_argument("--score", type=int, help="更新信号评分")
    parser.add_argument("--mode", choices=["sweet", "strategic", "hybrid"], help="更新追求模式")
    parser.add_argument("--base-dir", default="crushes", help="档案根目录（默认：crushes/）")

    args = parser.parse_args()

    global BASE_DIR
    BASE_DIR = Path(args.base_dir)

    if args.action == "list":
        list_crushes()
    elif args.action == "init":
        if not args.slug:
            print("❌ 请提供 --slug 参数")
            return
        init_crush(args.slug)
    elif args.action == "backup":
        if not args.slug:
            print("❌ 请提供 --slug 参数")
            return
        backup_crush(args.slug)
    elif args.action == "rollback":
        if not args.slug or not args.version:
            print("❌ 请提供 --slug 和 --version 参数")
            return
        rollback_crush(args.slug, args.version)
    elif args.action == "versions":
        if not args.slug:
            print("❌ 请提供 --slug 参数")
            return
        list_versions(args.slug)
    elif args.action == "update-meta":
        if not args.slug:
            print("❌ 请提供 --slug 参数")
            return
        kwargs = {}
        if args.stage:
            kwargs["current_stage"] = args.stage
        if args.score is not None:
            kwargs["signal_score"] = args.score
        if args.mode:
            kwargs["mode"] = args.mode
        update_meta(args.slug, **kwargs)


if __name__ == "__main__":
    main()
