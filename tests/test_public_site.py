import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"


class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.hrefs = []
        self.runtime_dependencies = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if tag in {"script", "img", "iframe", "audio", "video", "source"} and values.get("src"):
            self.runtime_dependencies.append(values["src"])
        if tag == "link" and "stylesheet" in values.get("rel", ""):
            self.runtime_dependencies.append(values.get("href", ""))


class PublicSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding="utf-8")
        cls.parser = SiteParser()
        cls.parser.feed(cls.html)

    def test_ids_are_unique_and_internal_anchors_resolve(self):
        counts = Counter(self.parser.ids)
        self.assertEqual([key for key, value in counts.items() if value != 1], [])
        missing = [href for href in self.parser.hrefs if href.startswith("#") and href[1:] not in counts]
        self.assertEqual(missing, [])

    def test_no_external_runtime_dependency(self):
        self.assertEqual(self.parser.runtime_dependencies, [])
        self.assertNotIn("miaoda.feishu.cn", self.html)
        self.assertNotIn("doubao.link/app/", self.html)

    def test_demo_is_explicitly_fictional_and_local_only(self):
        self.assertIn("页面数据均为虚构示例", self.html)
        self.assertIn("个人数据只保存在你的本地目录", self.html)
        self.assertIn("公开演示 v0.1.0", self.html)
        self.assertGreaterEqual(self.html.count("虚构演示"), 4)

    def test_public_sources_do_not_contain_private_identifiers(self):
        forbidden = [
            "gavinzhou",
            "astribot",
            "星尘智能",
            "C:\\Users\\",
            "D:\\私人资料\\",
            "open_id",
            "user_id",
        ]
        source_files = [
            path for path in ROOT.rglob("*")
            if path.is_file() and "tests" not in path.parts and path.suffix in {".html", ".md", ".py", ".ps1"}
        ]
        self.assertGreater(len(source_files), 8)
        for path in source_files:
            text = path.read_text(encoding="utf-8").lower()
            for marker in forbidden:
                self.assertNotIn(marker.lower(), text, f"{path.name} 含不应公开的标识")

    def test_skill_tree_is_complete(self):
        expected = [
            "SKILL.md",
            "references/data-and-templates.md",
            "references/reading-and-evaluation.md",
            "scripts/powanjuan.py",
            "scripts/windows-reminder.ps1",
        ]
        for relative in expected:
            path = ROOT / "po-wan-juan" / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 100, relative)

    def test_github_and_onboarding_paths_are_visible(self):
        self.assertGreaterEqual(self.html.count("https://github.com/zhoujinq/po-wan-juan"), 4)
        self.assertIn('data-copy-target="onboarding-prompt"', self.html)
        self.assertIn('id="onboarding-prompt"', self.html)
        self.assertIn("不要在我确认前修改长期偏好或创建系统任务", self.html)

    def test_accessibility_and_reduced_motion_are_present(self):
        self.assertIn(":focus-visible", self.html)
        self.assertIn("prefers-reduced-motion", self.html)
        self.assertIn('role="tablist"', self.html)
        self.assertIn('aria-live="polite"', self.html)

    def test_private_data_directories_are_not_in_repository(self):
        for name in ["inbox", "profile", "daily", "notes", "weekly", "memory", "state", "runtime"]:
            self.assertFalse((ROOT / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
