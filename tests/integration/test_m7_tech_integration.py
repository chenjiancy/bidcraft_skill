# -*- coding: utf-8 -*-
"""M7 T15 集成测试（L2）：技术标终稿检查 —— 真实 tech-export docx → check-rule（kind=tech）。

覆盖：M6 全链路（init/outline/ctx/draft/parse/rewrite/check/diff/export）产出真实技术标 docx 后，
M7 技术标检查 3 项跑通、落盘 机器检查_<项目>_技术标.json；暗标链路 anbiao_leak 通过。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

from _shared import core                      # noqa: E402
from m6_tech import store, cli as C           # noqa: E402
from m7_check import rule_check as R          # noqa: E402

PROJECT = "T15集成项目"


def _points(bid_mode="明标"):
    rule = "技术标总页数不超过 60 页；%s" % (
        "技术标采用暗标，不得出现企业标识" if bid_mode == "暗标" else "按明标编制")
    return {"project": PROJECT, "modules": [
        {"id": "scoring", "title": "评分办法", "type": "mixed",
         "method": {"value": "综合评分法", "evidence": "e"},
         "score_items": [
             {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
             {"item": "监理大纲·综合比较阐述（20分）", "weight": 20, "unit": "分", "evidence": "E2"}]},
        {"id": "reject", "title": "废标红线", "type": "items",
         "items": [{"type": "格式", "rule": rule, "evidence": "e"}]},
    ]}


def _draft():
    return {"chapters": [
        {"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
         "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
         "keyPoints": ["工程概况", "监理范围"], "wordCnt": 3000,
         "dependsOnMaterials": ["project_overview", "personnel", "performance", "enterprise_profile"]},
        {"id": "ch-02", "no": "2", "title": "质量管理与综合阐述", "level": 1,
         "scoreRefs": [{"idx": 1, "item": "监理大纲·综合比较阐述（20分）", "weight": 20}],
         "keyPoints": ["合同管理"], "wordCnt": 1000, "dependsOnMaterials": []},
    ]}


def _revised(md):
    body = md.split("<!-- M6-COVERAGE")[0].rstrip()
    return body + '\n\n<!-- M6-REVISE\n{"changes":[{"where":"末尾","why":"agent 平台精修补强"}],"untouched":"其余段落未改动"}\n-->\n'


class M7TechIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("T15集成企业")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        self._write_points()
        self._write_material()
        self.draft = self.proj / "章节树草案.json"
        self.draft.write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _write_points(self, bid_mode="明标"):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(bid_mode), ensure_ascii=False), encoding="utf-8")

    def _write_material(self):
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT,
                        "personnel": [{"name": "王五", "role": "总监理工程师"}],
                        "performance": [{"name": "T15集成业绩", "path": "业绩/x.pdf"}],
                        "企业基础信息": {"法定代表人姓名": "赵六", "企业名称": "T15集成企业"},
                        "qualification_required": [], "iso_certificates": [],
                        "honors": [], "items": []}, ensure_ascii=False), encoding="utf-8")

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _args(self, **kw):
        base = {"root": str(self.root), "enterprise": "T15集成企业", "project": PROJECT}
        base.update(kw)
        from types import SimpleNamespace
        return SimpleNamespace(**base)

    def _prep(self, bid_mode="明标"):
        if bid_mode == "暗标":
            self._write_points("暗标")
        C.cmd_tech_init(self._args())
        C.cmd_tech_outline(self._args(file=str(self.draft), tdir="", confirm=True,
                                      expert_pack="", bid_mode=""))
        C.cmd_tech_ctx(self._args(chapter="", all=True))

    def _chain_to_export(self):
        """draft → parse → rewrite → check → diff 裁决 → export（真实技术标 docx）。"""
        from m6_tech import draft as D, diff as Diff, export as E
        D.cmd_tech_draft(self._args(chapter="", all=True, tdir="", json=False))
        for cid in ("ch-01", "ch-02"):
            d = self._tech() / "章节" / ("%s.draft.md" % cid)
            C.cmd_tech_parse(self._args(chapter=cid, file=str(d), json=False))
            rev = self.proj / ("精修_%s.md" % cid)
            rev.write_text(_revised(d.read_text(encoding="utf-8")), encoding="utf-8")
            C.cmd_tech_rewrite(self._args(chapter=cid, file=str(rev)))
        C.cmd_tech_check(self._args(tdir="", chapter="", json=False))
        Diff.cmd_tech_diff(self._args(verdict="", confirm=False, json=False))
        jp = self._tech() / ("检查/双通道差异_%s.json" % PROJECT)
        n = len(json.loads(jp.read_text(encoding="utf-8"))["diffs"])
        vp = self.proj / "裁决.json"
        vp.write_text(json.dumps({"diffs": [{"idx": i, "verdict": "accept"}
                                            for i in range(n)]}, ensure_ascii=False),
                      encoding="utf-8")
        Diff.cmd_tech_diff(self._args(verdict=str(vp), confirm=True, json=False))
        E.cmd_tech_export(self._args(out="", override="", bid_mode="", force=False,
                                     template="", fill="", json=False))
        return self._tech() / "产出" / ("技术标_%s.docx" % PROJECT)

    def _check_tech(self, docx):
        return R.run_rule_checks("", str(self.proj), out_dir=str(docx), kind="tech", tag="")

    def test_real_tech_docx_passes_structure_and_anbiao(self):
        """真实导出 docx：结构检查通过（TOC+outlineLvl 真实落盘）、明标暗标复核跳过。"""
        self._prep()
        docx = self._chain_to_export()
        self.assertTrue(docx.is_file(), "真实技术标 docx 缺失")
        res = self._check_tech(docx)
        ids = {c["id"]: c for c in res["检查"]}
        self.assertIn("tech_structure", ids)
        self.assertTrue(ids["tech_structure"]["ok"], ids["tech_structure"]["issues"])
        self.assertIn("anbiao_leak", ids)
        self.assertTrue(ids["anbiao_leak"]["ok"], ids["anbiao_leak"]["issues"])
        self.assertTrue(any("跳过" in x for x in ids["anbiao_leak"]["issues"]))   # 明标
        jp = self.proj / "标书检查" / ("机器检查_%s_技术标.json" % PROJECT)
        self.assertTrue(jp.is_file(), "机器检查 json 落盘缺失")
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual(doc["kind"], "tech")
        self.assertEqual(doc["tag"], "技术标")
        self.assertEqual([c["id"] for c in doc["检查"]][:3],
                         ["format", "placeholder", "sensitive"])      # 通用硬检查在前

    def test_real_tech_docx_anbiao_mode_passes_leak_check(self):
        """暗标真实导出 docx：anbiao_leak 复核不命中（M6 暗标注入保证终稿无企业标识）。"""
        self._prep("暗标")
        docx = self._chain_to_export()
        res = self._check_tech(docx)
        ids = {c["id"]: c for c in res["检查"]}
        self.assertIn("anbiao_leak", ids)
        self.assertTrue(ids["anbiao_leak"]["ok"], ids["anbiao_leak"]["issues"])


if __name__ == "__main__":
    unittest.main()
