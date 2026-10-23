# -*- coding: utf-8 -*-
"""M6 模板设计器（P0）单测：template.json 数据模型、校验、暗标派生与 tpl-design 命令。"""
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

import bidcraft                     # noqa: E402
from m6_tech import layout, rules, sources, tpl_design   # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PRESETS = REPO / "共享资源" / "技术标风格" / "layout-presets.json"


def _doc():
    return json.loads(PRESETS.read_text(encoding="utf-8"))


def _issues_of(ok, issues, code):
    return [i for i in issues if i["code"] == code]


def _errs(issues):
    return [i for i in issues if i["level"] == "err"]


def _warns(issues):
    return [i for i in issues if i["level"] == "warn"]


class SchemaConstantsTest(unittest.TestCase):
    def test_schema_and_parts(self):
        self.assertEqual(tpl_design.TEMPLATE_SCHEMA, "m6.template/v1")
        self.assertEqual(tpl_design.PART_IDS, ("cover", "colophon", "toc", "body", "closing"))
        self.assertEqual(tpl_design.REQUIRED_PARTS, ("cover", "body"))

    def test_example_template_valid(self):
        ok, issues = tpl_design.validate_template(tpl_design.TEMPLATE_EXAMPLE, _doc())
        self.assertTrue(ok, issues)
        self.assertEqual(_errs(issues), [])

    def test_example_file_on_disk_matches_module(self):
        p = REPO / "共享资源" / "技术标风格" / "模板" / "示例-标准技术标.json"
        self.assertTrue(p.is_file(), "缺示例模板 %s" % p)
        on_disk = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, tpl_design.TEMPLATE_EXAMPLE)


class ValidateStructureTest(unittest.TestCase):
    def _base(self):
        doc = json.loads(json.dumps(tpl_design.TEMPLATE_EXAMPLE))
        return doc

    def test_empty_structure(self):
        doc = self._base()
        doc["structure"] = []
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertEqual(_issues_of(ok, issues, "struct-empty")[0]["level"], "err")

    def test_missing_body(self):
        doc = self._base()
        doc["structure"] = [s for s in doc["structure"] if s["part"] != "body"]
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-missing", [i["code"] for i in _errs(issues)])

    def test_cover_not_first(self):
        doc = self._base()
        doc["structure"] = [s for s in doc["structure"] if s["part"] != "cover"]
        doc["structure"].insert(1, {"part": "cover", "pageMode": "single"})
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-cover-first", [i["code"] for i in _errs(issues)])

    def test_duplicate_part(self):
        doc = self._base()
        doc["structure"].insert(2, {"part": "body", "pageMode": "flow"})
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-dup", [i["code"] for i in _errs(issues)])

    def test_order_toc_before_body(self):
        doc = self._base()
        doc["structure"] = [
            {"part": "cover", "pageMode": "single"},
            {"part": "body", "pageMode": "flow"},
            {"part": "toc", "pageMode": "single"},
        ]
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-order", [i["code"] for i in _errs(issues)])

    def test_bad_page_mode(self):
        doc = self._base()
        doc["structure"][0]["pageMode"] = "double"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-pagemode", [i["code"] for i in _errs(issues)])

    def test_unknown_part(self):
        doc = self._base()
        doc["structure"].insert(2, {"part": "appendix", "pageMode": "single"})
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("struct-part", [i["code"] for i in _errs(issues)])


class ValidateStyleRefTest(unittest.TestCase):
    def _base(self):
        return json.loads(json.dumps(tpl_design.TEMPLATE_EXAMPLE))

    def test_unknown_group_key(self):
        doc = self._base()
        doc["styleRef"]["coverStyle"] = "x"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("style-key", [i["code"] for i in _errs(issues)])

    def test_unknown_id(self):
        doc = self._base()
        doc["styleRef"]["preset"] = "no-such-preset"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("style-id", [i["code"] for i in _errs(issues)])

    def test_partial_style_ref_ok(self):
        doc = self._base()
        doc["styleRef"] = {"preset": "two-column", "palette": "pine-green"}
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertTrue(ok, issues)
        layout, _ = tpl_design.dark_derived(doc, _doc())
        self.assertEqual(layout["preset"], "two-column")
        self.assertEqual(layout["palette"], "pine-green")
        # 缺省键回默认
        self.assertEqual(layout["cover"], sources.DEFAULT_LAYOUT["cover"])

    def test_style_ref_type_error(self):
        doc = self._base()
        doc["styleRef"] = "not-a-dict"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("style-type", [i["code"] for i in _errs(issues)])


