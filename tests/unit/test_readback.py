# -*- coding: utf-8 -*-
"""⑩ 写后回读工具单测：文件/哈希/JSON/docx/一致性对账 的回读验证。"""
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from _shared import core                       # noqa: E402
from _shared.core import readback as rb        # noqa: E402
from _shared.core import trash as _trash       # noqa: E402


class ReadbackBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = core.Library(self.tmp.name)
        self.ent, _ = self.lib.init_enterprise("回读测试企业")

    def tearDown(self):
        self.tmp.cleanup()


class TestVerifyFile(ReadbackBase):
    def test_exists_ok(self):
        p = Path(self.tmp.name) / "a.txt"
        p.write_text("x", encoding="utf-8")
        self.assertTrue(rb.verify_file(p))

    def test_missing_raises(self):
        with self.assertRaises(core.LibraryError):
            rb.verify_file(Path(self.tmp.name) / "不存在.txt")

    def test_empty_raises_with_min_bytes(self):
        p = Path(self.tmp.name) / "empty.txt"
        p.write_text("", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            rb.verify_file(p, min_bytes=1)
        self.assertTrue(rb.verify_file(p, min_bytes=0))  # min_bytes=0 仅要求存在

    def test_directory_raises(self):
        d = Path(self.tmp.name) / "dir"
        d.mkdir()
        with self.assertRaises(core.LibraryError):
            rb.verify_file(d)


class TestVerifySha256(ReadbackBase):
    def test_match_ok(self):
        p = Path(self.tmp.name) / "f.jpg"
        p.write_bytes(b"hello")
        h = hashlib.sha256(b"hello").hexdigest()
        self.assertTrue(rb.verify_sha256(p, h))

    def test_mismatch_raises(self):
        p = Path(self.tmp.name) / "f.jpg"
        p.write_bytes(b"hello")
        with self.assertRaises(core.LibraryError):
            rb.verify_sha256(p, hashlib.sha256(b"world").hexdigest())

    def test_missing_expected_raises(self):
        p = Path(self.tmp.name) / "f.jpg"
        p.write_bytes(b"hello")
        with self.assertRaises(core.LibraryError):
            rb.verify_sha256(p, "")

    def test_file_missing_raises(self):
        with self.assertRaises(core.LibraryError):
            rb.verify_sha256(Path(self.tmp.name) / "无.txt", "ab" * 32)


class TestVerifyJson(ReadbackBase):
    def _doc(self):
        p = Path(self.tmp.name) / "d.json"
        p.write_text('{"project": "示例项目", "diffs": []}', encoding="utf-8")
        return p

    def test_valid_ok(self):
        self.assertIsNotNone(rb.verify_json(self._doc()))

    def test_valid_with_required_fields_ok(self):
        doc = rb.verify_json(self._doc(), required_fields=("project", "diffs"))
        self.assertEqual(doc["project"], "示例项目")

    def test_missing_field_raises(self):
        with self.assertRaises(core.LibraryError):
            rb.verify_json(self._doc(), required_fields=("project", "nope"))

    def test_invalid_json_raises(self):
        p = Path(self.tmp.name) / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            rb.verify_json(p)

    def test_empty_json_raises(self):
        p = Path(self.tmp.name) / "empty.json"
        p.write_text("", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            rb.verify_json(p)


class TestVerifyDocx(ReadbackBase):
    def _make_docx(self, path, paras=1):
        from docx import Document
        doc = Document()
        for _ in range(paras):
            doc.add_paragraph("内容")
        doc.save(str(path))

    def test_nonempty_ok(self):
        p = Path(self.tmp.name) / "a.docx"
        self._make_docx(p, paras=2)
        self.assertTrue(rb.verify_docx_nonempty(p, min_paras=1))

    def test_too_few_paras_raises(self):
        p = Path(self.tmp.name) / "b.docx"
        self._make_docx(p, paras=1)
        with self.assertRaises(core.LibraryError):
            rb.verify_docx_nonempty(p, min_paras=5)

    def test_missing_raises(self):
        with self.assertRaises(core.LibraryError):
            rb.verify_docx_nonempty(Path(self.tmp.name) / "无.docx")


class TestVerifyConsistency(ReadbackBase):
    def test_clean_ok(self):
        self.assertTrue(rb.verify_consistency(self.ent))

    def test_orphan_trash_raises(self):
        tdir = _trash.trash_dir(self.ent)
        (tdir / "孤儿.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            rb.verify_consistency(self.ent)


class TestReadbackFiles(ReadbackBase):
    def test_list_of_paths_ok(self):
        a = Path(self.tmp.name) / "a.txt"
        b = Path(self.tmp.name) / "b.txt"
        a.write_text("1", encoding="utf-8")
        b.write_text("2", encoding="utf-8")
        self.assertTrue(rb.readback_files([a, b]))

    def test_missing_one_raises(self):
        a = Path(self.tmp.name) / "a.txt"
        a.write_text("1", encoding="utf-8")
        with self.assertRaises(core.LibraryError):
            rb.readback_files([a, Path(self.tmp.name) / "不存在.txt"])


if __name__ == "__main__":
    unittest.main()
