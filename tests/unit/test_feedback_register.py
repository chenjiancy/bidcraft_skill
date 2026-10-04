# -*- coding: utf-8 -*-
"""fb.register 持久化回归（⑥ 发现：idx 与 rows 分离解析导致保存失效）。"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core                        # noqa: E402
from m_feedback import feedback as fb           # noqa: E402


class TestRegisterPersist(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = core.Library(self.tmp.name)
        self.ent, _ = self.lib.init_enterprise("反馈测试企业")
        self.f = os.path.join(self.ent, "项目级", "测试项目", "投标函.docx")
        os.makedirs(os.path.dirname(self.f))
        from docx import Document
        d = Document()
        d.add_paragraph("【项目名称】投标函正文")
        d.save(self.f)
        self.rel = os.path.relpath(self.f, self.ent).replace("\\", "/")

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_persists_and_bumps(self):
        r1 = fb.register(self.ent, self.rel, level="项目级", project="测试项目",
                         ptype="项目模板", generator="test")
        self.assertEqual(r1["版本"], "v1")
        # 重新读取磁盘，确认确实落盘（而不是仅内存对象被改）
        rows = fb.load_baseline(self.ent)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["版本"], "v1")
        self.assertEqual(rows[0]["sha256"], core.sha256_of(self.f))

        r2 = fb.register(self.ent, self.rel, level="项目级", project="测试项目",
                         ptype="项目模板", generator="test")
        self.assertEqual(r2["版本"], "v2")
        rows = fb.load_baseline(self.ent)
        self.assertEqual(len(rows), 1, "重复登记不应产生重复条目")
        self.assertEqual(rows[0]["版本"], "v2")

    def test_unregister_removes(self):
        fb.register(self.ent, self.rel, ptype="项目模板")
        self.assertTrue(fb.unregister(self.ent, self.rel))
        self.assertEqual(fb.load_baseline(self.ent), [])


if __name__ == "__main__":
    unittest.main()