class ValidatePlaceholdersAndRulesTest(unittest.TestCase):
    def _base(self):
        return json.loads(json.dumps(tpl_design.TEMPLATE_EXAMPLE))

    def test_bad_placeholder_key(self):
        doc = self._base()
        doc["placeholders"]["企业名称"] = "{{ x }}"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("ph-key", [i["code"] for i in _errs(issues)])

    def test_bad_placeholder_value(self):
        doc = self._base()
        doc["placeholders"]["ok1"] = "随便一段文字"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("ph-val", [i["code"] for i in _errs(issues)])

    def test_placeholder_image_ok(self):
        doc = self._base()
        doc["placeholders"]["cert"] = "【图片占位：证书】"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertTrue(ok, issues)

    def test_bad_bid_mode(self):
        doc = self._base()
        doc["rules"]["bidMode"] = "半明半暗"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("rules-bidmode", [i["code"] for i in _errs(issues)])

    def test_unknown_rule_warns(self):
        doc = self._base()
        doc["rules"]["forcePageBreak"] = True
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertTrue(ok, issues)  # 未知键仅提示
        self.assertIn("rules-key", [i["code"] for i in _warns(issues)])


class DarkDerivedTest(unittest.TestCase):
    def _base(self):
        return json.loads(json.dumps(tpl_design.TEMPLATE_EXAMPLE))

    def test_light_mode_no_derivation(self):
        doc = self._base()
        layout, notes = tpl_design.dark_derived(doc, _doc())
        self.assertEqual(notes, [])
        self.assertEqual(layout["font"], "gov-gongwen")

    def test_dark_forced_font(self):
        doc = self._base()
        doc["rules"]["bidMode"] = "暗标"
        doc["styleRef"]["font"] = "gov-gongwen"          # 非 dark-safe → 强制
        doc["styleRef"]["imageRule"] = "hybrid"           # 非二选一 → 降级 no-source
        doc["styleRef"]["headerFooter"] = "hf1-classic-enterprise"  # 非二选一 → 降级 hf9-dark-none
        layout, notes = tpl_design.dark_derived(doc, _doc())
        self.assertEqual(layout["font"], tpl_design.DARK_FONT_ID)
        self.assertEqual(layout["imageRule"], "no-source")
        self.assertEqual(layout["headerFooter"], "hf9-dark-none")
        self.assertTrue(any("font" in n for n in notes))
        self.assertTrue(any("imageRule" in n for n in notes))
        self.assertTrue(any("headerFooter" in n for n in notes))

    def test_dark_allowed_values_kept(self):
        doc = self._base()
        doc["rules"]["bidMode"] = "暗标"
        doc["styleRef"]["font"] = tpl_design.DARK_FONT_ID
        doc["styleRef"]["imageRule"] = "dark-safe-img"
        doc["styleRef"]["headerFooter"] = "hf10-dark-page-only"
        layout, notes = tpl_design.dark_derived(doc, _doc())
        self.assertEqual(layout["font"], tpl_design.DARK_FONT_ID)
        self.assertEqual(layout["imageRule"], "dark-safe-img")
        self.assertEqual(layout["headerFooter"], "hf10-dark-page-only")
        # 微观六组在 styleRef 显式指定时仅提示（按默认注入），不改变派生值
        self.assertTrue(all(n.startswith("暗标：") for n in notes))
        for g in tpl_design.DARK_INJECTED_GROUPS:
            self.assertEqual(layout[g], sources.DEFAULT_LAYOUT[g])

    def test_dark_compliance_errors(self):
        doc = self._base()
        doc["rules"]["bidMode"] = "暗标"
        doc["styleRef"]["font"] = "gov-gongwen"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertFalse(ok)
        self.assertIn("dark-font", [i["code"] for i in _errs(issues)])

    def test_dark_micro_injected(self):
        doc = self._base()
        doc["rules"]["bidMode"] = "暗标"
        doc["styleRef"]["font"] = tpl_design.DARK_FONT_ID
        doc["styleRef"]["imageRule"] = "dark-safe-img"
        doc["styleRef"]["headerFooter"] = "hf9-dark-none"
        doc["styleRef"]["headingSystem"] = "h1-gbt-arabic"
        ok, issues = tpl_design.validate_template(doc, _doc())
        self.assertTrue(ok, issues)  # 微观六组显式指定仅提示（将按默认注入）
        self.assertIn("dark-micro-inject", [i["code"] for i in issues])


class FileAndCmdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "素材库"
        self.root.mkdir()
        d = self.root / "共享资源" / "技术标风格"
        d.mkdir(parents=True)
        (d / layout.PRESETS_FILE).write_text(
            json.dumps(_doc(), ensure_ascii=False), encoding="utf-8")
        self.tpl_dir = d / "模板"
        self.tpl_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _args(self, **kw):
        base = {"root": str(self.root), "json": False, "confirm": False,
                "list": False, "show": "", "validate": "", "apply": "",
                "specimen": "", "project": "", "enterprise": ""}
        base.update(kw)
        return type("A", (), base)()

    def test_find_and_load(self):
        (self.tpl_dir / "示例-标准技术标.json").write_text(
            json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False), encoding="utf-8")
        args = self._args()
        self.assertEqual([p.name for p in tpl_design.find_templates(args)],
                         ["示例-标准技术标.json"])
        p, doc = tpl_design.load_template(args, "示例-标准技术标.json")
        self.assertEqual(doc["schema"], tpl_design.TEMPLATE_SCHEMA)
        # 绝对路径亦可
        p2, doc2 = tpl_design.load_template(args, str(p))
        self.assertEqual(doc2["name"], doc["name"])

    def test_load_missing_raises(self):
        with self.assertRaises(Exception):
            tpl_design.load_template(self._args(), "不存在.json")

    def test_cmd_list_json(self):
        out = StringIO()
        with redirect_stdout(out):
            rc = tpl_design.cmd_tpl_design(self._args(list=True, json=True))
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["schema"], tpl_design.TEMPLATE_SCHEMA)
        self.assertEqual(data["templates"], [])  # 空目录容错

    def test_cmd_show_valid(self):
        (self.tpl_dir / "示例-标准技术标.json").write_text(
            json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False), encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = tpl_design.cmd_tpl_design(self._args(show="示例-标准技术标.json", json=True))
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data["ok"])
        self.assertEqual(data["structure"][0]["part"], "cover")
        self.assertEqual(data["layout"]["preset"], "single-column")

    def test_cmd_validate_invalid(self):
        (self.tpl_dir / "坏模板.json").write_text(
            json.dumps({"schema": tpl_design.TEMPLATE_SCHEMA, "name": "坏",
                        "structure": [{"part": "cover", "pageMode": "single"}]},
                       ensure_ascii=False), encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = tpl_design.cmd_tpl_design(self._args(validate="坏模板.json", json=True))
        self.assertEqual(rc, 1)
        data = json.loads(out.getvalue())
        self.assertFalse(data["ok"])
        self.assertIn("struct-missing", [i["code"] for i in data["issues"]])

    def test_apply_requires_confirm(self):
        src = self.root.parent / "队列-新模板.json"
        src.write_text(json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False),
                       encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = tpl_design.cmd_tpl_design(self._args(apply=str(src)))
        self.assertEqual(rc, 0)
        self.assertIn("dry-run", out.getvalue())
        self.assertFalse((self.tpl_dir / "队列-新模板.json").exists())

    def test_apply_writes_and_reads_back(self):
        src = self.root.parent / "队列-新模板.json"
        src.write_text(json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False),
                       encoding="utf-8")
        out = StringIO()
        with redirect_stdout(out):
            rc = tpl_design.cmd_tpl_design(self._args(apply=str(src), confirm=True, json=True))
        self.assertEqual(rc, 0)
        data = json.loads(out.getvalue())
        self.assertTrue(data["ok"])
        target = Path(data["path"])
        self.assertEqual(target.parent, self.tpl_dir)
        self.assertTrue(target.is_file(), "落盘文件缺失")
        # 回读校验（load 再 validate）
        p2, doc2 = tpl_design.load_template(self._args(), str(target))
        ok, issues = tpl_design.validate_template(doc2, _doc())
        self.assertTrue(ok, issues)

    def test_apply_override_existing_raises(self):
        (self.tpl_dir / "示例-标准技术标.json").write_text(
            json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False), encoding="utf-8")
        src = self.root.parent / "示例-标准技术标.json"   # 同名 → 目标冲突防覆盖
        src.write_text(json.dumps(tpl_design.TEMPLATE_EXAMPLE, ensure_ascii=False),
                       encoding="utf-8")
        with self.assertRaises(Exception):
            tpl_design.cmd_tpl_design(self._args(apply=str(src), confirm=True))


if __name__ == "__main__":
    unittest.main()
