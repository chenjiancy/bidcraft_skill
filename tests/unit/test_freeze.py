# -*- coding: utf-8 -*-
"""⑥ proj-freeze 冻结单测：冻结清单/版本 bump/审计改动/M7 冻结一致检查。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core                        # noqa: E402
from m5_project import freeze as fz             # noqa: E402
from m7_check import checker as m7              # noqa: E402


def _mk_docx(path, text="【项目名称】正文"):
    from docx import Document
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    d.save(str(path))


class FreezeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = core.Library(self.tmp.name)
        self.ent, _ = self.lib.init_enterprise("冻结测试企业")
        self.project = "测试项目"
        self.tpl = Path(self.ent) / "项目级" / self.project / "项目模板"
        self.tpl.mkdir(parents=True)
        _mk_docx(self.tpl / "封面.docx", "【项目名称】封面")
        _mk_docx(self.tpl / "投标函.docx", "【项目名称】投标函")

    def tearDown(self):
        self.tmp.cleanup()


class TestFreeze(FreezeBase):
    def test_freeze_writes_manifest_and_baseline(self):
        man = fz.freeze_project(self.ent, self.project)
        self.assertEqual(man["冻结版本"], "v1")
        self.assertEqual(man["文件数"], 2)
        self.assertTrue((self.tpl / fz.FREEZE_JSON).is_file())
        rows = __import__("m_feedback.feedback", fromlist=["feedback"]).load_baseline(self.ent)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["产物类型"] == "项目模板" for r in rows))

    def test_refreeze_bumps_version(self):
        fz.freeze_project(self.ent, self.project)
        man2 = fz.freeze_project(self.ent, self.project)
        self.assertEqual(man2["冻结版本"], "v2")
        self.assertEqual(man2["文件"][0]["版本"], "v2")

    def test_audit_flags_modified(self):
        fz.freeze_project(self.ent, self.project)
        (self.tpl / "封面.docx").write_bytes(b"tampered")
        res = fz.audit_frozen(self.ent, self.project)
        self.assertEqual(len(res["modified"]), 1)
        self.assertIn("封面.docx", res["modified"][0]["相对路径"])


class TestM7FrozenCheck(FreezeBase):
    def test_skip_when_not_frozen(self):
        ok, issues = m7.check_frozen(Path(self.tmp.name), self.tpl)
        self.assertTrue(ok)
        self.assertTrue(any("未发现冻结清单" in x for x in issues))

    def test_modified_frozen_file_flagged(self):
        fz.freeze_project(self.ent, self.project)
        (self.tpl / "投标函.docx").write_bytes(b"tampered")
        ok, issues = m7.check_frozen(Path(self.tmp.name), self.tpl)
        self.assertFalse(ok)
        self.assertTrue(any("冻结版已改动" in x for x in issues))


if __name__ == "__main__":
    unittest.main()
