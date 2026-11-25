#!/usr/bin/env python3
"""破万卷：无第三方依赖的本地初始化、归档、周计算与输出校验工具。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

SCHEMA_VERSION = 1
DAILY_LIMIT = 400
DAILY_SECTIONS = ("最值得知道", "与你何干", "留给你判断")

# 初始化时写入的空白知识地图：状态固定为“待确认”，访谈是可选步骤。
KNOWLEDGE_MAP_TEMPLATE = """# 知识地图

- 状态：待确认
- 版本：v0.1
- 创建日期：{created}
- 最后确认：未确认
- 本地时区：{timezone}
- 修订与回滚：修改前复制版本，并在 `profile/revisions.jsonl` 记录旧内容、新内容、来源、确认与回滚指向。

## 阅读边界总览

| 区域 | 当前边界 | 下一小步 | 条目ID |
|---|---|---|---|
| 已掌握 |  |  |  |
| 正在学 |  |  |  |
| 明确不懂 / 暂不碰 |  |  |  |

## 事实（可独立核对）

| ID | 事实 | 来源 | 日期 | 置信度 | 最后确认 |
|---|---|---|---|---|---|
| F-001 |  |  |  | 高/中/低 |  |

## 用户自述（目标、经验、偏好与红线）

| ID | 分类 | 自述 | 来源 | 日期 | 置信度 | 最后确认 |
|---|---|---|---|---|---|---|
| U-001 | 已掌握/正在学/暂不碰/90天目标/瓶颈/信息源/隐私红线 |  |  |  | 高/中/低 |  |

## 90天目标与现实约束

| 目标ID | 结果与验收方式 | 当前瓶颈 | 每周亲读预算 | 关联自述ID |
|---|---|---|---|---|
| G-001 |  |  |  |  |

## 主要信息源与可信边界

| 来源 | 用途 | 是否可作一手证据 | 关联区域 | 备注 |
|---|---|---|---|---|
|  |  | 是/否/需核查 |  |  |

## Agent 假设（只能放待确认区）

| ID | 假设 | 依据 | 来源 | 日期 | 置信度 | 待用户确认的问题 |
|---|---|---|---|---|---|---|
| A-001 |  |  |  |  | 低/中 |  |

## 待确认区

- [ ] 条目ID：待确认内容；来源；日期；需要用户判断什么。

## 隐私红线

- 禁止读取：
- 禁止引用或公开：
- 禁止推断：
- 可读取但必须留在本地：

## 修订记录

