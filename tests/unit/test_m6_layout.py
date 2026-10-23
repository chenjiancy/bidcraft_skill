# -*- coding: utf-8 -*-
"""M6 技术标制作 · 排版预设（T13）单测：预设文件 / 读取 / F11 校验 / tech-layout。"""
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
from m6_tech import layout, rules   # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PRESETS = REPO / "共享资源" / "技术标风格" / "layout-presets.json"
HEX = ("primary", "accent", "heading", "tableFill", "coverBg")


def _doc():
    return json.loads(PRESETS.read_text(encoding="utf-8"))


class PresetFileTest(unittest.TestCase):
    """共享级预设文件是 T13 的交付物，结构须与契约 §3.2 对齐。"""

    def test_file_exists(self):
        self.assertTrue(PRESETS.is_file(), "缺共享级 %s" % PRESETS)

    def test_schema_and_counts(self):
        doc = _doc()
        self.assertEqual(doc.get("schema"), layout.PRESETS_SCHEMA)
        for group in ("preset", "palette", "cover", "decoration", "font",
                      "imageRatio", "imageRule", "imageLayout",
                      "pageSetup", "headingSystem", "tocStyle",
                      "tableStyle", "captionSystem", "paragraphStyle",
                      "headerFooter"):
            self.assertEqual(len(layout.entries(doc, group)), 10, group)

    def test_ids_match_builtin(self):
        doc = _doc()
        for group in ("preset", "palette", "cover", "decoration", "font",
                      "imageRatio", "imageRule", "imageLayout",
                      "pageSetup", "headingSystem", "tocStyle",
                      "tableStyle", "captionSystem", "paragraphStyle",
                      "headerFooter"):
            got = [r["id"] for r in layout.entries(doc, group)]
            self.assertEqual(got, list(rules.DEFAULT_LAYOUT[group]), group)

    def test_default_layout(self):
        doc = _doc()
        default = layout.default_entry(doc)
        self.assertEqual(default, {"preset": "single-column", "palette": "deep-indigo",
                                   "cover": "full-block", "decoration": "standard",
                                   "font": "gov-gongwen",
                                   "imageRatio": "mid", "imageRule": "hybrid",
                                   "imageLayout": "split-h",
                                   "pageSetup": "p1-standard-a4",
                                   "headingSystem": "h1-gbt-arabic",
                                   "tocStyle": "t1-jianyu-auto",
                                   "tableStyle": "tb1-three-line",
                                   "captionSystem": "c2-cy-chapter",
                                   "paragraphStyle": "pa7-jianyu-15",
                                   "headerFooter": "hf1-classic-enterprise"})

    def test_every_micro_row_has_id_and_note(self):
        doc = _doc()
        for group in ("pageSetup", "headingSystem", "tocStyle",
                      "tableStyle", "captionSystem", "paragraphStyle",
                      "headerFooter"):
            for row in layout.entries(doc, group):
                self.assertTrue(row.get("id"), "%s row missing id" % group)
                self.assertTrue(row.get("name"), "%s.%s missing name" % (group, row["id"]))
                self.assertTrue(row.get("note"), "%s.%s missing note" % (group, row["id"]))

    def test_every_palette_has_five_colors(self):
        doc = _doc()
        for row in layout.entries(doc, "palette"):
            for k in HEX:
                v = row.get(k)
                self.assertTrue(isinstance(v, str) and v.startswith("#") and len(v) == 7,
                                "%s.%s=%r" % (row["id"], k, v))
            self.assertTrue(row.get("name"))

    def test_gradient_palette_has_end_color(self):
        row = layout.palette_colors(_doc(), "gradient-blue-cyan")
        self.assertIsNotNone(row)
        self.assertTrue(row.get("coverBgEnd", "").startswith("#"))

    def test_image_underlay_disabled_for_dark(self):
        doc = _doc()
        cover = next(r for r in layout.entries(doc, "cover") if r["id"] == "image-underlay")
        self.assertFalse(cover.get("darkOk"))


class LoadAndValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "素材库"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self):
        return type("A", (), {"root": str(self.root)})()

    def _install(self, doc=None):
        d = self.root / "共享资源" / "技术标风格"
        d.mkdir(parents=True)
        p = d / layout.PRESETS_FILE
        p.write_text(json.dumps(doc if doc is not None else _doc(), ensure_ascii=False),
                     encoding="utf-8")
        return p

    def test_missing_returns_none(self):
        self.assertIsNone(layout.find_presets(self._args()))
        self.assertIsNone(layout.load_presets(self._args()))

    def test_find_and_load(self):
        p = self._install()
        self.assertEqual(layout.find_presets(self._args()), p)
        doc = layout.load_presets(self._args())
        self.assertEqual(len(layout.entries(doc, "palette")), 10)

    def test_bad_json_raises(self):
        p = self._install()
        p.write_text("[1,2]", encoding="utf-8")
        with self.assertRaises(Exception):
            layout.load_presets(self._args())

    def test_validate_layout_accepts_presets(self):
        self._install()
        doc = layout.load_presets(self._args())
        ok, issues = rules.validate_layout(layout.default_entry(doc), doc)
        self.assertTrue(ok, issues)

    def test_unknown_palette_rejected(self):
        self._install()
        doc = layout.load_presets(self._args())
        bad = dict(layout.default_entry(doc), palette="no-such-palette")
        ok, issues = rules.validate_layout(bad, doc)
        self.assertFalse(ok)
        self.assertIn("layout.unknown", [i["code"] for i in issues])

    def test_dark_mode_rejects_image_underlay(self):
        self._install()
        doc = layout.load_presets(self._args())
        bad = dict(layout.default_entry(doc), cover="image-underlay")
        ok, issues = rules.validate_layout(bad, doc, "暗标")
        self.assertFalse(ok)
        self.assertIn("layout.mixcover", [i["code"] for i in issues])


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "素材库"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root)] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_list_without_file_falls_back(self):
        code, out, _ = self._run("tech-layout", "--list")
        self.assertEqual(code, 0)
        self.assertIn("已回退内置清单", out)
        self.assertIn("deep-indigo", out)

    def test_list_reads_shared_file(self):
        d = self.root / "共享资源" / "技术标风格"
        d.mkdir(parents=True)
        (d / layout.PRESETS_FILE).write_text(
            json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
        code, out, _ = self._run("tech-layout", "--list")
        self.assertEqual(code, 0)
        self.assertIn("配色方案 · 10 种", out)
        self.assertIn("深靛蓝", out)
        self.assertIn("[默认]", out)
        self.assertIn("暗标禁用", out)

    def test_list_json(self):
        code, out, _ = self._run("tech-layout", "--list", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["default"]["palette"], "deep-indigo")
        self.assertEqual(len(payload["groups"]["palette"]), 10)
        self.assertEqual(len(payload["groups"]["headerFooter"]), 10)

    def test_preview_routes_to_export(self):
        """T10 已实现：--preview 直接渲染样张 docx（内置样例 fixture），不再报错。"""
        code, out, _ = self._run("tech-layout", "--preview", "single-column")
        self.assertEqual(code, 0)
        self.assertIn("技术标样张_single-column.docx", out)
        target = Path.cwd() / "技术标样张_single-column.docx"
        self.assertTrue(target.is_file())
        try:
            target.unlink()
        except OSError:
            pass

    def test_preview_unknown_preset(self):
        code, _, err = self._run("tech-layout", "--preview", "no-such-preset")
        self.assertEqual(code, 1)
        self.assertIn("版面范式不存在", err)

    def test_preview_real_project(self):
        """--preview + --project 走真实项目导出（覆盖 preset）。"""
        root2 = self.root
        d = root2 / "共享资源" / "技术标风格"
        d.mkdir(parents=True)
        (d / layout.PRESETS_FILE).write_text(
            json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
        ent = root2 / "测试企业"
        tech = ent / "项目级" / "演示项目" / "技术标"
        for dd in ("章节", "章节/.meta", "产出"):
            (tech / dd).mkdir(parents=True, exist_ok=True)
        (tech / "章节" / "ch-01").mkdir(parents=True, exist_ok=True)
        tree = {"schema": "m6.tree/v1", "project": "演示项目", "confirmed": True,
                "chapters": [{"id": "ch-01", "title": "第一章", "status": "WRITTEN",
                              "files": {"body": "章节/ch-01/正文.md"}}]}
        (tech / "章节树.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")
        (tech / "章节" / "ch-01" / "正文.md").write_text(
            "# 一、概况\n\n演示项目正文。\n", encoding="utf-8")
        code, _, err = self._run(
            "tech-layout", "--preview", "single-column", "--project", "演示项目",
            "--enterprise", "测试企业")
        self.assertEqual(code, 0, err)
        self.assertTrue((tech / "产出" / "技术标_演示项目.docx").is_file())


class ApplyComboTest(unittest.TestCase):
    """版面设计器「存组合」闭环：组合补丁 → 专家包（dry-run / confirm / 非法回绝）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "素材库"
        self.root.mkdir()
        self.shared = self.root / "共享资源" / "技术标风格"
        self.shared.mkdir(parents=True)
        (self.shared / layout.PRESETS_FILE).write_text(
            json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
        # 模板 taxonomy：复制官方包（apply-combo 以此为模板生成新包）
        tax = REPO / "共享资源" / "技术标风格" / "专家包" / "official-tech" / "taxonomy.json"
        if tax.is_file():
            (self.shared / "专家包" / "official-tech").mkdir(parents=True, exist_ok=True)
            (self.shared / "专家包" / "official-tech" / "taxonomy.json").write_text(
                tax.read_text(encoding="utf-8"), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _patch(self, layout_override=None, name="测试组合"):
        combo = dict(_doc()["default"])
        if layout_override:
            combo.update(layout_override)
        p = self.root / "组合补丁_测试.json"
        p.write_text(json.dumps({
            "schema": "m6.layout-designer/v1", "version": "1.2", "kind": "combo-patch",
            "name": name, "bidMode": "明标", "layout": combo,
        }, ensure_ascii=False), encoding="utf-8")
        return p

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root)] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def test_dry_run_does_not_write(self):
        p = self._patch()
        code, out, _ = self._run("tech-layout", "--apply-combo", str(p))
        self.assertEqual(code, 0)
        self.assertIn("[DRY-RUN]", out)
        self.assertFalse((self.shared / "专家包" / "custom-single-column-deep-indigo").exists())

    def test_confirm_generates_pack_and_reads_back(self):
        p = self._patch({"palette": "steel-cyan", "decoration": "rich"})
        code, out, _ = self._run("tech-layout", "--apply-combo", str(p), "--confirm")
        self.assertEqual(code, 0, out)
        self.assertIn("已生成专家包", out)
        pdir = self.shared / "专家包" / "custom-single-column-steel-cyan"
        self.assertTrue((pdir / "包.json").is_file())
        self.assertTrue((pdir / "taxonomy.json").is_file())
        m = json.loads((pdir / "包.json").read_text(encoding="utf-8"))
        self.assertEqual(m["schema"], "m6.expert-pack/v1")
        self.assertEqual(m["id"], "custom-single-column-steel-cyan")
        self.assertEqual(m["layoutCombo"]["palette"], "steel-cyan")
        self.assertEqual(m["layoutCombo"]["decoration"], "rich")
        self.assertEqual(len(m["layoutCombo"]), 15)
        t = json.loads((pdir / "taxonomy.json").read_text(encoding="utf-8"))
        self.assertEqual(t["pack"], "custom-single-column-steel-cyan")

    def test_explicit_pack_id(self):
        p = self._patch(name="我的组合")
        code, out, _ = self._run("tech-layout", "--apply-combo", str(p),
                                 "--pack-id", "custom-mine", "--confirm")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.shared / "专家包" / "custom-mine" / "包.json").is_file())
        m = json.loads((self.shared / "专家包" / "custom-mine" / "包.json").read_text(encoding="utf-8"))
        self.assertEqual(m["name"], "我的组合")

    def test_unknown_id_rejected(self):
        p = self._patch({"palette": "no-such"})
        code, _, err = self._run("tech-layout", "--apply-combo", str(p))
        self.assertEqual(code, 1)
        self.assertIn("组合校验未通过", err)

    def test_missing_layout_rejected(self):
        p = self.root / "组合补丁_bad.json"
        p.write_text(json.dumps({"schema": "m6.layout-designer/v1", "name": "x"},
                                ensure_ascii=False), encoding="utf-8")
        code, _, err = self._run("tech-layout", "--apply-combo", str(p))
        self.assertEqual(code, 1)
        self.assertIn("缺少 layout", err)

    def test_outline_applies_pack_combo(self):
        """设计器闭环端到端：专家包 layoutCombo 经 tech-outline 落盘章节树。"""
        p = self._patch({"palette": "steel-cyan", "decoration": "rich"})
        code, _, err = self._run("tech-layout", "--apply-combo", str(p), "--confirm")
        self.assertEqual(code, 0, err)
        code, _, err = self._run("init-enterprise", "--name", "企业A")
        self.assertEqual(code, 0, err)
        proj = self.root / "企业A" / "项目级" / "演示项目"
        (proj / "技术标" / "章节").mkdir(parents=True)
        (proj / "招标解析").mkdir(parents=True)
        (proj / "招标解析" / "投标要点_演示项目.json").write_text(json.dumps({
            "project": "演示项目",
            "modules": [
                {"id": "basic", "title": "项目基本信息", "type": "fields",
                 "fields": {"项目名称": {"value": "演示项目", "evidence": "e"}}},
                {"id": "project_overview", "title": "项目概况", "type": "fields",
                 "fields": {"项目概况": {"value": "演示项目为公共建筑", "evidence": "e"}}},
                {"id": "scoring", "title": "评分办法", "type": "score_items",
                 "score_items": [{"item": "监理大纲", "weight": 50, "unit": "分", "evidence": "e"}]},
                {"id": "reject", "title": "废标红线", "type": "items",
                 "items": [{"type": "格式", "rule": "技术标总页数不超过 60 页；按明标编制",
                            "evidence": "e"}]},
            ]}, ensure_ascii=False), encoding="utf-8")
        code, _, err = self._run("tech-init", "--project", "演示项目")
        self.assertEqual(code, 0, err)
        draft = proj / "技术标" / "章节树草案.json"
        draft.write_text(json.dumps({
            "schema": "m6.tree/v1", "project": "演示项目",
            "chapters": [{"id": "ch-01", "no": "1", "title": "工程概况与监理范围", "level": 1,
                          "scoreRefs": [{"idx": 0, "item": "监理大纲", "weight": 50}],
                          "keyPoints": ["监理大纲"], "wordCnt": 3000,
                          "dependsOnMaterials": ["project_overview"]}],
        }, ensure_ascii=False), encoding="utf-8")
        code, _, err = self._run("tech-outline", "--project", "演示项目", "--file", str(draft),
                                 "--expert-pack", "custom-single-column-steel-cyan", "--confirm")
        self.assertEqual(code, 0, err)
        tree = json.loads((proj / "技术标" / "章节树.json").read_text(encoding="utf-8"))
        self.assertEqual(tree["layout"]["palette"], "steel-cyan")
        self.assertEqual(tree["layout"]["decoration"], "rich")
        self.assertEqual(tree["expertPack"]["id"], "custom-single-column-steel-cyan")


if __name__ == "__main__":
    unittest.main()
