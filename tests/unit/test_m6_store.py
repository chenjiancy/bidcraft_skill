# -*- coding: utf-8 -*-
"""M6 技术标制作 · 存储层（T4）单测。"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core  # noqa: E402
from m6_tech import store  # noqa: E402

PROJECT = "和县2026"


def chapter(**kw):
    base = {
        "id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
        "scoreRefs": [{"idx": 0, "item": "监理大纲（30分）", "weight": 30}],
        "keyPoints": ["监理大纲完整性", "针对性", "监理范围"],
        "wordCnt": 3000, "dependsOnMaterials": ["project_overview"],
        "status": "PENDING", "files": {"body": "章节/ch-01.md", "meta": "章节/.meta/ch-01.json"},
    }
    base.update(kw)
    return base


def tree(**kw):
    base = {
        "schema": "m6.chapters/v1", "project": PROJECT, "bidMode": "明标",
        "pageConstraint": {"max": 80, "estimate": 72, "charsPerPage": 1000, "source": "招标文件"},
        "style": {"id": "strict", "name": "严谨正式", "promptRef": "styles.json#strict"},
        "layout": {"preset": "single-column", "palette": "deep-indigo",
                   "cover": "full-block", "decoration": "standard", "font": "gov-gongwen",
                   "imageRatio": "mid", "imageRule": "hybrid", "imageLayout": "split-h"},
        "terminology": {"招标人": "和县住建局", "项目名称": PROJECT},
        "personnel": [{"name": "张三", "post": "总监理工程师", "source": "素材清单#personnel[0]"}],
        "chapters": [chapter()],
    }
    base.update(kw)
    return base


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ent = Path(self.tmp.name) / "企业A"
        (self.ent / "项目级" / PROJECT).mkdir(parents=True)
        self.tech = store.ensure_tech_dir(self.ent, PROJECT)

    def tearDown(self):
        self.tmp.cleanup()

    # -- 目录 -------------------------------------------------------------
    def test_ensure_dirs(self):
        for sub in store.SUBDIRS:
            self.assertTrue((self.tech / sub).is_dir(), sub)

    def test_bad_project_name(self):
        with self.assertRaises(core.LibraryError):
            store.ensure_tech_dir(self.ent, "a/b")

    def test_missing_project(self):
        with self.assertRaises(core.LibraryError):
            store.ensure_tech_dir(self.ent, "不存在的项目")

    # -- 章节树 -----------------------------------------------------------
    def test_tree_roundtrip(self):
        store.write_tree(self.tech, tree())
        back = store.read_tree(self.tech)
        self.assertEqual(back["project"], PROJECT)
        self.assertEqual(len(store.list_chapters(back)), 1)

    def test_tree_missing(self):
        with self.assertRaises(core.LibraryError):
            store.read_tree(self.tech)

    def test_invalid_tree_not_overwrite(self):
        store.write_tree(self.tech, tree())
        bad = tree()
        bad["chapters"][0]["status"] = "DONE"
        with self.assertRaises(core.LibraryError):
            store.write_tree(self.tech, bad)
        self.assertEqual(store.read_tree(self.tech)["chapters"][0]["status"], "PENDING")

    def test_find_chapter_missing(self):
        with self.assertRaises(core.LibraryError):
            store.find_chapter(tree(), "ch-99")

    # -- 正文 -------------------------------------------------------------
    def test_body_roundtrip(self):
        ch = chapter()
        store.write_chapter_body(self.tech, ch, "# 一、工程概况\n正文")
        self.assertEqual(store.read_chapter_body(self.tech, ch), "# 一、工程概况\n正文")

    def test_empty_body_rejected(self):
        with self.assertRaises(core.LibraryError):
            store.write_chapter_body(self.tech, chapter(), "   ")

    def test_body_escape_rejected(self):
        ch = chapter(files={"body": "../evil.md", "meta": "章节/.meta/ch-01.json"})
        with self.assertRaises(core.LibraryError):
            store.write_chapter_body(self.tech, ch, "正文")
        self.assertFalse((self.tech.parent / "evil.md").exists())

    def test_rewrite_backup(self):
        ch = chapter()
        store.write_chapter_body(self.tech, ch, "旧正文")
        store.write_chapter_body(self.tech, ch, "新正文")
        backups = list((self.tech / store.TRASH_DIR).rglob("ch-01.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "旧正文")
        self.assertEqual(store.read_chapter_body(self.tech, ch), "新正文")

    def test_same_body_no_backup(self):
        ch = chapter()
        store.write_chapter_body(self.tech, ch, "同一正文")
        store.write_chapter_body(self.tech, ch, "同一正文")
        self.assertFalse((self.tech / store.TRASH_DIR).exists())

    # -- .meta ------------------------------------------------------------
    def test_context_pack_roundtrip(self):
        pack = {"schema": store.CTX_SCHEMA, "chapter": "ch-01", "scoreItems": []}
        store.write_context_pack(self.tech, "ch-01", pack)
        self.assertEqual(store.read_context_pack(self.tech, "ch-01"), pack)

    def test_context_pack_schema(self):
        with self.assertRaises(core.LibraryError):
            store.write_context_pack(self.tech, "ch-01", {"chapter": "ch-01"})

    def test_selfcheck_roundtrip(self):
        info = {"block": "M6-COVERAGE",
                "data": {"keyPoints": [{"point": "范围", "covered": True}],
                         "missingMaterials": [], "notes": ""}}
        store.write_selfcheck(self.tech, "ch-01", info)
        back = store.read_selfcheck(self.tech, "ch-01")
        self.assertEqual(back["block"], "M6-COVERAGE")
        self.assertEqual(back["chapter"], "ch-01")

    def test_selfcheck_missing_returns_none(self):
        self.assertIsNone(store.read_selfcheck(self.tech, "ch-01"))

    def test_state_invalid(self):
        with self.assertRaises(core.LibraryError):
            store.write_state(self.tech, "ch-01", "DONE")

    # -- 状态机 / 闸门 ----------------------------------------------------
    def test_advance_valid(self):
        store.write_tree(self.tech, tree())
        store.advance_chapter(self.tech, "ch-01", "CONTEXT_READY")
        self.assertEqual(store.read_tree(self.tech)["chapters"][0]["status"], "CONTEXT_READY")
        state = store.read_state(self.tech, "ch-01")
        self.assertEqual(state["status"], "CONTEXT_READY")
        self.assertEqual(len(state["history"]), 1)
        store.advance_chapter(self.tech, "ch-01", "WRITING")
        self.assertEqual(len(store.read_state(self.tech, "ch-01")["history"]), 2)

    def test_advance_invalid(self):
        store.write_tree(self.tech, tree())
        with self.assertRaises(core.LibraryError):
            store.advance_chapter(self.tech, "ch-01", "WRITTEN")
        self.assertEqual(store.read_tree(self.tech)["chapters"][0]["status"], "PENDING")
        self.assertIsNone(store.read_state(self.tech, "ch-01"))

    def test_confirm_gate_outline(self):
        store.write_tree(self.tech, tree())
        store.confirm_gate(self.tech, "outline", "已确认")
        t = store.read_tree(self.tech)
        self.assertTrue(t["confirmed"])
        self.assertEqual(t["confirmLog"][0]["gate"], "outline")
        self.assertTrue(store.outline_confirmed(t))

    def test_confirm_gate_invalid(self):
        store.write_tree(self.tech, tree())
        with self.assertRaises(core.LibraryError):
            store.confirm_gate(self.tech, "review")

    def test_outline_not_confirmed(self):
        self.assertFalse(store.outline_confirmed(tree()))

    # -- 通用读写 / 越界 --------------------------------------------------
    def test_write_text_inside(self):
        p = store.write_text_inside(self.tech, "检查/说明.md", "内容")
        self.assertEqual(p.read_text(encoding="utf-8"), "内容")

    def test_json_inside_roundtrip(self):
        store.write_json_inside(self.tech, "检查/覆盖矩阵.json", {"ok": True})
        self.assertEqual(store.read_json_inside(self.tech, "检查/覆盖矩阵.json"), {"ok": True})

    def test_json_inside_escape(self):
        with self.assertRaises(core.LibraryError):
            store.write_json_inside(self.tech, "../x.json", {"a": 1})
        with self.assertRaises(core.LibraryError):
            store.read_json_inside(self.tech, "../x.json")


if __name__ == "__main__":
    unittest.main()
