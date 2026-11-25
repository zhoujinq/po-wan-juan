import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "po-wan-juan" / "scripts" / "windows-reminder.ps1"
POWERSHELL = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
)

REQUIRED_PHRASES = [
    "出阅读卡片＋日摘",
    "\\inbox\\",
    "\\cards\\",
    "\\daily\\",
    "地图未就绪",
    "400字",
]
RETIRED_PHRASES = [
    "关联我的目标与评测集",
    "完整阅读索引",
    "22:01",
]


@unittest.skipUnless(os.name == "nt" and POWERSHELL.is_file(), "需要 Windows PowerShell 5.1")
class ReminderPromptTests(unittest.TestCase):
    def test_prompt_follows_card_and_digest_flow_without_side_effects(self):
        with tempfile.TemporaryDirectory(prefix="pwj-reminder-") as temp:
            data_root = Path(temp) / "虚构 数据"
            completed = subprocess.run(
                [
                    str(POWERSHELL),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-PrintPrompt",
                    "-DataRoot",
                    str(data_root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(str(data_root), completed.stdout)
            for phrase in REQUIRED_PHRASES:
                self.assertIn(phrase, completed.stdout)
            for phrase in RETIRED_PHRASES:
                self.assertNotIn(phrase, completed.stdout)
            # 只打印提示词：不弹窗、不建任务、不创建数据目录。
            self.assertFalse(data_root.exists())

    def test_default_time_and_task_name_are_unchanged(self):
        text = SCRIPT.read_text(encoding="utf-8-sig")
        self.assertIn("[string]$Time = '22:00'", text)
        self.assertIn("$TaskName = '破万卷-每日投喂提醒'", text)


if __name__ == "__main__":
    unittest.main()
