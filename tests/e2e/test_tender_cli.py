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
        """agent 产物：投标要点 / 素材清单 文本 + JSON（v2.1：投标要点须 9 模块全覆盖）。"""
        pmd = self.root / "points.md"
        pmd.write_text("# 投标要点\n## 项目概况\n- 项目名称：XX", encoding="utf-8")
        pjson = self.root / "points.json"
        pjson.write_text(json.dumps({"project": PROJECT, "modules": [
            {"id": "basic", "title": "项目基本信息", "type": "fields",
             "fields": {"项目名称": {"value": "XX", "evidence": "第1页"}}},
            {"id": "qualification", "title": "资格条件", "type": "items", "items": []},
            {"id": "staff", "title": "人员配备", "type": "fields", "fields": {}},
            {"id": "project_overview", "title": "项目概况与监理工作内容", "type": "fields", "fields": {}},
            {"id": "scoring", "title": "评分办法", "type": "mixed"},
            {"id": "pricing", "title": "报价要求", "type": "fields", "fields": {}},
            {"id": "submission", "title": "响应文件编制与递交", "type": "fields", "fields": {}},
            {"id": "reject", "title": "废标/否决红线", "type": "items", "items": []},
            {"id": "pending", "title": "待确认/缺失项", "type": "items", "items": []}],
            },
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
        # 1) tender-init 幂等（项目级目录结构：招标解析 + 项目资料）
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.tdir.is_dir())
        self.assertTrue((self.ent_dir / "项目级" / PROJECT / "项目资料").is_dir(),
                        "tender-init 应创建项目资料目录（项目独享资料）")
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
        """PDF 场景：--file 归档原件 + --text-file 提供 agent 提取文本（回退路径）。"""
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

    def test_extract_pdf_auto(self):
        """④ PDF 自动提取：--file <真 PDF> 不再需要 --text-file。无 PyMuPDF 跳过。"""
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                self.skipTest("未安装 PyMuPDF")
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        pdf = self.root / "招标文件.pdf"
        d = fitz.open()
        page = d.new_page()
        page.insert_text((72, 72), "第一章 招标公告", fontname="china-s")
        d.save(str(pdf))
        d.close()
        r = run(str(self.root), "tender-extract", "--project", PROJECT, "--file", str(pdf))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / "源文件" / ("源文件_%s.pdf" % PROJECT)).exists())
        self.assertTrue((self.tdir / "原文_招标文件.txt").exists())
        content = (self.tdir / "原文_招标文件.txt").read_text(encoding="utf-8")
        self.assertIn("第一章 招标公告", content)
        self.assertIn("【第 1 页】", content)

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

    def test_parse_missing_9module_exit1(self):
        """v2.1：投标要点缺标准模块（如 pending）→ tender-parse 拒绝落盘。"""
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        pmd, pjson, lmd, ljson = self._seed_products()
        doc = json.loads(pjson.read_text(encoding="utf-8"))
        doc["modules"] = [m for m in doc["modules"] if m["id"] != "pending"]
        pjson.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        r = run(str(self.root), "tender-parse", "--project", PROJECT,
                "--points-md", str(pmd), "--points-json", str(pjson),
                "--list-md", str(lmd), "--list-json", str(ljson))
        self.assertEqual(r.returncode, 1)
        self.assertIn("pending", r.stderr)


