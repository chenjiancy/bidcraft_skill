# -*- coding: utf-8 -*-
"""M9 端到端测试（L3）：m9-verify / m9-evidence CLI 全链 ——
空项目 → 红灯（必做未做）；补齐 M4/M6/M7/M8/M10 闭环产物 → 绿灯 + 自检体检/投标留痕包
json/md/html 三件套落盘；红绿灯随产物状态动态翻转。
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

PROJECT = "T19端到端项目"
ENT = "T19端到端企业"


class M9VerifyE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.proj = self.root / ENT / "项目级" / PROJECT
        self.proj.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, *argv):
        import io as _io
        from contextlib import redirect_stdout, redirect_stderr
        out, err, code = _io.StringIO(), _io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", ENT] + list(argv))
            except SystemExit as e:
                code = e.code or 0
        return code, out.getvalue(), err.getvalue()

    def _verify_json(self):
        return json.loads((self.proj / "自检" / ("自检体检_%s.json" % PROJECT)).read_text(encoding="utf-8"))

    def test_red_then_green(self):
        # —— 空项目：红灯 ——
        code, out, err = self._run("m9-verify", "--project", PROJECT)
        self.assertEqual(code, 0, "%s|%s" % (out, err))
        doc = self._verify_json()
        self.assertEqual(doc["总评"], "红灯")
        self.assertIn("红灯", out)

        # —— 补齐 M4/M6 ——
        tdir = self.proj / "招标解析"; tdir.mkdir(parents=True)
        (tdir / ("投标要点_%s.json" % PROJECT)).write_text(json.dumps({"project": PROJECT}), encoding="utf-8")
        (tdir / ("素材清单_%s.json" % PROJECT)).write_text(json.dumps({"project": PROJECT}), encoding="utf-8")
        tech = self.proj / "技术标"; tech.mkdir(parents=True)
        (tech / "设置.json").write_text(json.dumps({"bidMode": "明标"}), encoding="utf-8")
        outd = tech / "产出"; outd.mkdir(parents=True)
        (outd / ("技术标_%s.docx" % PROJECT)).write_bytes(b"\x00docx")

        # —— 补齐 M7 检查（全过）——
        cdir = self.proj / "标书检查"; cdir.mkdir(parents=True)
        (cdir / ("机器检查_%s_技术标.json" % PROJECT)).write_text(json.dumps(
            {"kind": "tech", "检查": [{"id": "t", "ok": True, "issues": []}]}), encoding="utf-8")

        # —— 补齐 M8 评标（无失分）——
        sdir = self.proj / "模拟评标"; sdir.mkdir(parents=True)
        (sdir / ("模拟评标_%s.json" % PROJECT)).write_text(json.dumps(
            {"summary": {"issues": []}}), encoding="utf-8")

        # —— 补齐 M10 闭环 ——
        (sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "tasks": [{"id": "C01", "标题": "x", "完成状态": "已完成"}]}), encoding="utf-8")
        (sdir / ("补救后重检报告_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "summary": {"已勾选任务": 1, "验证通过": 1}}), encoding="utf-8")

        # —— 补齐后：绿灯 ——
        code, out, err = self._run("m9-verify", "--project", PROJECT)
        self.assertEqual(code, 0, err)
        doc = self._verify_json()
        self.assertEqual(doc["总评"], "绿灯")
        self.assertIn("绿灯", out)
        # 三件套落盘
        for ext in ("json", "md", "html"):
            p = self.proj / "自检" / ("自检体检_%s.%s" % (PROJECT, ext))
            self.assertTrue(p.is_file(), p)

        # —— 留痕包 ——
        code, out, err = self._run("m9-evidence", "--project", PROJECT)
        self.assertEqual(code, 0, "%s|%s" % (out, err))
        ev = json.loads((self.proj / "自检" / ("投标留痕包_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(ev["总评"], "绿灯")
        self.assertEqual(ev["KPI"]["任务完成率"], "1/1")
        self.assertEqual(ev["KPI"]["重检通过率"], "1/1")
        for ext in ("json", "md", "html"):
            self.assertTrue((self.proj / "自检" / ("投标留痕包_%s.%s" % (PROJECT, ext))).is_file())
        html = (self.proj / "自检" / ("投标留痕包_%s.html" % PROJECT)).read_text(encoding="utf-8")
        self.assertIn("全过程产物索引", html)


if __name__ == "__main__":
    unittest.main()
