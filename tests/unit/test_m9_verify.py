# -*- coding: utf-8 -*-
"""M9 取证/自检纯逻辑单测：run_checks 断言矩阵（绿灯全通过/缺产物 fail/检查未过 warn/
任务未勾选 warn/重检缺失 warn）+ collect_evidence KPI 与产物索引提取。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m9_verify import verify   # noqa: E402

PROJECT = "P"
ENT = "E"


def _full_proj(root):
    """构造绿灯项目：全部产物 + 闭环完成。"""
    proj = root / ENT / "项目级" / PROJECT
    tdir = proj / "招标解析"; tdir.mkdir(parents=True)
    (tdir / ("投标要点_%s.json" % PROJECT)).write_text(json.dumps({"project": PROJECT}), encoding="utf-8")
    perf = proj / "业绩" / "x.pdf"; perf.parent.mkdir(parents=True); perf.write_bytes(b"%PDF")
    (tdir / ("素材清单_%s.json" % PROJECT)).write_text(json.dumps(
        {"project": PROJECT, "performance": [{"name": "x", "path": str(perf)}]}), encoding="utf-8")
    tech = proj / "技术标"; tech.mkdir(parents=True)
    (tech / "设置.json").write_text(json.dumps({"bidMode": "明标"}), encoding="utf-8")
    outd = tech / "产出"; outd.mkdir(parents=True)
    (outd / ("技术标_%s.docx" % PROJECT)).write_bytes(b"\x00docx")
    cdir = proj / "标书检查"; cdir.mkdir(parents=True)
    (cdir / ("机器检查_%s_技术标.json" % PROJECT)).write_text(json.dumps(
        {"kind": "tech", "检查": [{"id": "t", "ok": True, "issues": []}]}), encoding="utf-8")
    sdir = proj / "模拟评标"; sdir.mkdir(parents=True)
    (sdir / ("模拟评标_%s.json" % PROJECT)).write_text(json.dumps(
        {"summary": {"issues": [{"item": "i", "gap": 0}]}}), encoding="utf-8")
    (sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
        {"project": PROJECT, "tasks": [{"id": "C01", "标题": "x", "完成状态": "已完成"}]}), encoding="utf-8")
    (sdir / ("补救后重检报告_%s.json" % PROJECT)).write_text(json.dumps(
        {"project": PROJECT, "summary": {"已勾选任务": 1, "验证通过": 1}}), encoding="utf-8")
    return proj


class RunChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_project_green(self):
        proj = _full_proj(self.root)
        checks, overall, _concl, _ts = verify.run_checks(proj, PROJECT)
        self.assertEqual(overall, "绿灯")
        self.assertTrue(checks)
        self.assertTrue(all(c["状态"] == "pass" for c in checks), [c for c in checks if c["状态"] != "pass"])

    def test_missing_docx_fail(self):
        proj = _full_proj(self.root)
        (proj / "技术标" / "产出" / ("技术标_%s.docx" % PROJECT)).unlink()
        checks, overall, concl, _ = verify.run_checks(proj, PROJECT)
        self.assertEqual(overall, "红灯")
        self.assertIn("m6_docx", [c["id"] for c in checks if c["状态"] == "fail"])
        self.assertIn("m6_docx", concl)

    def test_check_failed_warn(self):
        proj = _full_proj(self.root)
        cjson = proj / "标书检查" / ("机器检查_%s_技术标.json" % PROJECT)
        cjson.write_text(json.dumps({"kind": "tech", "检查": [
            {"id": "t1", "ok": True, "issues": []}, {"id": "t2", "ok": False, "issues": ["问题"]}]}),
            encoding="utf-8")
        checks, overall, _c, _ = verify.run_checks(proj, PROJECT)
        self.assertEqual(overall, "黄灯")
        c = next(x for x in checks if x["id"] == "m7_check")
        self.assertEqual(c["状态"], "warn")
        self.assertIn("t2", c["依据"])

    def test_task_not_all_done_warn(self):
        proj = _full_proj(self.root)
        sdir = proj / "模拟评标"
        (sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "tasks": [{"id": "C01", "标题": "x", "完成状态": "已完成"},
                                            {"id": "C02", "标题": "y"}]}), encoding="utf-8")
        (sdir / ("补救后重检报告_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "summary": {"已勾选任务": 1, "验证通过": 1}}), encoding="utf-8")
        checks, overall, _c, _ = verify.run_checks(proj, PROJECT)
        self.assertEqual(overall, "黄灯")
        c = next(x for x in checks if x["id"] == "m10_tasks")
        self.assertEqual(c["状态"], "warn")
        self.assertIn("C02", c["依据"])

    def test_done_without_recheck_warn(self):
        proj = _full_proj(self.root)
        sdir = proj / "模拟评标"
        (sdir / ("补救后重检报告_%s.json" % PROJECT)).unlink()
        checks, overall, _c, _ = verify.run_checks(proj, PROJECT)
        self.assertEqual(overall, "黄灯")
        c = next(x for x in checks if x["id"] == "m10_recheck")
        self.assertEqual(c["状态"], "warn")
        self.assertIn("remedy-recheck", c["依据"])


class CollectEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_kpi_extraction(self):
        proj = _full_proj(self.root)
        doc = verify.collect_evidence(proj, PROJECT)
        self.assertEqual(doc["KPI"]["检查项通过"], "1/1")
        self.assertEqual(doc["KPI"]["失分合计"], 0)
        self.assertEqual(doc["KPI"]["任务完成率"], "1/1")
        self.assertEqual(doc["KPI"]["重检通过率"], "1/1")
        self.assertEqual(doc["总评"], "绿灯")
        names = {it["产物"]: it for it in doc["产物清单"]}
        self.assertTrue(names["技术标成稿"]["存在"])
        self.assertEqual(names["技术标成稿"]["相对路径"], "技术标/产出/技术标_%s.docx" % PROJECT)
        self.assertFalse(names["主观评审"]["存在"])

    def test_missing_evidence_red(self):
        proj = root = self.root / ENT / "项目级" / PROJECT
        proj.mkdir(parents=True)
        doc = verify.collect_evidence(proj, PROJECT)
        self.assertEqual(doc["总评"], "红灯")
        self.assertEqual(doc["KPI"]["检查项通过"], None)


if __name__ == "__main__":
    unittest.main()
