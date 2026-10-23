# -*- coding: utf-8 -*-
"""M6 T11/T12 集成测试（L2）：真实 python-docx 导出闭环 —— 双通道差异裁决后 tech-export 产出 docx。

覆盖：未裁决差异阻塞导出（--force 留痕绕过）、裁决后正常导出 docx 可打开且含目录域。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

from docx import Document                     # noqa: E402
from _shared import core                      # noqa: E402
from m6_tech import store                    # noqa: E402
from m6_tech import export as E              # noqa: E402

PROJECT = "预览项目"


def _points():
    return {
        "project": PROJECT,
        "modules": [
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": [
                 {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
                 {"item": "监理大纲·综合比较阐述（20分）", "weight": 20, "unit": "分", "evidence": "E2"},
             ]},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": "技术标总页数不超过 60 页；按明标编制", "evidence": "e"}]},
        ],
    }


def _draft():
    return {"chapters": [
        {"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
         "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
         "keyPoints": ["监理大纲"], "wordCnt": 3000, "dependsOnMaterials": ["project_overview"]},
        {"id": "ch-02", "no": "2", "title": "质量管理与综合阐述", "level": 1,
         "scoreRefs": [{"idx": 1, "item": "监理大纲·综合比较阐述（20分）", "weight": 20}],
         "keyPoints": ["监理大纲综合比较"], "wordCnt": 1000, "dependsOnMaterials": []},
    ]}


class RewriteDiffIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("预览企业")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(), ensure_ascii=False), encoding="utf-8")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT, "personnel": [], "performance": [],
                        "items": []}, ensure_ascii=False), encoding="utf-8")
        self.draft = self.proj / "章节树草案.json"
        self.draft.write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _body(self, chars=2400, tail=""):
        return ("# 1 工程概况与监理范围\n\n" + "监理大纲" * (chars // 4) + tail +
                '\n\n<!-- M6-COVERAGE\n'
                '{"keyPoints":[{"point":"监理大纲","covered":true}],'
                '"missingMaterials":[],"notes":"结构完整"}\n-->\n')

    def _prepare(self, bid_mode="明标"):
        args = {"root": str(self.root), "enterprise": "预览企业", "project": PROJECT}
        from m6_tech import cli as C
        from types import SimpleNamespace
        C.cmd_tech_init(SimpleNamespace(**args))
        C.cmd_tech_outline(SimpleNamespace(**args, file=str(self.draft), tdir="", confirm=True,
                                            expert_pack="", bid_mode=""))
        C.cmd_tech_ctx(SimpleNamespace(**args, chapter="ch-01", all=False))
        C.cmd_tech_ctx(SimpleNamespace(**args, chapter="ch-02", all=False))
        md = self.proj / "章节_ch-01.md"
        md.write_text(self._body(), encoding="utf-8")
        C.cmd_tech_parse(SimpleNamespace(**args, chapter="ch-01", file=str(md), json=False))
        md2 = self.proj / "章节_ch-02.md"
        md2.write_text(self._body(chars=800), encoding="utf-8")
        C.cmd_tech_parse(SimpleNamespace(**args, chapter="ch-02", file=str(md2), json=False))
        C.cmd_tech_check(SimpleNamespace(**args, tdir="", chapter="", json=False))
        from m6_tech import diff as D
        D.cmd_tech_diff(SimpleNamespace(**args, verdict="", confirm=False, json=False))

    def _diff_count(self):
        jp = self._tech() / ("检查/双通道差异_%s.json" % PROJECT)
        return len(json.loads(jp.read_text(encoding="utf-8"))["diffs"])

    def _export(self, force=False):
        from m6_tech import export as E
        from types import SimpleNamespace
        return E.cmd_tech_export(SimpleNamespace(
            root=str(self.root), enterprise="预览企业", project=PROJECT, out="", override="",
            bid_mode="", force=force, template="", fill="", json=False))

    def test_export_docx_after_diff_resolved(self):
        self._prepare()
        n = self._diff_count()
        self.assertGreaterEqual(n, 1)
        # 未裁决 → 拒绝
        with self.assertRaises(core.LibraryError) as cm:
            self._export()
        self.assertIn("未全部裁决", str(cm.exception))
        # 裁决 → 导出 docx
        vp = self.proj / "裁决.json"
        vp.write_text(json.dumps({"diffs": [{"idx": i, "verdict": "accept"}
                                            for i in range(n)]}, ensure_ascii=False),
                      encoding="utf-8")
        from m6_tech import diff as D
        from types import SimpleNamespace
        D.cmd_tech_diff(SimpleNamespace(root=str(self.root), enterprise="预览企业",
                                        project=PROJECT, verdict=str(vp), confirm=True,
                                        json=False))
        self.assertEqual(self._export(), 0)
        out = self._tech() / "产出" / ("技术标_%s.docx" % PROJECT)
        self.assertTrue(out.is_file(), "导出 docx 缺失")
        doc = Document(str(out))
        self.assertGreater(len(doc.paragraphs), 0)
        self.assertIn("fldChar", doc.element.xml)        # 目录域


if __name__ == "__main__":
    unittest.main()
