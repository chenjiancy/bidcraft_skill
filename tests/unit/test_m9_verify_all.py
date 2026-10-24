# -*- coding: utf-8 -*-
"""M9 T20 企业级多项目体检纯逻辑单测：run_checks_all 汇总（多项目混合状态、
红灯项目未通过项提取、无项目/结论分级）。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m9_verify import verify   # noqa: E402

ENT = "E"


def _mk_proj(root, name, full):
    proj = root / ENT / "项目级" / name
    tdir = proj / "招标解析"; tdir.mkdir(parents=True)
    (tdir / ("投标要点_%s.json" % name)).write_text(json.dumps({"project": name}), encoding="utf-8")
    (tdir / ("素材清单_%s.json" % name)).write_text(json.dumps({"project": name}), encoding="utf-8")
    tech = proj / "技术标"; tech.mkdir(parents=True)
    (tech / "设置.json").write_text(json.dumps({"bidMode": "明标"}), encoding="utf-8")
    outd = tech / "产出"; outd.mkdir(parents=True)
    (outd / ("技术标_%s.docx" % name)).write_bytes(b"\x00docx")
    if full:
        cdir = proj / "标书检查"; cdir.mkdir(parents=True)
        (cdir / ("机器检查_%s_技术标.json" % name)).write_text(json.dumps(
            {"kind": "tech", "检查": [{"id": "t", "ok": True, "issues": []}]}), encoding="utf-8")
        sdir = proj / "模拟评标"; sdir.mkdir(parents=True)
        (sdir / ("模拟评标_%s.json" % name)).write_text(json.dumps({"summary": {"issues": []}}), encoding="utf-8")
        (sdir / ("失分补救任务单_%s.json" % name)).write_text(json.dumps(
            {"project": name, "tasks": [{"id": "C01", "完成状态": "已完成"}]}), encoding="utf-8")
        (sdir / ("补救后重检报告_%s.json" % name)).write_text(json.dumps(
            {"project": name, "summary": {"已勾选任务": 1, "验证通过": 1}}), encoding="utf-8")


class RunChecksAllTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ENT).mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_mixed_projects(self):
        _mk_proj(self.root, "A项目", True)
        _mk_proj(self.root, "B项目", False)
        agg = verify.run_checks_all(self.root / ENT)
        s = agg["summary"]
        self.assertEqual(s["项目总数"], 2)
        self.assertEqual(s["绿灯"], 1)
        self.assertEqual(s["红灯"], 1)
        self.assertEqual(s["含红灯项目"], ["B项目"])
        by = {r["project"]: r for r in agg["projects"]}
        self.assertEqual(by["A项目"]["总评"], "绿灯")
        self.assertEqual(by["A项目"]["必做未做"], 0)
        self.assertEqual(by["B项目"]["总评"], "红灯")
        self.assertIn("m7_check", by["B项目"]["未通过项"])
        self.assertIn("m8_eval", by["B项目"]["未通过项"])
        self.assertIn("B项目", agg["结论"])

    def test_no_projects(self):
        agg = verify.run_checks_all(self.root / ENT)
        self.assertEqual(agg["summary"]["项目总数"], 0)
        self.assertEqual(agg["summary"]["绿灯"], 0)

    def test_no_project_root(self):
        empty = self.root / "空企业"
        empty.mkdir(parents=True)
        agg = verify.run_checks_all(empty)
        self.assertEqual(agg["summary"]["项目总数"], 0)

    def test_amber_project(self):
        _mk_proj(self.root, "C项目", True)
        # 制造黄灯：重检报告缺失但有勾选任务
        sdir = self.root / ENT / "项目级" / "C项目" / "模拟评标"
        (sdir / ("补救后重检报告_C项目.json")).unlink()
        agg = verify.run_checks_all(self.root / ENT)
        self.assertEqual(agg["summary"]["黄灯"], 1)
        self.assertEqual(agg["summary"]["红灯"], 0)
        self.assertEqual(agg["结论"], "全部项目产物齐备，1 个黄灯待整改；整改后重跑 m9-verify --all 复核")


if __name__ == "__main__":
    unittest.main()