| 日期 | 版本 | 修改摘要 | 用户确认 | 回滚指向 |
|---|---|---|---|---|
|  |  |  |  |  |
"""


def emit(data: dict) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def root_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def parse_day(value: str | None, root: Path | None = None) -> date:
    if value:
        return date.fromisoformat(value)
    tz_name = "local"
    if root:
        config_file = root / "config.json"
        if config_file.exists():
            try:
                tz_name = json.loads(config_file.read_text(encoding="utf-8")).get("timezone", "local")
            except (json.JSONDecodeError, OSError):
                pass
    if tz_name != "local" and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return datetime.now().astimezone().date()


def write_if_absent(path: Path, content: str = "") -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def command_init(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    created = []
    if not root.exists():
        root.mkdir(parents=True)
        created.append(str(root))
    for name in (
        "profile", "inbox", "cards", "notes", "daily", "weekly", "memory", "state", "runtime"
    ):
        path = root / name
        if not path.exists():
            path.mkdir(parents=True)
            created.append(str(path) + "/")

    files = {
        "config.json": json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "display_name": "破万卷",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "timezone": args.timezone,
                "week_convention": "ISO-8601",
                "daily_reminder": "22:00",
                "weekly_review": "Sunday 22:15",
                "profile_confirmed": False,
                "profile_confirmed_at": None,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        "profile/self.md": "# 我是谁\n\n> 仅记录用户确认的事实、角色与现实约束，并注明来源和日期。\n",
        "profile/goals.md": "# 目标与长期主题\n\n## 未来90天\n\n## 长期主题\n",
        "profile/preferences.md": "# 已确认偏好\n\n> 保存可观察、可评测的规则，不保存空泛人格标签。\n",
        "profile/knowledge-map.md": KNOWLEDGE_MAP_TEMPLATE.format(
            created=datetime.now().astimezone().date().isoformat(),
            timezone=args.timezone,
        ),
        "profile/evaluation.jsonl": "",
        "profile/revisions.jsonl": "",
        "state/ingest-log.jsonl": "",
    }
    for relative, content in files.items():
        path = root / relative
        if write_if_absent(path, content):
            created.append(str(path))

    emit({
        "ok": True,
        "root": str(root),
        "created": created,
        "already_present": not created,
        "next": "知识地图已建立，状态为“待确认”；访谈是可选步骤，用户明确要求时再进行。经用户确认后执行 confirm-profile。",
    })
    return 0


def command_confirm_profile(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    config_file = root / "config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"找不到 {config_file}，请先执行 init。")
    config = json.loads(config_file.read_text(encoding="utf-8"))
    config["profile_confirmed"] = True
    config["profile_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    emit({"ok": True, "profile_confirmed": True, "config": str(config_file)})
    return 0


def command_ingest(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    if not (root / "config.json").exists():
        raise FileNotFoundError("数据目录尚未初始化，请先执行 init。")
    day = parse_day(args.date)
    if args.file:
        raw = Path(args.file).expanduser().resolve().read_text(encoding="utf-8-sig")
        origin = str(Path(args.file).expanduser().resolve())
    else:
        raw = args.text
        origin = "command-line text"
    if not raw.strip():
        raise ValueError("原始记录为空，未写入。")

    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    log_file = root / "state" / "ingest-log.jsonl"
    existing = []
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    existing.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    if any(item.get("sha256") == digest for item in existing):
        emit({"ok": True, "duplicate": True, "sha256": digest, "message": "相同内容已归档，本次跳过。"})
        return 0

    inbox = root / "inbox" / f"{day.isoformat()}.md"
    with inbox.open("a", encoding="utf-8", newline="\n") as handle:
        if inbox.exists() and inbox.stat().st_size > 0:
            handle.write("\n\n---\n\n")
        handle.write(raw.rstrip() + "\n")
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "date": day.isoformat(),
        "sha256": digest,
        "bytes": len(raw.encode("utf-8")),
        "origin": origin,
        "path": str(inbox),
    }
    with log_file.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    emit({"ok": True, "duplicate": False, **event})
    return 0


def normalize_url(value: str) -> str:
    """统一协议、域名大小写、首尾空白与锚点；路径和查询参数原样保留。"""
    text = value.strip()
    try:
        parts = urlsplit(text)
        path = "" if parts.path == "/" else parts.path
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
    except ValueError:
        return text


def normalize_path(value: str) -> str:
    """按 Windows 习惯比较附件路径：不区分大小写，统一分隔符。"""
    return value.strip().replace("\\", "/").rstrip("/").lower()


def item_key(item: dict) -> tuple[str, str] | None:
    """返回（键类型, 规范化键）。优先用链接，其次文字，最后附件路径；都没有则返回 None。"""
    if str(item.get("url", "")).strip():
        return "url", normalize_url(str(item["url"]))
    if str(item.get("text", "")).strip():
        compact = re.sub(r"\s+", "", str(item["text"]))
        return "text", hashlib.sha256(compact.encode("utf-8")).hexdigest()
    if str(item.get("path", "")).strip():
        return "path", normalize_path(str(item["path"]))
    return None


def command_dedupe_items(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    log_file = None
    day = None
    if args.root:
        log_file = root_path(args.root) / "state" / "item-log.jsonl"
        day = parse_day(None, root_path(args.root))
    try:
        items = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {number} 行不是合法 JSON：{exc.msg}") from exc
            if not isinstance(item, dict) or not str(item.get("id", "")).strip():
                raise ValueError(f"第 {number} 行缺少非空的 id。")
            items.append(item)

        seen: dict[tuple[str | None, str | None], str] = {}
        if log_file and log_file.exists():
            for line in log_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                seen[(record.get("key_kind"), record.get("key"))] = record.get("id")

        unique_ids, duplicates, new_records = [], [], []
        recorded_at = datetime.now(timezone.utc).isoformat()
        for item in items:
            key = item_key(item)
            if key is None:  # 没有可比较的内容：保留，不参与去重
                unique_ids.append(item["id"])
                continue
            if key in seen:
                duplicates.append({"id": item["id"], "first_id": seen[key], "key_kind": key[0]})
                continue
            seen[key] = item["id"]
            unique_ids.append(item["id"])
            new_records.append({
                "key_kind": key[0],
                "key": key[1],
                "id": item["id"],
                "date": day.isoformat() if day else None,
                "recorded_at": recorded_at,
            })

        committed = False
        if args.commit and log_file and new_records:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("a", encoding="utf-8", newline="\n") as handle:
                for record in new_records:
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            committed = True
    except (OSError, ValueError) as exc:
        emit({"ok": False, "error": str(exc), "file": str(path)})
        return 1

    emit({
        "ok": True,
        "file": str(path),
        "total": len(items),
        "unique_count": len(unique_ids),
        "duplicate_count": len(duplicates),
        "unique_ids": unique_ids,
        "duplicates": duplicates,
        "committed": committed,
        "log": str(log_file) if args.commit and log_file else None,
        "rule": "同一 URL（忽略域名大小写与锚点）、去除空白后相同的文字、同一附件路径只算一条；默认只检查不写入。",
    })
    return 0


def week_info(day: date, root: Path | None = None) -> dict:
    iso = day.isocalendar()
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    label = f"{iso.year}-W{iso.week:02d}"
    result = {
        "ok": True,
        "date": day.isoformat(),
        "iso_year": iso.year,
        "iso_week": iso.week,
        "label": label,
        "start": monday.isoformat(),
        "end": sunday.isoformat(),
    }
    if root:
        result["weekly_path"] = str(root / "weekly" / f"{label}.md")
        result["daily_paths"] = [
            str(root / "daily" / f"{(monday + timedelta(days=i)).isoformat()}.md")
            for i in range(7)
        ]
    return result


def command_week(args: argparse.Namespace) -> int:
    root = root_path(args.root) if args.root else None
    emit(week_info(parse_day(args.date, root), root))
    return 0


def command_validate_daily(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    text = path.read_text(encoding="utf-8-sig")
    body = re.split(r"\r?\n---\r?\n", text, maxsplit=1)[0]
    count = len(re.sub(r"\s+", "", body))
    missing_sections = [name for name in DAILY_SECTIONS if name not in body]
    require_sections = getattr(args, "require_sections", False)
    too_long = count > args.limit
    emit({
        "ok": not too_long and not (require_sections and missing_sections),
        "file": str(path),
        "count_non_whitespace": count,
        "limit": args.limit,
        "remaining": args.limit - count,
        "rule": "第一个独立 --- 分隔线前的全部非空白字符，含标题。",
        "require_sections": require_sections,
        "sections": list(DAILY_SECTIONS),
        "missing_sections": missing_sections,
        "sections_rule": "开启 --require-sections 时正文须包含这三个小节；缺失时退出码为 3，字数超限仍为 2。",
    })
    if too_long:
        return 2
    if require_sections and missing_sections:
        return 3
    return 0


def command_status(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    day = parse_day(args.date, root)
    config_file = root / "config.json"
    config = {}
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding="utf-8"))
    paths = {
        "inbox": root / "inbox" / f"{day.isoformat()}.md",
        "notes": root / "notes" / f"{day.isoformat()}.md",
        "daily": root / "daily" / f"{day.isoformat()}.md",
    }
    emit({
        "ok": config_file.exists(),
        "root": str(root),
        "date": day.isoformat(),
        "profile_confirmed": bool(config.get("profile_confirmed", False)),
        "files": {name: {"path": str(path), "exists": path.exists()} for name, path in paths.items()},
        "week": week_info(day, root),
    })
    return 0 if config_file.exists() else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="破万卷本地数据工具")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="初始化个人数据目录，不覆盖已有文件")
    init.add_argument("--root", required=True)
    init.add_argument("--timezone", default="local")
    init.set_defaults(func=command_init)

    confirm = sub.add_parser("confirm-profile", help="在用户明确确认后标记档案可用")
    confirm.add_argument("--root", required=True)
    confirm.set_defaults(func=command_confirm_profile)

    ingest = sub.add_parser("ingest", help="原样追加一份记录并按 SHA-256 去重")
    ingest.add_argument("--root", required=True)
    ingest.add_argument("--date", help="YYYY-MM-DD，默认按配置时区取当天")
    source = ingest.add_mutually_exclusive_group(required=True)
    source.add_argument("--file")
    source.add_argument("--text")
    ingest.set_defaults(func=command_ingest)

    dedupe = sub.add_parser("dedupe-items", help="按链接、文字或附件路径做条目级去重")
    dedupe.add_argument("--file", required=True, help="条目清单 JSONL：每行含 id，以及 url、text、path 之一")
    dedupe.add_argument("--root", help="可选数据目录：读取历史去重记录，配合 --commit 追加")
    dedupe.add_argument("--commit", action="store_true", help="把首次出现的条目写入 state/item-log.jsonl")
    dedupe.set_defaults(func=command_dedupe_items)

    week = sub.add_parser("week", help="计算 ISO-8601 周标签与起止日期")
    week.add_argument("--date", help="YYYY-MM-DD，默认按配置时区取当天")
    week.add_argument("--root", help="可选数据目录，用于返回对应文件路径和时区")
    week.set_defaults(func=command_week)

    validate = sub.add_parser("validate-daily", help="校验每日正文非空白字符数")
    validate.add_argument("--file", required=True)
    validate.add_argument("--limit", type=int, default=DAILY_LIMIT)
    validate.add_argument(
        "--require-sections",
        action="store_true",
        help="同时要求正文包含“最值得知道、与你何干、留给你判断”，缺失时退出码为 3",
    )
    validate.set_defaults(func=command_validate_daily)

    status = sub.add_parser("status", help="检查当天文件、档案确认状态和周信息")
    status.add_argument("--root", required=True)
    status.add_argument("--date", help="YYYY-MM-DD，默认按配置时区取当天")
    status.set_defaults(func=command_status)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