class TestTenderFmtRuleDiffCli(TenderCliBase):
    """v2.1：tender-fmt / tender-rule / tender-diff CLI 全流程。"""

    FMT_TEXT = (
        "第一章 招标公告\n"
        "项目编号：HXTD-2026-018\n"
        "最高投标限价：48.86万元\n"
        "投标截止时间：2026年8月10日 14:00\n"
        "第七章 响应文件格式\n"
        "一、投标函\n"
        "（一）投标函格式\n"
        "法定代表人：\n"
        "第八章 评标标准\n"
    )

    def _seed_original(self):
        txt = self.root / "招标文件.txt"
        txt.write_text(self.FMT_TEXT, encoding="utf-8")
        r = run(str(self.root), "tender-extract", "--project", PROJECT, "--file", str(txt))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_fmt_rule_diff_flow(self):
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        self._seed_original()

        # tender-fmt：响应文件格式独立文件（自动定位章节）
        r = run(str(self.root), "tender-fmt", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        fmt_p = self.tdir / ("响应文件格式_%s.txt" % PROJECT)
        self.assertTrue(fmt_p.exists())
        content = fmt_p.read_text(encoding="utf-8")
        self.assertIn("第七章 响应文件格式", content)
        self.assertIn("法定代表人：", content)
        self.assertNotIn("第八章", content)

        # tender-rule：通道A 文档解析
        r = run(str(self.root), "tender-rule", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        rule_p = self.tdir / ("文档解析_%s.json" % PROJECT)
        self.assertTrue(rule_p.exists())
        self.assertIn("HXTD-2026-018", rule_p.read_text(encoding="utf-8"))

        # tender-diff：双通道差异比对（通道B 无对应字段 → 存在性差异）
        pmd, pjson, lmd, ljson = self._seed_products()
        r = run(str(self.root), "tender-parse", "--project", PROJECT,
                "--points-md", str(pmd), "--points-json", str(pjson),
                "--list-md", str(lmd), "--list-json", str(ljson))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run(str(self.root), "tender-diff", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tdir / ("双通道差异_%s.json" % PROJECT)).exists())
        self.assertTrue((self.tdir / ("双通道差异_%s.md" % PROJECT)).exists())
        self.assertIn("存在性差异", r.stdout)

    def test_fmt_not_found_exit1(self):
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0)
        txt = self.root / "招标文件.txt"
        txt.write_text("第一章 招标公告\n一、投标函\n", encoding="utf-8")
        r = run(str(self.root), "tender-extract", "--project", PROJECT, "--file", str(txt))
        self.assertEqual(r.returncode, 0)
        r = run(str(self.root), "tender-fmt", "--project", PROJECT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("定位失败", r.stderr)

    def test_m1_regression_still_ok(self):
        """回归：挂载 M4 后 M1 命令不受影响。"""
        r = run(str(self.root), "list-enterprises")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(ENT, r.stdout)


class TestTenderGapCli(TenderCliBase):
    """v2.6：素材缺口收口 CLI（init/add/resolve/waive/verify 契约 + 产物落位）。"""

    def test_gap_full_flow(self):
        r = run(str(self.root), "tender-init", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)

        # init
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--init")
        self.assertEqual(r.returncode, 0, r.stderr)
        json_p = self.tdir / ("素材缺口_%s.json" % PROJECT)
        md_p = self.tdir / ("素材缺口_%s.md" % PROJECT)
        self.assertTrue(json_p.exists())
        self.assertTrue(md_p.exists())

        # add 文字性缺口
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--add",
                "--item", "拟派总监理工程师联系电话", "--type", "text",
                "--source", "投标要点·模块二·人员红线")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("G01", r.stdout)
        # add 图片/文件缺口
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--add",
                "--item", "总监理工程师注册证扫描件", "--type", "asset",
                "--source", "响应文件格式·拟派人员表")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("G02", r.stdout)

        # verify：未收口 → 列出待补充
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("尚未收口", r.stdout)
        self.assertIn("G01", r.stdout)

        # resolve（用户输入文字）
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--resolve",
                "--gap-id", "G01", "--value", "13800000000", "--note", "用户会话输入")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("已补充", r.stdout)
        # waive（用户确认无此素材）
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--waive",
                "--gap-id", "G02", "--note", "用户无此素材，对投标无影响")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("豁免", r.stdout)

        # verify：全部收口
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--verify")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("全部收口", r.stdout)
        self.assertIn("可以进入项目模板生成", r.stdout)

        # show（人读渲染）
        r = run(str(self.root), "tender-gap", "--project", PROJECT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("素材缺口清单", r.stdout)
        self.assertIn("13800000000", r.stdout)

    def test_gap_show_without_init_raises(self):
        r = run(str(self.root), "tender-gap", "--project", PROJECT)
        self.assertEqual(r.returncode, 1)
        self.assertIn("先执行 tender-gap --init", r.stderr)

    def test_gap_bad_type_exit1(self):
        run(str(self.root), "tender-init", "--project", PROJECT)
        run(str(self.root), "tender-gap", "--project", PROJECT, "--init")
        r = run(str(self.root), "tender-gap", "--project", PROJECT, "--add",
                "--item", "某某资料", "--type", "file", "--source", "投标要点")
        self.assertEqual(r.returncode, 1)
        self.assertIn("必须是", r.stderr)

    def test_gap_json_validate_ok(self):
        run(str(self.root), "tender-init", "--project", PROJECT)
        run(str(self.root), "tender-gap", "--project", PROJECT, "--init")
        run(str(self.root), "tender-gap", "--project", PROJECT, "--add",
            "--item", "联系电话", "--type", "text", "--source", "投标要点")
        run(str(self.root), "tender-gap", "--project", PROJECT, "--resolve",
            "--gap-id", "G01", "--value", "13900000000")
        json_p = self.tdir / ("素材缺口_%s.json" % PROJECT)
        doc = json.loads(json_p.read_text(encoding="utf-8"))
        self.assertEqual(doc["items"][0]["status"], "已补充")
        self.assertEqual(doc["items"][0]["value"], "13900000000")


if __name__ == "__main__":
    unittest.main()
