# -*- coding: utf-8 -*-
"""M10 T22 集成测试（L2）：补救素材→企业素材库入库申请 真实项目链路 ——
init-enterprise 建企业（M1 素材库）→ 用 M1 现有命令链（open-inbox/sync-inbox/close-inbox/
propose/apply）预归档一份「监理合同_近年同类监理业绩」→ 任务单含 2 个已归档素材任务 →
assets-archive：R01（近年同类监理业绩）台账命中=已在库可复用，R02（荣誉表彰）待入库；
申请单三件套落盘 + 生成时间戳文件名 + summary 正确。
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

ENT = "T22集成企业"
PROJECT = "T22集成项目"


class M10AssetsArchiveIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self._run("init-enterprise", "--name", ENT)
        self.proj = self.root / ENT / "项目级" / PROJECT
        self.sdir = self.proj / "模拟评标"
        self.sdir.mkdir(parents=True)
        (self.sdir / ("失分补救任务单_%s.json" % PROJECT)).write_text(json.dumps(
            {"project": PROJECT, "tasks": [
                {"id": "R01", "类型": "素材补齐", "动作": "补业绩", "标题": "近年同类监理业绩（3.0 分）",
                 "来源": "通道A-客观", "评分项": "近年同类监理业绩",
                 "涉及素材": {"category": "业绩", "subtype": "近年同类监理业绩"},
                 "完成状态": "已完成", "归档状态": "已归档"},
                {"id": "R02", "类型": "素材补齐", "动作": "补荣誉", "标题": "先进示范表彰（2.0 分）",
                 "来源": "通道A-客观", "评分项": "先进示范表彰",
                 "涉及素材": {"category": "荣誉", "subtype": "先进示范优秀监理企业表彰证书"},
                 "完成状态": "已完成", "归档状态": "已归档"},
            ]}), encoding="utf-8")
        # M1 预归档一份业绩素材（真实命令链）
        inbox = self.root / ENT / "企业级" / "素材库" / "收件箱"
        (inbox / "监理合同_近年同类监理业绩_20261024.pdf").write_bytes(b"%PDF-1.4 fake")
        self._run("open-inbox")
        self._run("sync-inbox")
        self._run("close-inbox")
        self._run("propose", "--out", str(self.root / "提案.json"))
        prop = json.loads((self.root / "提案.json").read_text(encoding="utf-8"))
        for it in prop["items"]:
            if it.get("category") == "业绩" and not it.get("project_folder"):
                it["project_folder"] = PROJECT
        (self.root / "提案.json").write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
        code, out, err = self._run("apply", "--proposal", str(self.root / "提案.json"))
        self.assertEqual(code, 0, "%s|%s" % (out, err))

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

    def test_assets_archive_dedup_and_waiting(self):
        code, out, err = self._run("assets-archive", "--project", PROJECT)
        self.assertEqual(code, 0, "%s | %s" % (out, err))
        inbox = self.root / ENT / "企业级" / "素材库" / "收件箱"
        files = sorted(inbox.glob("补救入库申请_*.json"))
        self.assertEqual(len(files), 1)
        adoc = json.loads(files[0].read_text(encoding="utf-8"))
        s = adoc["summary"]
        self.assertEqual((s["申请条数"], s["待入库"], s["已在库（可复用）"]), (2, 1, 1))
        by = {e["任务ID"]: e for e in adoc["entries"]}
        self.assertIn("已在库", by["R01"]["状态"])
        self.assertEqual(by["R01"]["企业类别"], "业绩")
        self.assertTrue(by["R01"]["台账命中"])
        self.assertEqual(by["R02"]["状态"], "待入库")
        self.assertEqual(by["R02"]["企业类别"], "荣誉")
        # 三件套落盘
        self.assertEqual(len(list(inbox.glob("补救入库申请_*.md"))), 1)
        self.assertEqual(len(list(inbox.glob("补救入库申请_*.html"))), 1)
        html = list(inbox.glob("补救入库申请_*.html"))[0].read_text(encoding="utf-8")
        self.assertIn("企业素材库入库申请单", html)
        self.assertIn("open-inbox", html)
        # 输出含引导
        self.assertIn("apply --proposal", out)


if __name__ == "__main__":
    unittest.main()
