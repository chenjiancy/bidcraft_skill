# -*- coding: utf-8 -*-
"""L3 端到端测试：M6 模板设计器 CLI（tpl-design）全流程（subprocess，临时根）。

验证命令契约与退出码约定：apply 落盘登记 → validate 通过 → specimen 模板全映射出样张。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
CLI = os.path.join(_SCRIPTS, "bidcraft.py")
ENT = "模板设计端到端测试监理有限公司"

REPO = Path(__file__).resolve().parents[2]
EXAMPLE_TPL = REPO / "共享资源" / "技术标风格" / "模板" / "示例-标准技术标.json"


def run(root, cwd, *args):
    return subprocess.run(
        [sys.executable, CLI, "--root", root, "--enterprise", ENT, *args],
        capture_output=True, text=True, encoding="utf-8", cwd=cwd)


class TestTplDesignCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m6_tpl_")
        self.root = Path(self.tmp)
        r = run(str(self.root), self.tmp, "init-enterprise", "--name", ENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tpl_dir = self.root / "共享资源" / "技术标风格" / "模板"
        self.tpl_dir.mkdir(parents=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_empty_and_apply_validate(self):
        # 空模板目录容错
        r = run(str(self.root), self.tmp, "tpl-design", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("空", r.stdout)
        # apply 落盘（dry-run 拒绝 → --confirm 成功）
        r = run(str(self.root), self.tmp, "tpl-design", "--apply", str(EXAMPLE_TPL))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("dry-run", r.stdout)
        r = run(str(self.root), self.tmp, "tpl-design", "--apply", str(EXAMPLE_TPL), "--confirm")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tpl_dir / "示例-标准技术标.json").is_file())
        # validate 通过
        r = run(str(self.root), self.tmp, "tpl-design", "--validate", "示例-标准技术标.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("通过", r.stdout)
        # list 显示已登记
        r = run(str(self.root), self.tmp, "tpl-design", "--list")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("示例-标准技术标.json", r.stdout)

    def test_specimen_template_full(self):
        # 模板全映射样张（cwd=临时目录，样张落 cwd；fixture 回溯 REPO 共享预设）
        r = run(str(self.root), self.tmp, "tpl-design", "--specimen", str(EXAMPLE_TPL),
                "--fill", "project_name=端到端工程;enterprise_name=端到端企业")
        self.assertEqual(r.returncode, 0, r.stderr)
        target = Path(self.tmp) / "技术标样张_示例-标准技术标.docx"
        self.assertTrue(target.is_file(), "样张 docx 缺失：%s" % r.stdout)
        # 内容级抽查：封面/扉页填充 + 结尾
        from docx import Document
        doc = Document(str(target))
        text = "\n".join(p.text for p in doc.paragraphs)
        self.assertIn("端到端工程", text)
        self.assertIn("端到端企业", text)
        self.assertIn("（以下无正文）", text)


if __name__ == "__main__":
    unittest.main()
