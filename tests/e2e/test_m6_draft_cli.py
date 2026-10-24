# -*- coding: utf-8 -*-
"""M6 T14 端到端测试（L3）：tech-draft 自动撰写引擎 CLI 全链路。

真实入口 bidcraft.main（--root/--enterprise/子命令 argv）：
init→outline(--confirm)→ctx(--all)→draft(--all)→parse(逐章)→rewrite(精修)→check→diff(裁决)→
export docx；另覆盖：闸门/上下文缺失拒绝、单章生成、--json 输出、暗标无泄露。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft                       # noqa: E402
from m6_tech import store             # noqa: E402

PROJECT = "T14端到端项目"
ENT = "T14端到端企业"


def _points(bid_mode="明标"):
    rule = "技术标总页数不超过 60 页；%s" % (
        "技术标采用暗标，不得出现企业标识" if bid_mode == "暗标" else "按明标编制")
    return {
        "project": PROJECT,
        "modules": [
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": [
                 {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
                 {"item": "监理大纲·综合比较阐述（20分）", "weight": 20, "unit": "分", "evidence": "E2"}]},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": rule, "evidence": "e"}]},
        ],
    }


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


class DraftE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.ent = self.root / ENT
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
                        "personnel": [{"name": "钱七", "role": "总监理工程师"}],
                        "performance": [{"name": "端到端业绩", "path": "业绩/x.pdf"}],
                        "企业基础信息": {"法定代表人姓名": "孙八"},
                        "qualification_required": [], "iso_certificates": [],
                        "honors": [], "items": []}, ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = __import__("io").StringIO(), __import__("io").StringIO(), 0
        with __import__("contextlib").redirect_stdout(out), __import__("contextlib").redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", ENT] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _prep(self, bid_mode="明标"):
        if bid_mode == "暗标":
            self._write_points("暗标")
        self.assertEqual(self._run("tech-init", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-outline", "--project", PROJECT, "--confirm",
                                   "--file", str(self.draft))[0], 0)
        self.assertEqual(self._run("tech-ctx", "--project", PROJECT, "--all")[0], 0)

    def _export(self, force=False):
        argv = ["tech-export", "--project", PROJECT, "--enterprise", ENT]
        if force:
            argv += ["--force"]
        return self._run(*argv)

    # -- 用例 -------------------------------------------------------------
    def test_draft_gates(self):
        """未 outline / 未 ctx 时拒绝生成（闸门纪律）。"""
        self._run("tech-init", "--project", PROJECT)
        code, _, err = self._run("tech-draft", "--project", PROJECT, "--chapter", "ch-01")
        self.assertEqual(code, 1)
        self.assertIn("章节树", err)
        self._run("tech-outline", "--project", PROJECT, "--confirm", "--file", str(self.draft))
        code, _, err = self._run("tech-draft", "--project", PROJECT, "--chapter", "ch-01")
        self.assertEqual(code, 1)
        self.assertIn("上下文包不存在", err)

    def test_draft_single_chapter_and_json(self):
        self._prep()
        code, out, _ = self._run("tech-draft", "--project", PROJECT, "--chapter", "ch-01")
        self.assertEqual(code, 0, out)
        self.assertTrue((self._tech() / "章节" / "ch-01.draft.md").is_file())
        code, out, _ = self._run("tech-draft", "--project", PROJECT, "--chapter", "ch-01", "--json")
        self.assertEqual(code, 0)
        obj = json.loads(out)
        self.assertEqual(obj["chapters"][0]["id"], "ch-01")
        self.assertGreaterEqual(obj["chapters"][0]["chars"], 0)

    def test_draft_all_full_chain_to_export(self):
        """全链路：draft --all → parse → rewrite → check → diff 裁决 → export docx。"""
        self._prep()
        self.assertEqual(self._run("tech-draft", "--project", PROJECT, "--all")[0], 0)
        for cid in ("ch-01", "ch-02"):
            d = self._tech() / "章节" / ("%s.draft.md" % cid)
            self.assertTrue(d.is_file(), cid)
            self.assertEqual(self._run("tech-parse", "--project", PROJECT, "--chapter", cid,
                                       "--file", str(d))[0], 0)
            md = d.read_text(encoding="utf-8").split("<!-- M6-COVERAGE")[0].rstrip()
            rev = self.proj / ("精修_%s.md" % cid)
            rev.write_text(md + '\n\n<!-- M6-REVISE\n{"changes":[{"where":"末尾","why":"LLM 精修"}],"untouched":"其余未动"}\n-->\n',
                           encoding="utf-8")
            self.assertEqual(self._run("tech-rewrite", "--project", PROJECT, "--chapter", cid,
                                       "--file", str(rev))[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        self.assertEqual(self._run("tech-diff", "--project", PROJECT)[0], 0)
        # 未裁决 → 拒绝导出
        self.assertEqual(self._export()[0], 1)
        jp = self._tech() / ("检查/双通道差异_%s.json" % PROJECT)
        n = len(json.loads(jp.read_text(encoding="utf-8"))["diffs"])
        vp = self.proj / "裁决.json"
        vp.write_text(json.dumps({"diffs": [{"idx": i, "verdict": "accept"}
                                            for i in range(n)]}, ensure_ascii=False),
                      encoding="utf-8")
        self.assertEqual(self._run("tech-diff", "--project", PROJECT, "--verdict", str(vp),
                                   "--confirm")[0], 0)
        code, out, _ = self._export()
        self.assertEqual(code, 0, out)
        out_docx = self._tech() / "产出" / ("技术标_%s.docx" % PROJECT)
        self.assertTrue(out_docx.is_file(), "导出 docx 缺失")

    def test_draft_anbiao_no_identity_leak(self):
        """暗标：草稿无企业/人名/业绩名，parse 敏感词校验天然通过。"""
        self._prep("暗标")
        code, out, _ = self._run("tech-draft", "--project", PROJECT, "--all")
        self.assertEqual(code, 0, out)
        md = (self._tech() / "章节" / "ch-01.draft.md").read_text(encoding="utf-8")
        for banned in (ENT, "钱七", "孙八", "端到端业绩"):
            self.assertNotIn(banned, md)
        d = self._tech() / "章节" / "ch-01.draft.md"
        self.assertEqual(self._run("tech-parse", "--project", PROJECT, "--chapter", "ch-01",
                                   "--file", str(d))[0], 0)


if __name__ == "__main__":
    unittest.main()
