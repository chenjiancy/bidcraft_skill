# -*- coding: utf-8 -*-
"""M10 T21 集成测试（L2）：补救→M5 归档联动真实项目链路 ——
手写 M8 通道A 失分产物（kind=perf 缺业绩）→ remedy-gen（生成 R 类素材补齐任务）
→ remedy-done（勾选完成）→ remedy-archive（生成归档申请单，人工确认闸门）
→ 无 --confirm 拒绝 → --apply --confirm 应用（素材清单 performance 落点 + 任务单归档标记 + 归档记录三件套）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "scripts"))

import bidcraft  # noqa: E402

PROJECT = "T21集成项目"
ENT = "T21集成企业"


class M10ArchiveIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.proj = self.root / ENT / "项目级" / PROJECT
        self.tdir = self.proj / "招标解析"
        self.tdir.mkdir(parents=True)
        (self.tdir / ("投标要点_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT}, ensure_ascii=False), encoding="utf-8")
        (self.tdir / ("素材清单_%s.json" % PROJECT)).write_text(
            json.dumps({"project": PROJECT, "personnel": [{"name": "王监理", "role": "总监理工程师"}],
                        "企业基础信息": {"法定代表人姓名": "刘总", "企业名称": ENT},
                        "performance": [], "qualification_required": [],
                        "iso_certificates": [], "honors": [], "items": []},
                        ensure_ascii=False), encoding="utf-8")
        sdir = self.proj / "模拟评标"
        sdir.mkdir(parents=True)
        # M8 通道A 失分产物：缺同类业绩 → R 类 补业绩
        (sdir / ("模拟评标_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "standard": {"items": []},
             "summary": {"issues": [{"kind": "perf", "item": "近年同类监理业绩（每份3分）",
                                     "gap": 3.0, "advice": "未提供同类业绩扫描件", "evidence": "E1"}],
                         "可追分合计": 3.0, "客观分当前": 0, "客观分满分": 3.0}}, ensure_ascii=False),
            encoding="utf-8")

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

    def test_archive_full_chain(self):
        # 1) remedy-gen：生成 R01 素材补齐任务（补业绩）
        code, _, err = self._run("remedy-gen", "--project", PROJECT)
        self.assertEqual(code, 0, err)
        tp = self.proj / "模拟评标" / ("失分补救任务单_%s.json" % PROJECT)
        doc = json.loads(tp.read_text(encoding="utf-8"))
        r01 = next(t for t in doc["tasks"] if t["类型"] == "素材补齐" and t["动作"] == "补业绩")
        self.assertEqual(r01["涉及素材"]["category"], "业绩")
        self.assertNotIn("完成状态", r01)

        # 2) remedy-done：勾选完成
        code, out, err = self._run("remedy-done", "--project", PROJECT, "--id", r01["id"],
                                   "--note", "已归档业绩合同扫描件")
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        doc = json.loads(tp.read_text(encoding="utf-8"))
        done = next(t for t in doc["tasks"] if t["id"] == r01["id"])
        self.assertEqual(done["完成状态"], "已完成")

        # 3) remedy-archive：生成归档申请单（R01 在列）
        code, out, err = self._run("remedy-archive", "--project", PROJECT)
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        ap = self.proj / "模拟评标" / ("归档申请_%s.json" % PROJECT)
        adoc = json.loads(ap.read_text(encoding="utf-8"))
        entries = adoc["entries"]
        self.assertEqual([e["任务ID"] for e in entries], [r01["id"]])
        self.assertEqual(entries[0]["类别"], "业绩")
        self.assertEqual(entries[0]["状态"], "待确认")
        self.assertTrue((self.proj / "模拟评标" / ("归档申请_%s.html" % PROJECT)).is_file())
        self.assertTrue((self.proj / "模拟评标" / ("归档申请_%s.md" % PROJECT)).is_file())

        # 4) 无 --confirm → 拒绝（人工确认闸门）
        code, _, err = self._run("remedy-archive", "--project", PROJECT, "--apply")
        self.assertNotEqual(code, 0)
        self.assertIn("--confirm", err)
        # 素材清单未被写入
        mdoc = json.loads((self.tdir / ("素材清单_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(mdoc["performance"], [])

        # 5) --apply --confirm：应用归档
        code, out, err = self._run("remedy-archive", "--project", PROJECT, "--apply", "--confirm")
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        # 素材清单 performance 落点 + 来源标记
        mdoc = json.loads((self.tdir / ("素材清单_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        perf = mdoc["performance"]
        self.assertEqual(len(perf), 1)
        self.assertTrue(perf[0]["来源"].startswith("M10补救任务-%s" % r01["id"]))
        self.assertIn("归档时间", perf[0])
        # 任务单归档标记
        doc = json.loads(tp.read_text(encoding="utf-8"))
        done = next(t for t in doc["tasks"] if t["id"] == r01["id"])
        self.assertEqual(done["归档状态"], "已归档")
        self.assertIn("归档时间", done)
        # 申请单条目状态
        adoc = json.loads(ap.read_text(encoding="utf-8"))
        self.assertEqual(adoc["entries"][0]["状态"], "已应用")
        # 归档记录三件套 + 写后回读
        rec = json.loads((self.proj / "模拟评标" / ("归档记录_%s.json" % PROJECT)).read_text(encoding="utf-8"))
        self.assertEqual(len(rec["applied"]), 1)
        self.assertEqual(rec["applied"][0]["任务ID"], r01["id"])
        self.assertEqual(rec["applied"][0]["落点"], "performance")
        self.assertTrue((self.proj / "模拟评标" / ("归档记录_%s.md" % PROJECT)).is_file())
        self.assertTrue((self.proj / "模拟评标" / ("归档记录_%s.html" % PROJECT)).is_file())

        # 6) 再次 apply：无可应用条目 → 拒绝
        code, _, err = self._run("remedy-archive", "--project", PROJECT, "--apply", "--confirm")
        self.assertNotEqual(code, 0)
        self.assertIn("已全部应用", err)


if __name__ == "__main__":
    unittest.main()
