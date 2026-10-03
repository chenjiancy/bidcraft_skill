# -*- coding: utf-8 -*-
"""L3 端到端测试：M2 模板库 CLI 全流程（subprocess 调用，临时根，数量最少）。
验证命令契约、退出码约定（0/1）与企业级落位；并回归验证 M1/M4 命令不受影响。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
CLI = os.path.join(_SCRIPTS, "bidcraft.py")
ENT = "模板端到端测试监理有限公司"


def make_min_docx(path, text):
    import xml.sax.saxutils as sx
    paras = "".join("<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % sx.escape(p)
                    for p in text.split("\n"))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:body>%s</w:body></w:document>' % paras)
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
          '</Types>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("word/document.xml", doc)


def run(root, *args):
    return subprocess.run(
        [sys.executable, CLI, "--root", root, "--enterprise", ENT, *args],
        capture_output=True, text=True, encoding="utf-8")


class TplCliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m2_e2e_")
        self.root = Path(self.tmp)
        r = run(str(self.root), "init-enterprise", "--name", ENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tpl_dir = self.root / ENT / "企业级" / "模板库"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTplCliFlow(TplCliBase):
    def test_full_flow(self):
        # 1) tpl-init 幂等
        r = run(str(self.root), "tpl-init")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tpl_dir / "模板台账.json").exists())
        self.assertTrue((self.tpl_dir / "模板台账.csv").exists())
        r = run(str(self.root), "tpl-init")
        self.assertEqual(r.returncode, 0)

        # 2) tpl-import（docx 自动扫描占位符）
        src = self.root / "开标一览表.docx"
        make_min_docx(src, "【项目名称】\n【图片：营业执照】")
        r = run(str(self.root), "tpl-import", "--file", str(src),
                "--agency", "大成工程咨询有限公司", "--mode", "投标", "--note", "报价表")
        self.assertEqual(r.returncode, 0, r.stderr)
        dst = self.tpl_dir / "大成工程咨询有限公司" / "投标" / "开标一览表.docx"
        self.assertTrue(dst.exists())
        self.assertIn("占位符：2", r.stdout)

        # 3) tpl-list / tpl-query / tpl-overview
        r = run(str(self.root), "tpl-list", "--agency", "大成工程咨询有限公司")
        self.assertEqual(r.returncode, 0)
        self.assertIn("开标一览表", r.stdout)
        r = run(str(self.root), "tpl-query", "--keyword", "开标一览表")
        self.assertEqual(r.returncode, 0)
        self.assertIn("大成工程咨询有限公司", r.stdout)
        r = run(str(self.root), "tpl-overview")
        self.assertEqual(r.returncode, 0)
        self.assertIn("台账总数：1", r.stdout)
        # --json 机读
        r = run(str(self.root), "tpl-query", "--keyword", "开标一览表", "--json")
        self.assertEqual(r.returncode, 0)
        data = json.loads(r.stdout)
        self.assertEqual(data["total"], 1)

        # 4) tpl-sync：未登记文件发现
        (self.tpl_dir / "大成工程咨询有限公司" / "投标" / "承诺书.docx").write_bytes(b"x")
        r = run(str(self.root), "tpl-sync")
        self.assertEqual(r.returncode, 0)
        self.assertIn("承诺书.docx", r.stdout)

        # 5) tpl-registry：无登记清单 → 提示；有则打印
        r = run(str(self.root), "tpl-registry",
                "--agency", "大成工程咨询有限公司", "--mode", "投标")
        self.assertEqual(r.returncode, 0)
        self.assertIn("不存在", r.stdout)
        (self.tpl_dir / "大成工程咨询有限公司" / "投标" / "占位符登记清单.md").write_text(
            "## 开标一览表.docx\n|1|【项目名称】|项目名|\n", encoding="utf-8")
        r = run(str(self.root), "tpl-registry",
                "--agency", "大成工程咨询有限公司", "--mode", "投标", "--file", "开标一览表")
        self.assertEqual(r.returncode, 0)
        self.assertIn("开标一览表", r.stdout)

    def test_import_conflict_exit1(self):
        src = self.root / "t.docx"
        make_min_docx(src, "【项目名称】")
        run(str(self.root), "tpl-init")
        r1 = run(str(self.root), "tpl-import", "--file", str(src),
                 "--agency", "A", "--mode", "投标")
        self.assertEqual(r1.returncode, 0)
        r2 = run(str(self.root), "tpl-import", "--file", str(src),
                 "--agency", "A", "--mode", "投标")
        self.assertEqual(r2.returncode, 1)
        self.assertIn("已存在", r2.stderr)

    def test_import_bad_mode_exit1(self):
        src = self.root / "t.docx"
        make_min_docx(src, "【项目名称】")
        run(str(self.root), "tpl-init")
        r = run(str(self.root), "tpl-import", "--file", str(src),
                "--agency", "A", "--mode", "议标")
        self.assertEqual(r.returncode, 2)      # argparse choices 拒绝
        r = run(str(self.root), "tpl-import", "--file", str(src),
                "--agency", "A", "--mode", "采购", "--placeholders", "3")
        self.assertEqual(r.returncode, 0)

    def test_m1_m4_regression_still_ok(self):
        """回归：挂载 M2 后 M1/M4 命令不受影响。"""
        run(str(self.root), "tpl-init")
        r = run(str(self.root), "list-enterprises")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(ENT, r.stdout)
        r = run(str(self.root), "tender-init", "--project", "回归项目监理")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / ENT / "项目级" / "回归项目监理" / "招标解析").is_dir())


if __name__ == "__main__":
    unittest.main()
