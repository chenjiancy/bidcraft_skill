# -*- coding: utf-8 -*-
"""L3 端到端测试：M4 招标解析 CLI 全流程（subprocess 调用，临时根，数量最少）。
验证命令契约、退出码约定（0/1）与项目级落位；并回归验证 M1 命令不受影响。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
CLI = os.path.join(_SCRIPTS, "bidcraft.py")
ENT = "端到端测试监理有限公司"
PROJECT = "端到端安置房项目监理"


def run(root, *args):
    return subprocess.run(
        [sys.executable, CLI, "--root", root, "--enterprise", ENT, *args],
        capture_output=True, text=True, encoding="utf-8")


class TenderCliBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_m4_e2e_")
        self.root = Path(self.tmp)
        self.ent_dir = self.root / ENT
        r = run(str(self.root), "init-enterprise", "--name", ENT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.tdir = self.ent_dir / "项目级" / PROJECT / "招标解析"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_products(self):
        """agent 产物：投标要点 / 素材清单 文本 + JSON。"""
        pmd = self.root / "points.md"
        pmd.write_text("# 投标要点\n## 项目概况\n- 项目名称：XX", encoding="utf-8")
        pjson = self.root / "points.json"
        pjson.write_text(json.dumps({"project": PROJECT, "modules": [
            {"id": "m1", "title": "项目概况", "type": "fields",
             "fields": {"project_name": {"value": "XX", "evidence": "第1页"}}}]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        lmd = self.root / "list.md"
        lmd.write_text("# 素材清单", encoding="utf-8")
        ljson = self.root / "list.json"
        ljson.write_text(json.dumps({"project": PROJECT, "items": [
            {"category": "资质", "subtype": "企业资质证书", "keywords": ["房屋建筑工程监理甲级"],
             "purpose": "资格要求", "required": True, "source": "3.1"}]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        return pmd, pjson, lmd, ljson


class TestTenderCliFlow(TenderCliBase):
    def test_full_flow(self):
        # 1) tender-init 幂等
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.tdir.is_dir())
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)

        # 2) tender-extract（txt：归档原件 + 提取原文）
        txt = self.root / "招标文件.txt"
        txt.write_text("第一章 招标公告\n投标截止时间：2026年10月30日", encoding="utf-8")
        r = run(str(self.root), "tender-extract", "--project", PROJECT, "--file", str(txt))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / "原文_招标文件.txt").exists())
        self.assertTrue((self.tdir / "源文件" / ("源文件_%s.txt" % PROJECT)).exists())

        # 3) tender-parse 产物落盘
        pmd, pjson, lmd, ljson = self._seed_products()
        r = run(str(self.root), "tender-parse", "--project", PROJECT,
                "--points-md", str(pmd), "--points-json", str(pjson),
                "--list-md", str(lmd), "--list-json", str(ljson))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / ("投标要点_%s.md" % PROJECT)).exists())
        self.assertTrue((self.tdir / ("素材清单_%s.json" % PROJECT)).exists())

        # 4) tender-check 素材对照（素材库空 → 必须项缺失 → 汇总含必缺）
        r = run(str(self.root), "tender-check", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / ("素材对照_%s.csv" % PROJECT)).exists())
        self.assertIn("必缺", r.stdout)

        # 5) tender-show
        r = run(str(self.root), "tender-show", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("投标要点", r.stdout)
        r = run(str(self.root), "tender-show", "--project", PROJECT, "--what", "list")
        self.assertEqual(r.returncode, 0)
        r = run(str(self.root), "tender-show", "--project", PROJECT, "--what", "check")
        self.assertEqual(r.returncode, 0)
        self.assertIn("素材对照", r.stdout)

    def test_bad_project_name_exit1(self):
        r = run(str(self.root), "tender-init", "--project", "a/b")
        self.assertEqual(r.returncode, 1)

    def test_extract_pdf_with_text_file(self):
        """PDF 场景：--file 归档原件 + --text-file 提供 agent 提取文本。"""
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        pdf = self.root / "招标文件.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake pdf")
        txt = self.root / "提取文本.txt"
        txt.write_text("第一章 招标公告\n项目名称：XX", encoding="utf-8")
        r = run(str(self.root), "tender-extract", "--project", PROJECT,
                "--file", str(pdf), "--text-file", str(txt))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / "源文件" / ("源文件_%s.pdf" % PROJECT)).exists())
        self.assertTrue((self.tdir / "原文_招标文件.txt").exists())

    def test_parse_bad_json_exit1(self):
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        pmd = self.root / "p.md"
        pmd.write_text("x", encoding="utf-8")
        pbad = self.root / "p.json"
        pbad.write_text(json.dumps({"project": "P"}), encoding="utf-8")
        lmd = self.root / "l.md"
        lmd.write_text("x", encoding="utf-8")
        ljson = self.root / "l.json"
        ljson.write_text(json.dumps({"items": [{"category": ""}]}), encoding="utf-8")
        r = run(str(self.root), "tender-parse", "--project", PROJECT,
                "--points-md", str(pmd), "--points-json", str(pbad),
                "--list-md", str(lmd), "--list-json", str(ljson))
        self.assertEqual(r.returncode, 1)

    def test_m1_regression_still_ok(self):
        """回归：挂载 M4 后 M1 命令不受影响。"""
        r = run(str(self.root), "list-enterprises")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(ENT, r.stdout)


if __name__ == "__main__":
    unittest.main()
