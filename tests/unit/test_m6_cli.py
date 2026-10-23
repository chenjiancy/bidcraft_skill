# -*- coding: utf-8 -*-
"""M6 技术标制作 · CLI 首批（T5）单测：tech-init / tech-outline / tech-ctx / tech-status。"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import bidcraft                     # noqa: E402
from _shared import core            # noqa: E402
from m6_tech import store           # noqa: E402

PROJECT = "测试项目M6"


def _points(score_items=None, bid_mode="明标", pages=60):
    items = score_items if score_items is not None else [
        {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
        {"item": "质量管理体系认证证书", "weight": 1, "unit": "分", "evidence": "E2"},
        {"item": "监理大纲·综合比较阐述（20分）", "weight": 20, "unit": "分", "evidence": "E3"},
    ]
    rule = "技术标总页数不超过 %d 页；%s" % (
        pages, "技术标采用暗标，不得出现企业标识" if bid_mode == "暗标" else "按明标编制")
    return {
        "project": PROJECT,
        "modules": [
            {"id": "basic", "title": "项目基本信息", "type": "fields", "fields": {
                "采购人": {"value": "和县住建局", "evidence": "e"},
                "项目名称": {"value": PROJECT, "evidence": "e"},
                "服务期": {"value": "合同签订至缺陷责任期结束", "evidence": "e"},
            }},
            {"id": "project_overview", "title": "项目概况", "type": "fields", "fields": {
                "项目概况": {"value": "两个片区共 762 栋房屋", "evidence": "e"},
                "监理范围": {"value": "施工及保修阶段全过程监理", "evidence": "e"},
            }},
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": items},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": rule, "evidence": "e"}]},
        ],
    }


def _material():
    return {
        "project": PROJECT,
        "personnel": [{"name": "张三", "role": "总监理工程师"}],
        "performance": [{"name": "某小区改造监理", "path": "业绩/某小区.pdf"}],
        "企业基础信息": {"法定代表人姓名": "李四"},
        "qualification_required": [{"name": "营业执照", "path": "资质/营业执照.pdf"}],
        "iso_certificates": [], "honors": [],
        "items": [],
    }


def _draft(refs=None, chapters=2):
    refs = refs if refs is not None else [0, 1, 2]
    out = [{
        "id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
        "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
        "keyPoints": ["监理大纲", "工程概况", "监理范围", "质量控制", "进度控制"],
        "wordCnt": 3000, "dependsOnMaterials": ["project_overview", "personnel"],
    }]
    if chapters > 1:
        out.append({
            "id": "ch-02", "no": "2", "title": "质量管理与综合阐述", "level": 1,
            "scoreRefs": [{"idx": i, "item": ["质量管理体系认证证书",
                                              "监理大纲·综合比较阐述（20分）"][i - 1],
                           "weight": [1, 20][i - 1]} for i in refs if i > 0],
            "keyPoints": ["质量管理体系认证证书", "监理大纲综合比较", "有效期内"],
            "wordCnt": 1000, "dependsOnMaterials": ["enterprise_profile"],
        })
    return {"chapters": out}


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("企业A")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        self._write_points(_points())
        self._write_material()
        self.draft_path = self.proj / "章节树草案.json"
        self._write_draft(_draft())

    def tearDown(self):
        self.tmp.cleanup()

    # -- fixture ---------------------------------------------------------
    def _write_points(self, obj):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _write_material(self):
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")

    def _write_draft(self, obj, path=None):
        (path or self.draft_path).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", "企业A"] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _init(self, *extra):
        return self._run("tech-init", "--project", PROJECT, *extra)

    def _outline(self, *extra):
        return self._run("tech-outline", "--project", PROJECT, "--file", str(self.draft_path), *extra)

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _tree(self):
        return store.read_tree(self._tech())

    # -- tech-init -------------------------------------------------------
    def test_init_creates_dirs_and_settings(self):
        code, out, _ = self._init()
        self.assertEqual(code, 0, out)
        tech = self._tech()
        for sub in store.SUBDIRS:
            self.assertTrue((tech / sub).is_dir(), sub)
        st = json.loads((tech / "设置.json").read_text(encoding="utf-8"))
        self.assertEqual(st["schema"], "m6.settings/v1")
        self.assertEqual(st["bidMode"], "明标")
        self.assertEqual(st["pageConstraint"]["max"], 60)
        self.assertEqual(st["terminology"]["招标人"], "和县住建局")
        self.assertEqual(st["personnel"][0]["post"], "总监理工程师")
        self.assertEqual(st["personnelWriteMode"], "with-name")

    def test_init_detects_anbiao(self):
        self._write_points(_points(bid_mode="暗标"))
        code, out, _ = self._init()
        self.assertEqual(code, 0, out)
        st = json.loads((self._tech() / "设置.json").read_text(encoding="utf-8"))
        self.assertEqual(st["bidMode"], "暗标")
        self.assertEqual(st["personnelWriteMode"], "post-only")

    def test_init_page_override(self):
        code, out, _ = self._init("--pages", "40")
        self.assertEqual(code, 0, out)
        st = json.loads((self._tech() / "设置.json").read_text(encoding="utf-8"))
        self.assertEqual(st["pageConstraint"]["max"], 40)
        self.assertIn("--pages", st["pageConstraint"]["source"])

    def test_init_requires_scoring(self):
        self._write_points({"project": PROJECT, "modules": [
            {"id": "basic", "title": "基础", "type": "fields", "fields": {}}]})
        code, _, err = self._init()
        self.assertEqual(code, 1)
        self.assertIn("scoring", err)

    def test_init_requires_points_file(self):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).unlink()
        code, _, err = self._init()
        self.assertEqual(code, 1)
        self.assertIn("投标要点 JSON 不存在", err)

    # -- tech-outline ----------------------------------------------------
    def test_outline_writes_tree(self):
        self.assertEqual(self._init()[0], 0)
        code, out, _ = self._outline()
        self.assertEqual(code, 0, out)
        tree = self._tree()
        self.assertEqual(tree["schema"], "m6.chapters/v1")
        self.assertEqual(len(tree["chapters"]), 2)
        self.assertEqual(tree["pageConstraint"]["estimate"], 4)
        self.assertEqual(tree["chapters"][0]["status"], "PENDING")
        self.assertEqual(tree["chapters"][0]["files"]["body"], "章节/ch-01.md")
        self.assertFalse(tree.get("confirmed"))

    def test_outline_rejects_bad_draft(self):
        self.assertEqual(self._init()[0], 0)
        self._write_draft({"chapters": [{
            "id": "ch-01", "no": "1", "title": "缺字段", "level": 1,
            "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
            "wordCnt": 1000,
        }]})
        code, _, err = self._outline()
        self.assertEqual(code, 1)
        self.assertIn("校验失败", err)
        self.assertFalse(store.tree_path(self._tech()).is_file())

    def test_outline_confirm_gate(self):
        self.assertEqual(self._init()[0], 0)
        code, out, _ = self._outline("--confirm")
        self.assertEqual(code, 0, out)
        tree = self._tree()
        self.assertTrue(tree["confirmed"])
        self.assertEqual(tree["confirmLog"][-1]["gate"], "outline")

    def test_outline_confirm_blocked_by_missing_coverage(self):
        self.assertEqual(self._init()[0], 0)
        self._write_draft(_draft(refs=[0], chapters=1))
        code, _, err = self._outline("--confirm")
        self.assertEqual(code, 1)
        self.assertIn("未覆盖", err)
        self.assertFalse(store.tree_path(self._tech()).is_file())

    def test_outline_refuses_overwrite_confirmed(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline("--confirm")[0], 0)
        code, _, err = self._outline()
        self.assertEqual(code, 1)
        self.assertIn("已确认", err)

    def test_outline_draft_outside_project(self):
        self.assertEqual(self._init()[0], 0)
        outside = self.root / "外部草案.json"
        self._write_draft(_draft(), path=outside)
        code, _, err = self._run("tech-outline", "--project", PROJECT, "--file", str(outside))
        self.assertEqual(code, 1)
        self.assertIn("越界", err)

    # -- tech-ctx --------------------------------------------------------
    def test_ctx_requires_gate(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline()[0], 0)
        code, _, err = self._run("tech-ctx", "--project", PROJECT, "--chapter", "ch-01")
        self.assertEqual(code, 1)
        self.assertIn("闸门①未确认", err)

    def test_ctx_builds_pack_and_advances(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline("--confirm")[0], 0)
        code, out, _ = self._run("tech-ctx", "--project", PROJECT, "--chapter", "ch-01")
        self.assertEqual(code, 0, out)
        tech = self._tech()
        pack = store.read_context_pack(tech, "ch-01")
        self.assertEqual(pack["schema"], "m6.ctx/v1")
        self.assertEqual(pack["chapter"]["id"], "ch-01")
        self.assertEqual(pack["scoreItems"][0]["idx"], 0)
        self.assertEqual(pack["scoreItems"][0]["evidence"], "E1")
        self.assertEqual(pack["terminology"]["项目名称"], PROJECT)
        self.assertEqual(len(pack["personnel"]), 1)
        self.assertIn("project_overview",
                      [m["category"] for m in pack["materials"]])
        self.assertEqual(pack["bidMode"], "明标")
        self.assertEqual(pack["personnelWriteMode"], "with-name")
        self.assertEqual(pack["kbStatus"], "unavailable")
        self.assertIn("同级：2 质量管理与综合阐述", pack["tocBrief"])
        self.assertEqual(store.find_chapter(store.read_tree(tech), "ch-01")["status"],
                         "CONTEXT_READY")
        self.assertEqual(store.read_state(tech, "ch-01")["status"], "CONTEXT_READY")

    def test_ctx_all_and_anbiao_personnel(self):
        self._write_points(_points(bid_mode="暗标"))
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline("--confirm")[0], 0)
        code, out, _ = self._run("tech-ctx", "--project", PROJECT, "--all")
        self.assertEqual(code, 0, out)
        tech = self._tech()
        for cid in ("ch-01", "ch-02"):
            pack = store.read_context_pack(tech, cid)
            self.assertEqual(pack["bidMode"], "暗标")
            self.assertEqual(pack["personnelWriteMode"], "post-only")
        self.assertEqual(pack["personnel"], [])   # ch-02 未依赖 personnel

    def test_ctx_requires_chapter_or_all(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline("--confirm")[0], 0)
        code, _, err = self._run("tech-ctx", "--project", PROJECT)
        self.assertEqual(code, 1)
        self.assertIn("--chapter", err)

    # -- tech-status -----------------------------------------------------
    def test_status_json(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline("--confirm")[0], 0)
        tech = self._tech()
        ch = store.find_chapter(store.read_tree(tech), "ch-01")
        store.write_chapter_body(tech, ch, "监理大纲" * 300)
        code, out, _ = self._run("tech-status", "--project", PROJECT, "--json")
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["bidMode"], "明标")
        self.assertTrue(doc["summary"]["confirmed"])
        row = [r for r in doc["chapters"] if r["id"] == "ch-01"][0]
        self.assertEqual(row["actualChars"], 1200)
        self.assertEqual(row["pages"], 2)
        self.assertEqual(row["status"], "PENDING")

    def test_init_does_not_overwrite_settings_after_tree(self):
        self.assertEqual(self._init()[0], 0)
        self.assertEqual(self._outline()[0], 0)
        code, out, _ = self._init()
        self.assertEqual(code, 0, out)
        self.assertIn("已存在章节树", out)
        st = json.loads((self._tech() / "设置.json").read_text(encoding="utf-8"))
        self.assertNotIn("已存在章节树", "\n".join(st["notes"]))


if __name__ == "__main__":
    unittest.main()
