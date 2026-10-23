# -*- coding: utf-8 -*-
"""M6 技术标制作 · CLI 第二批（T5）：tech-parse / tech-check / tech-report。"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft                                     # noqa: E402
from _shared import core                            # noqa: E402
from m6_tech import store                           # noqa: E402
from test_m6_cli import PROJECT, _draft, _material, _points   # noqa: E402

BLOCK = ('\n\n<!-- M6-COVERAGE\n'
         '{"keyPoints":[{"point":"监理大纲","covered":true}],'
         '"missingMaterials":[],"notes":"结构完整"}\n-->\n')


def _body(chars=2400, tail=""):
    """≥ ch-01 预算 3000×0.7=2100 字的正文（CJK 计数）。"""
    return "# 1 工程概况与监理范围\n\n" + "监理大纲" * (chars // 4) + tail + BLOCK


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ent, _ = core.Library(self.root).init_enterprise("企业A")
        self.proj = self.ent / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        self._write_points(_points())
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps(_material(), ensure_ascii=False), encoding="utf-8")
        self.draft_path = self.proj / "章节树草案.json"
        self.draft_path.write_text(json.dumps(_draft(), ensure_ascii=False), encoding="utf-8")
        self.md_path = self.proj / "草稿_ch-01.md"

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    def _write_points(self, obj):
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps(obj, ensure_ascii=False), encoding="utf-8")

    def _run(self, *argv):
        out, err, code = io.StringIO(), io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", "企业A"] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _tech(self):
        return store.tech_path(self.ent, PROJECT)

    def _ready(self, bid_mode="明标", confirm=True):
        if bid_mode != "明标":
            self._write_points(_points(bid_mode=bid_mode))
        self.assertEqual(self._run("tech-init", "--project", PROJECT)[0], 0)
        args = ["tech-outline", "--project", PROJECT, "--file", str(self.draft_path)]
        if confirm:
            args.append("--confirm")
        self.assertEqual(self._run(*args)[0], 0)

    def _ctx(self, cid="ch-01"):
        code, out, err = self._run("tech-ctx", "--project", PROJECT, "--chapter", cid)
        self.assertEqual(code, 0, out + err)

    def _write_md(self, text):
        self.md_path.write_text(text, encoding="utf-8")
        return self.md_path

    def _parse(self, text=None):
        self._write_md(_body() if text is None else text)
        return self._run("tech-parse", "--project", PROJECT,
                         "--chapter", "ch-01", "--file", str(self.md_path))

    def _state(self, cid="ch-01"):
        return store.find_chapter(store.read_tree(self._tech()), cid)["status"]

    # -- tech-parse ------------------------------------------------------
    def test_parse_requires_gate(self):
        self._ready(confirm=False)
        code, _, err = self._parse()
        self.assertEqual(code, 1)
        self.assertIn("闸门①未确认", err)

    def test_parse_requires_ctx(self):
        self._ready()
        code, _, err = self._parse()
        self.assertEqual(code, 1)
        self.assertIn("尚无上下文包", err)

    def test_parse_writes_body_and_selfcheck(self):
        self._ready()
        self._ctx()
        code, out, err = self._parse()
        self.assertEqual(code, 0, out + err)
        tech = self._tech()
        text = store.read_chapter_body(tech, store.find_chapter(store.read_tree(tech), "ch-01"))
        self.assertNotIn("M6-COVERAGE", text)
        self.assertIn("监理大纲", text)
        sc = store.read_selfcheck(tech, "ch-01")
        self.assertEqual(sc["block"], "M6-COVERAGE")
        self.assertEqual(self._state(), "WRITTEN")
        self.assertEqual(store.read_state(tech, "ch-01")["status"], "WRITTEN")

    def test_parse_rejects_short_body_then_recovers(self):
        self._ready()
        self._ctx()
        code, _, err = self._parse("# 短\n\n内容不足" + BLOCK)
        self.assertEqual(code, 1)
        self.assertIn("篇幅不足", err)
        self.assertEqual(self._state(), "FAILED")
        tech = self._tech()
        ch = store.find_chapter(store.read_tree(tech), "ch-01")
        with self.assertRaises(core.LibraryError):
            store.read_chapter_body(tech, ch)       # 未落盘
        code, out, err = self._parse()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(), "WRITTEN")

    def test_parse_rejects_template_placeholder(self):
        self._ready()
        self._ctx()
        code, _, err = self._parse(_body(tail="\n\n{{占位}}\n"))
        self.assertEqual(code, 1)
        self.assertIn("模板占位", err)
        self.assertEqual(self._state(), "FAILED")

    def test_parse_allows_tian_dai(self):
        self._ready()
        self._ctx()
        code, out, err = self._parse(_body(tail="\n\n资质编号：{{待填:资质证书编号}}\n"))
        self.assertEqual(code, 0, out + err)
        self.assertIn("缺料披露", out)
        self.assertEqual(self._state(), "WRITTEN")

    def test_parse_rejects_sensitive_in_anbiao(self):
        self._ready(bid_mode="暗标")
        self._ctx()
        code, _, err = self._parse(_body(tail="\n\n本项目由企业A承担。\n"))
        self.assertEqual(code, 1)
        self.assertIn("敏感词", err)
        self.assertEqual(self._state(), "FAILED")

    def test_parse_missing_selfcheck_block(self):
        self._ready()
        self._ctx()
        code, _, err = self._parse("监理大纲" * 600 + "\n")
        self.assertEqual(code, 1)
        self.assertIn("未找到自述块", err)

    # -- tech-check ------------------------------------------------------
    def test_check_after_parse(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        code, out, err = self._run("tech-check", "--project", PROJECT)
        self.assertEqual(code, 0, out + err)
        tech = self._tech()
        jp = tech / ("检查/覆盖矩阵_%s.json" % PROJECT)
        mp = tech / ("检查/覆盖矩阵_%s.md" % PROJECT)
        self.assertTrue(jp.is_file())
        self.assertTrue(mp.is_file())
        doc = json.loads(jp.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "m6.check/v1")
        self.assertTrue(doc["ok"])
        self.assertEqual(len(doc["coverage"]["rows"]), 3)
        self.assertTrue(doc["chapters"]["ch-01"]["body"])
        self.assertFalse(doc["chapters"]["ch-02"]["body"])
        self.assertEqual(self._state(), "CHECKED")

    def test_check_blocks_on_sensitive_error(self):
        self._ready(bid_mode="暗标")
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        tech = self._tech()
        ch = store.find_chapter(store.read_tree(tech), "ch-01")
        store.write_chapter_body(tech, ch, "企业A" + "监理大纲" * 600 + "\n")
        code, out, _ = self._run("tech-check", "--project", PROJECT)
        self.assertEqual(code, 1)
        doc = json.loads((tech / ("检查/覆盖矩阵_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertFalse(doc["ok"])
        codes = [i["code"] for i in doc["issues"]]
        self.assertIn("A4.sensitive", codes)
        self.assertEqual(self._state(), "WRITTEN")     # 不推进

    # -- tech-report -----------------------------------------------------
    def test_report_requires_check(self):
        self._ready()
        code, _, err = self._run("tech-report", "--project", PROJECT)
        self.assertEqual(code, 1)
        self.assertIn("请先 tech-check", err)

    def test_report_and_confirm_gate(self):
        self._ready()
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 0)
        code, out, err = self._run("tech-report", "--project", PROJECT, "--confirm")
        self.assertEqual(code, 0, out + err)
        tech = self._tech()
        hp = tech / ("检查/技术标检查报告_%s.html" % PROJECT)
        self.assertTrue(hp.is_file())
        html = hp.read_text(encoding="utf-8")
        self.assertIn("技术标检查报告", html)
        self.assertIn("闸门② 裁决区", html)
        self.assertNotIn("http://", html)
        tree = store.read_tree(tech)
        self.assertEqual(tree["confirmLog"][-1]["gate"], "write")
        self.assertEqual(self._state(), "CONFIRMED")

    def test_report_confirm_rejects_errors_then_force(self):
        self._ready(bid_mode="暗标")
        self._ctx()
        self.assertEqual(self._parse()[0], 0)
        tech = self._tech()
        ch = store.find_chapter(store.read_tree(tech), "ch-01")
        store.write_chapter_body(tech, ch, "企业A" + "监理大纲" * 600 + "\n")
        self.assertEqual(self._run("tech-check", "--project", PROJECT)[0], 1)
        code, _, err = self._run("tech-report", "--project", PROJECT, "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("--force", err)
        code, out, _ = self._run("tech-report", "--project", PROJECT, "--confirm", "--force")
        self.assertEqual(code, 0, out)
        tree = store.read_tree(tech)
        self.assertEqual(tree["confirmLog"][-1]["gate"], "write")
        self.assertIn("--force", tree["confirmLog"][-1]["note"])


if __name__ == "__main__":
    unittest.main()
