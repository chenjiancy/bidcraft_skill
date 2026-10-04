# -*- coding: utf-8 -*-
"""⑩ 素材台账单源化：save_ledger 只写 JSON，export_ledger_csv 按需导出。"""
import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core  # noqa: E402


class TestLedgerSingleSource(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = core.Library(self.tmp.name)
        self.ent, _existed = self.lib.init_enterprise("企业A", credit_code="913400000000000000")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_writes_json_only(self):
        rows = [core.new_ledger_row(category="资质", rel_path="资质/营业执照.png",
                                    keywords="营业执照", upload_date="2026-10-04")]
        core.save_ledger(self.ent, rows)
        lib = core.lib_root(self.ent)
        self.assertTrue((lib / core.LEDGER_JSON).exists())
        self.assertFalse((lib / core.LEDGER_CSV).exists())

    def test_export_csv_from_json(self):
        rows = [core.new_ledger_row(category="资质", rel_path="资质/营业执照.png",
                                    keywords="营业执照", upload_date="2026-10-04")]
        core.save_ledger(self.ent, rows)
        core.export_ledger_csv(self.ent)
        lib = core.lib_root(self.ent)
        with open(lib / core.LEDGER_CSV, encoding="utf-8-sig", newline="") as f:
            got = list(csv.DictReader(f))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["category"], "资质")
        self.assertEqual(got[0]["rel_path"], "资质/营业执照.png")
        # 导出后再 load 仍以 JSON 为准
        self.assertEqual(len(core.load_ledger(self.ent)), 1)


if __name__ == "__main__":
    unittest.main()
