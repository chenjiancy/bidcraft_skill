# -*- coding: utf-8 -*-
"""⑥ proj-freeze CLI e2e：冻结→审计未变→篡改→审计已改。"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
ENT = "冻结e2e企业"


def run(root, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "bidcraft.py"),
                           "--root", root, *args],
                          capture_output=True, text=True, encoding="utf-8")


class FreezeCliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_freeze_e2e_")
        self.root = Path(self.tmp)
        r = run(str(self.root), "init-enterprise", "--name", ENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tpl = self.root / ENT / "项目级" / "测试项目" / "项目模板"
        self.tpl.mkdir(parents=True)
        from docx import Document
        d = Document()
        d.add_paragraph("【项目名称】封面")
        d.save(str(self.tpl / "封面.docx"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestFreezeCli(FreezeCliBase):
    def test_freeze_check_then_tamper(self):
        r = run(str(self.root), "proj-freeze", "--project", "测试项目")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tpl / "冻结清单.json").is_file())
        self.assertIn("冻结版本 v1", r.stdout)

        r2 = run(str(self.root), "proj-freeze", "--project", "测试项目", "--check")
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertIn("冻结版未变", r2.stdout)

        (self.tpl / "封面.docx").write_bytes(b"tampered")
        r3 = run(str(self.root), "proj-freeze", "--project", "测试项目", "--check")
        self.assertEqual(r3.returncode, 0, r3.stderr)
        self.assertIn("已改（须重新冻结）", r3.stdout)


if __name__ == "__main__":
    unittest.main()
