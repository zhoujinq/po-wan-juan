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


if __name__ == "__main__":
    unittest.main()
