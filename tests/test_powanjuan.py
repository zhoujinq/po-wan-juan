import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "po-wan-juan" / "scripts" / "powanjuan.py"
SPEC = importlib.util.spec_from_file_location("powanjuan", SCRIPT)
powanjuan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(powanjuan)


class PowanjuanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="powanjuan-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "synthetic-data"

    def call(self, function, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = function(SimpleNamespace(**kwargs))
        return code, json.loads(output.getvalue())

    def init_root(self):
        return self.call(
            powanjuan.command_init,
            root=str(self.root),
            timezone="Asia/Shanghai",
        )

    def test_init_is_idempotent_and_never_overwrites(self):
        code, first = self.init_root()
        self.assertEqual(code, 0)
        self.assertTrue(first["ok"])
        self_file = self.root / "profile" / "self.md"
        self_file.write_text("# 虚构测试档案\n", encoding="utf-8")
        code, second = self.init_root()
        self.assertEqual(code, 0)
        self.assertTrue(second["already_present"])
        self.assertEqual(self_file.read_text(encoding="utf-8"), "# 虚构测试档案\n")

    def test_ingest_deduplicates_identical_content(self):
        self.init_root()
        args = dict(root=str(self.root), date="2026-11-22", file=None, text="一条虚构测试记录")
        code, first = self.call(powanjuan.command_ingest, **args)
        self.assertEqual(code, 0)
        self.assertFalse(first["duplicate"])
        code, second = self.call(powanjuan.command_ingest, **args)
        self.assertEqual(code, 0)
        self.assertTrue(second["duplicate"])
        inbox = (self.root / "inbox" / "2026-11-22.md").read_text(encoding="utf-8")
        self.assertEqual(inbox.count("一条虚构测试记录"), 1)

    def test_confirm_profile_marks_explicit_confirmation(self):
        self.init_root()
        code, result = self.call(powanjuan.command_confirm_profile, root=str(self.root))
        self.assertEqual(code, 0)
        self.assertTrue(result["profile_confirmed"])
        config = json.loads((self.root / "config.json").read_text(encoding="utf-8"))
        self.assertTrue(config["profile_confirmed"])
        self.assertTrue(config["profile_confirmed_at"])

    def test_iso_week_and_boundaries(self):
        result = powanjuan.week_info(date(2026, 11, 22))
        self.assertEqual(result["label"], "2026-W47")
        self.assertEqual(result["start"], "2026-11-16")
        self.assertEqual(result["end"], "2026-11-22")
        cross_year = powanjuan.week_info(date(2026, 1, 1))
        self.assertEqual(cross_year["label"], "2026-W01")
        self.assertEqual(cross_year["start"], "2025-12-29")

    def test_daily_limit_counts_body_before_separator(self):
        daily = Path(self.temp.name) / "daily.md"
        daily.write_text("字" * 400 + "\n\n---\n\n来源不计入正文", encoding="utf-8")
        code, result = self.call(powanjuan.command_validate_daily, file=str(daily), limit=400)
        self.assertEqual(code, 0)
        self.assertEqual(result["count_non_whitespace"], 400)
        daily.write_text("字" * 401 + "\n\n---\n\n来源", encoding="utf-8")
        code, result = self.call(powanjuan.command_validate_daily, file=str(daily), limit=400)
        self.assertEqual(code, 2)
        self.assertFalse(result["ok"])

    def test_status_reports_initialized_root(self):
        self.init_root()
        code, result = self.call(
            powanjuan.command_status,
            root=str(self.root),
            date="2026-11-22",
        )
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["week"]["label"], "2026-W47")
        self.assertFalse(result["files"]["daily"]["exists"])

    def test_init_creates_pending_knowledge_map_and_card_dir(self):
        code, result = self.init_root()
        self.assertEqual(code, 0)
        knowledge_map = self.root / "profile" / "knowledge-map.md"
        self.assertTrue(knowledge_map.is_file())
        text = knowledge_map.read_text(encoding="utf-8")
        self.assertIn("待确认", text)
        self.assertIn("隐私红线", text)
        self.assertIn("Agent 假设", text)
        self.assertIn("Asia/Shanghai", text)
        self.assertTrue((self.root / "cards").is_dir())
        self.assertNotIn("完成两轮蒸馏访谈", result["next"])
        self.assertIn("可选", result["next"])

    def test_init_never_overwrites_edited_knowledge_map(self):
        self.init_root()
        knowledge_map = self.root / "profile" / "knowledge-map.md"
        self.assertTrue(knowledge_map.is_file())
        knowledge_map.write_text("# 虚构测试地图\n", encoding="utf-8")
        code, second = self.init_root()
        self.assertEqual(code, 0)
        self.assertTrue(second["already_present"])
        self.assertEqual(knowledge_map.read_text(encoding="utf-8"), "# 虚构测试地图\n")

    def write_items(self, name, items):
        path = Path(self.temp.name) / name
        path.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items),
            encoding="utf-8",
        )
        return str(path)

    def dedupe(self, items, root=None, commit=False, name="items.jsonl"):
        return self.call(
            powanjuan.command_dedupe_items,
            file=self.write_items(name, items),
            root=root,
            commit=commit,
        )

    def test_dedupe_items_flags_same_url_text_and_path(self):
        items = [
            {"id": "W-A01", "type": "article", "url": "https://mp.weixin.qq.com/s/abc?x=1#top"},
            {"id": "W-A02", "type": "article", "url": " https://mp.weixin.qq.com/s/abc?x=1 "},
            {"id": "W-A03", "type": "article", "url": "https://mp.weixin.qq.com/s/other"},
            {"id": "W-N01", "type": "note", "text": "今天 想通\n了 一件事"},
            {"id": "W-N02", "type": "note", "text": "今天想通了一件事"},
            {"id": "W-I01", "type": "image", "path": r"附件\A.jpg"},
            {"id": "W-I02", "type": "image", "path": "附件/a.jpg"},
            {"id": "W-V01", "type": "video", "url": "https://b23.tv/xyz"},
        ]
        code, result = self.dedupe(items)
        self.assertEqual(code, 0)
        self.assertEqual(result["total"], 8)
        self.assertEqual(result["unique_ids"], ["W-A01", "W-A03", "W-N01", "W-I01", "W-V01"])
        self.assertEqual(
            [(item["id"], item["first_id"], item["key_kind"]) for item in result["duplicates"]],
            [("W-A02", "W-A01", "url"), ("W-N02", "W-N01", "text"), ("W-I02", "W-I01", "path")],
        )
        self.assertFalse(result["committed"])

    def test_dedupe_items_without_commit_writes_nothing(self):
        code, result = self.dedupe([{"id": "W-A01", "url": "https://example.com/a"}])
        self.assertEqual(code, 0)
        self.assertIsNone(result["log"])
        self.assertFalse((Path(self.temp.name) / "state").exists())
        self.init_root()
        code, result = self.dedupe([{"id": "W-A01", "url": "https://example.com/a"}], root=str(self.root))
        self.assertEqual(code, 0)
        self.assertFalse(result["committed"])
        self.assertFalse((self.root / "state" / "item-log.jsonl").exists())

    def test_dedupe_items_commit_enables_cross_batch_dedupe(self):
        self.init_root()
        first = [
            {"id": "W-A01", "url": "https://example.com/a"},
            {"id": "W-N01", "text": "虚构随笔"},
        ]
        code, result = self.dedupe(first, root=str(self.root), commit=True)
        self.assertEqual(code, 0)
        self.assertTrue(result["committed"])
        self.assertEqual(result["duplicate_count"], 0)
        second = [
            {"id": "S-L01", "url": "https://EXAMPLE.com/a#section"},
            {"id": "W-N09", "text": "虚构 随笔"},
            {"id": "W-A09", "url": "https://example.com/new"},
        ]
        code, result = self.dedupe(second, root=str(self.root), commit=True, name="items-2.jsonl")
        self.assertEqual(code, 0)
        self.assertEqual(result["unique_ids"], ["W-A09"])
        self.assertEqual(
            [(item["id"], item["first_id"]) for item in result["duplicates"]],
            [("S-L01", "W-A01"), ("W-N09", "W-N01")],
        )
        log_lines = (self.root / "state" / "item-log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log_lines), 3)

    def test_dedupe_items_rejects_invalid_input(self):
        bad = Path(self.temp.name) / "bad.jsonl"
        bad.write_text('{"id": "W-A01"\n', encoding="utf-8")
        code, result = self.call(powanjuan.command_dedupe_items, file=str(bad), root=None, commit=False)
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])
        missing_id = self.write_items("missing-id.jsonl", [{"url": "https://example.com/a"}])
        code, result = self.call(
            powanjuan.command_dedupe_items, file=missing_id, root=None, commit=False
        )
        self.assertEqual(code, 1)
        self.assertFalse(result["ok"])

    def write_daily(self, body):
        daily = Path(self.temp.name) / "daily.md"
        daily.write_text(body + "\n\n---\n\n## 来源\n- 虚构来源", encoding="utf-8")
        return str(daily)

    def test_validate_daily_reports_missing_sections_without_failing_by_default(self):
        file = self.write_daily("# 2026-11-25 · 今日洞察\n\n今天没有值得打断你的内容。")
        code, result = self.call(powanjuan.command_validate_daily, file=file, limit=400)
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_sections"], ["最值得知道", "与你何干", "留给你判断"])

    def test_validate_daily_require_sections_rejects_incomplete_digest(self):
        file = self.write_daily("**最值得知道**：一条虚构信息。\n\n**与你何干**：地图未就绪。")
        code, result = self.call(
            powanjuan.command_validate_daily, file=file, limit=400, require_sections=True
        )
        self.assertEqual(code, 3)
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing_sections"], ["留给你判断"])

    def test_validate_daily_require_sections_accepts_three_sections(self):
        file = self.write_daily(
            "# 2026-11-25 · 今日洞察\n\n"
            "**最值得知道**：一条虚构信息。\n\n"
            "**与你何干**：地图未就绪。\n\n"
            "**留给你判断**：一个虚构问题。"
        )
        code, result = self.call(
            powanjuan.command_validate_daily, file=file, limit=400, require_sections=True
        )
        self.assertEqual(code, 0)
        self.assertTrue(result["ok"])
        self.assertEqual(result["missing_sections"], [])

    def test_validate_daily_reports_length_before_structure(self):
        file = self.write_daily("字" * 401)
        code, result = self.call(
            powanjuan.command_validate_daily, file=file, limit=400, require_sections=True
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
