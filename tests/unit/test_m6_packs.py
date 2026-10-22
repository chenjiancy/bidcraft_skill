# -*- coding: utf-8 -*-
"""bidcraft · M6 单元测试 —— 专家包（R-T3，契约 §3.3）。

覆盖：
- packs.load_pack：正常加载（含 styleRef 未生效 notes）、id 非法、包不存在、
  schema 错、id 不一致、taxonomy 空、layoutCombo 缺项/非法 id；
- packs.tree_entry / class_for / attach_context：树字段、标题命中（含空白差异）、
  未命中、注入字段完整性；
- CLI 接线：tech-outline --expert-pack 落 expertPack 字段（F2 附加字段放行）、
  包不存在报错；tech-ctx 注入 description 进 .meta、未命中章不注入。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import bidcraft                     # noqa: E402
from _shared import core            # noqa: E402
from m6_tech import packs, store    # noqa: E402

PROJECT = "专家包项目"


def _points():
    rule = "技术标总页数不超过 60 页；按明标编制"
    return {
        "project": PROJECT,
        "modules": [
            {"id": "basic", "title": "项目基本信息", "type": "fields", "fields": {
                "采购人": {"value": "某住建局", "evidence": "e"},
                "项目名称": {"value": PROJECT, "evidence": "e"},
                "服务期": {"value": "合同签订至缺陷责任期结束", "evidence": "e"},
            }},
            {"id": "scoring", "title": "评分办法", "type": "mixed",
             "method": {"value": "综合评分法", "evidence": "e"},
             "score_items": [
                 {"item": "监理大纲（50分）", "weight": 50, "unit": "分", "evidence": "E1"},
                 {"item": "人员配置（30分）", "weight": 30, "unit": "分", "evidence": "E2"},
             ]},
            {"id": "reject", "title": "废标红线", "type": "items",
             "items": [{"type": "格式", "rule": rule, "evidence": "e"}]},
        ],
    }


def _material():
    return {
        "project": PROJECT,
        "personnel": [{"name": "张三", "role": "总监理工程师"}],
        "performance": [], "企业基础信息": {"法定代表人姓名": "李四"},
        "qualification_required": [], "iso_certificates": [], "honors": [],
        "items": [],
    }


def _draft():
    return {"chapters": [
        {"id": "ch-01", "no": "1", "title": "工程概况", "level": 1,
         "scoreRefs": [{"idx": 0, "item": "监理大纲（50分）", "weight": 50}],
         "keyPoints": ["工程概况", "监理范围"], "wordCnt": 1000,
         "dependsOnMaterials": []},
        {"id": "ch-02", "no": "2", "title": "自定义章", "level": 1,
         "scoreRefs": [{"idx": 1, "item": "人员配置（30分）", "weight": 30}],
         "keyPoints": ["人员配置"], "wordCnt": 1000,
         "dependsOnMaterials": []},
    ]}


MANIFEST = {
    "schema": "m6.expert-pack/v1",
    "id": "demo-pack",
    "name": "演示专家包",
    "description": "测试用",
    "tags": ["测试"],
    "bidType": ["engineering"],
    "docType": "ENGINEERING",
    "taxonomy": "taxonomy.json",
    "layoutCombo": {"preset": "single-column", "palette": "deep-indigo",
                    "cover": "full-block", "decoration": "standard",
                    "font": "gov-gongwen", "imageRatio": "mid",
                    "imageRule": "hybrid", "imageLayout": "split-h",
                    "pageSetup": "p1-standard-a4", "headingSystem": "h1-gbt-arabic",
                    "tocStyle": "t1-jianyu-auto", "tableStyle": "tb1-three-line",
                    "captionSystem": "c2-cy-chapter", "paragraphStyle": "pa7-jianyu-15"},
    "styleRef": "styles.json#default",
    "source": {"kind": "test"},
}

TAXONOMY = {
    "schema": "m6.taxonomy/v1",
    "pack": "demo-pack",
    "docType": "ENGINEERING",
    "classes": [
        {"id": "1", "name": "内容完整性及编制说明", "description": "要点甲",
         "bodyMode": "two_step", "illustration": True},
        {"id": "2", "name": "工程概况", "description": "要点乙",
         "bodyMode": "two_step", "illustration": True},
    ],
}


class PacksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("企业A")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(_points(), ensure_ascii=False), encoding="utf-8")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")
        # 共享资源：layout-presets + 专家包
        style_dir = self.root / "共享资源" / "技术标风格"
        style_dir.mkdir(parents=True)
        shutil.copy(_find_presets_source(), style_dir / "layout-presets.json")
        self.pack_dir = style_dir / "专家包" / "demo-pack"
        self.pack_dir.mkdir(parents=True)
        self._write_pack(MANIFEST, TAXONOMY)
        self.draft_path = self.proj / "章节树草案.json"
        self._write_draft()

    def tearDown(self):
        self.tmp.cleanup()

    # -- fixture ---------------------------------------------------------
    def _write_pack(self, manifest, taxonomy):
        (self.pack_dir / "包.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        (self.pack_dir / "taxonomy.json").write_text(
            json.dumps(taxonomy, ensure_ascii=False), encoding="utf-8")

    def _write_draft(self):
        self.draft_path.write_text(
            json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", "企业A"] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    # ---- packs.load_pack ----
    def test_load_pack_ok(self):
        r = packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")
        self.assertEqual(r["manifest"]["id"], "demo-pack")
        self.assertEqual(len(r["taxonomy"]["classes"]), 2)
        self.assertTrue(any("T6" in n for n in r["notes"]))   # styleRef 未生效披露

    def test_find_pack_bad_id(self):
        with self.assertRaises(core.LibraryError):
            packs.find_pack_dir(type("A", (), {"root": str(self.root)})(), "../evil")

    def test_load_pack_missing(self):
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "nope")

    def test_load_pack_wrong_schema(self):
        self._write_pack(dict(MANIFEST, schema="x"), TAXONOMY)
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")

    def test_load_pack_id_mismatch(self):
        self._write_pack(dict(MANIFEST, id="other"), TAXONOMY)
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")

    def test_load_pack_empty_taxonomy(self):
        self._write_pack(MANIFEST, dict(TAXONOMY, classes=[]))
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")

    def test_load_pack_unknown_combo_id(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad["layoutCombo"]["palette"] = "not-exist"
        self._write_pack(bad, TAXONOMY)
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")

    def test_load_pack_missing_combo_key(self):
        bad = json.loads(json.dumps(MANIFEST))
        bad["layoutCombo"].pop("font")
        self._write_pack(bad, TAXONOMY)
        with self.assertRaises(core.LibraryError):
            packs.load_pack(type("A", (), {"root": str(self.root)})(), "demo-pack")

    # ---- tree_entry / class_for / attach_context ----
    def test_tree_entry(self):
        e = packs.tree_entry(MANIFEST)
        self.assertEqual(e, {"id": "demo-pack", "name": "演示专家包", "docType": "ENGINEERING"})

    def test_class_for_match_tolerates_spaces(self):
        c = packs.class_for(TAXONOMY, "内容完整性 及 编制说明")
        self.assertIsNotNone(c)
        self.assertEqual(c["id"], "1")

    def test_class_for_miss(self):
        self.assertIsNone(packs.class_for(TAXONOMY, "不存在的章"))

    def test_attach_context_hit_and_miss(self):
        ctx, ch = {}, {"title": "工程概况"}
        self.assertTrue(packs.attach_context(ctx, MANIFEST, TAXONOMY, ch))
        self.assertEqual(ctx["expertPack"]["classDescription"], "要点乙")
        self.assertTrue(ctx["expertPack"]["illustration"])
        self.assertFalse(packs.attach_context({}, MANIFEST, TAXONOMY, {"title": "其他"}))

    # ---- CLI：tech-outline --expert-pack / tech-ctx 注入 ----
    def test_outline_bind_and_ctx_inject(self):
        self.assertEqual(self._run("tech-init", "--project", PROJECT)[0], 0)
        code, _, err = self._run("tech-outline", "--project", PROJECT,
                                 "--file", str(self.draft_path),
                                 "--expert-pack", "demo-pack", "--confirm")
        self.assertEqual(code, 0, err)
        self.assertIn("专家包 demo-pack", _)
        tech = self.proj / "技术标"
        tree = store.read_tree(tech)
        self.assertEqual(tree["expertPack"]["id"], "demo-pack")   # F2 附加字段放行
        self.assertEqual(self._run("tech-ctx", "--project", PROJECT, "--all")[0], 0)
        meta1 = json.loads((tech / "章节" / ".meta" / "ch-01.json").read_text("utf-8"))
        meta2 = json.loads((tech / "章节" / ".meta" / "ch-02.json").read_text("utf-8"))
        self.assertEqual(meta1["expertPack"]["className"], "工程概况")
        self.assertEqual(meta1["expertPack"]["classDescription"], "要点乙")
        self.assertNotIn("expertPack", meta2)                     # 未命中不注入

    def test_outline_bind_missing_pack_errors(self):
        self._run("tech-init", "--project", PROJECT)
        code, _, err = self._run("tech-outline", "--project", PROJECT,
                                 "--file", str(self.draft_path),
                                 "--expert-pack", "ghost")
        self.assertNotEqual(code, 0)
        self.assertIn("专家包不存在", err)

    def test_outline_without_pack_unchanged(self):
        self._run("tech-init", "--project", PROJECT)
        code, _, err = self._run("tech-outline", "--project", PROJECT,
                                 "--file", str(self.draft_path), "--confirm")
        self.assertEqual(code, 0, err)
        tree = store.read_tree(self.proj / "技术标")
        self.assertNotIn("expertPack", tree)                      # 无包 → 现状不变


def _find_presets_source():
    return Path(__file__).resolve().parents[2] / "共享资源" / "技术标风格" / "layout-presets.json"


if __name__ == "__main__":
    unittest.main()
