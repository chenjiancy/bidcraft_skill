# -*- coding: utf-8 -*-
"""M9 T20 端到端测试：m9-verify --all CLI 行为 ——
--project 与 --all 互斥校验（同传报错）；无项目 → 汇总 0 项目；补齐两项目 →
企业汇总 json/md/html 三件套 + 汇总结论分级正确。
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

ENT = "T20端到端企业"
PROJ_X = "X项目"
PROJ_Y = "Y项目"


def _mk(root, name, full):
    proj = root / ENT / "项目级" / name
    tdir = proj / "招标解析"; tdir.mkdir(parents=True)
    (tdir / ("投标要点_%s.json" % name)).write_text(json.dumps({"project": name}), encoding="utf-8")
    (tdir / ("素材清单_%s.json" % name)).write_text(json.dumps({"project": name}), encoding="utf-8")
    tech = proj / "技术标"; tech.mkdir(parents=True)
    (tech / "设置.json").write_text(json.dumps({"bidMode": "明标"}), encoding="utf-8")
    outd = tech / "产出"; outd.mkdir(parents=True)
    (outd / ("技术标_%s.docx" % name)).write_bytes(b"\x00docx")
    if full:
        cdir = proj / "标书检查"; cdir.mkdir(parents=True)
        (cdir / ("机器检查_%s_技术标.json" % name)).write_text(json.dumps(
            {"kind": "tech", "检查": [{"id": "t", "ok": True, "issues": []}]}), encoding="utf-8")
        sdir = proj / "模拟评标"; sdir.mkdir(parents=True)
        (sdir / ("模拟评标_%s.json" % name)).write_text(json.dumps({"summary": {"issues": []}}), encoding="utf-8")
        (sdir / ("失分补救任务单_%s.json" % name)).write_text(json.dumps(
            {"project": name, "tasks": [{"id": "C01", "完成状态": "已完成"}]}), encoding="utf-8")
        (sdir / ("补救后重检报告_%s.json" % name)).write_text(json.dumps(
            {"project": name, "summary": {"已勾选任务": 1, "验证通过": 1}}), encoding="utf-8")


class M9VerifyAllE2ETest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)

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

    def test_all_cli_behavior(self):
        # 1) --project 与 --all 互斥：同传报错（SystemExit 2）
        import io as _io
        from contextlib import redirect_stdout, redirect_stderr
        out, err, code = _io.StringIO(), _io.StringIO(), 0
        with redirect_stdout(out), redirect_stderr(err):
            try:
                bidcraft.main(["--root", str(self.root), "--enterprise", ENT,
                               "m9-verify", "--project", PROJ_X, "--all"])
            except SystemExit as e:
                code = e.code or 0
        self.assertNotEqual(code, 0)

        # 2) 空企业 → 0 项目汇总
        code, out, err = self._run("m9-verify", "--all")
        self.assertEqual(code, 0, err)
        agg = json.loads((self.root / ENT / "自检" / ("企业体检汇总_%s.json" % ENT)).read_text(encoding="utf-8"))
        self.assertEqual(agg["summary"]["项目总数"], 0)

        # 3) 两项目（X 闭环绿灯 / Y 半程红灯）→ 汇总 1绿1红
        _mk(self.root, PROJ_X, True)
        _mk(self.root, PROJ_Y, False)
        code, out, err = self._run("m9-verify", "--all")
        self.assertEqual(code, 0, "%s|%s" % (out, err))
        agg = json.loads((self.root / ENT / "自检" / ("企业体检汇总_%s.json" % ENT)).read_text(encoding="utf-8"))
        s = agg["summary"]
        self.assertEqual((s["项目总数"], s["绿灯"], s["红灯"]), (2, 1, 1))
        by = {r["project"]: r for r in agg["projects"]}
        self.assertEqual(by[PROJ_Y]["总评"], "红灯")
        # 4) 三件套落盘
        for ext in ("json", "md", "html"):
            p = self.root / ENT / "自检" / ("企业体检汇总_%s.%s" % (ENT, ext))
            self.assertTrue(p.is_file(), p)
        md = (self.root / ENT / "自检" / ("企业体检汇总_%s.md" % ENT)).read_text(encoding="utf-8")
        self.assertIn("| 项目 |", md)
        self.assertIn("🔴 红灯", md)


if __name__ == "__main__":
    unittest.main()
