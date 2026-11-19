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

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

SCHEMA_VERSION = 1
DAILY_LIMIT = 400


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
        "profile", "inbox", "notes", "daily", "weekly", "memory", "state", "runtime"
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
        "next": "完成两轮蒸馏访谈，经用户确认后执行 confirm-profile。",
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
    ok = count <= args.limit
    emit({
        "ok": ok,
        "file": str(path),
        "count_non_whitespace": count,
        "limit": args.limit,
        "remaining": args.limit - count,
        "rule": "第一个独立 --- 分隔线前的全部非空白字符，含标题。",
    })
    return 0 if ok else 2


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

    week = sub.add_parser("week", help="计算 ISO-8601 周标签与起止日期")
    week.add_argument("--date", help="YYYY-MM-DD，默认按配置时区取当天")
    week.add_argument("--root", help="可选数据目录，用于返回对应文件路径和时区")
    week.set_defaults(func=command_week)

    validate = sub.add_parser("validate-daily", help="校验每日正文非空白字符数")
    validate.add_argument("--file", required=True)
    validate.add_argument("--limit", type=int, default=DAILY_LIMIT)
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
