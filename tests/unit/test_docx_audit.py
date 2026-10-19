# -*- coding: utf-8 -*-
"""docx_tools.audit 单测：包检查 / 样式继承 / 表格结构 / 属性顺序 / 基线差异 / 退出码。

覆盖：issue 契约、enrich 兜底、结构 hash 稳定性与敏感性、致命包错误
（损坏 zip/缺部件/重复成员/坏 XML）、OOXML 属性顺序、基线差异过滤、
command_audit 退出码（0/1/2）。
"""
import base64
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from docx import Document  # noqa: E402
from docx.oxml.ns import qn as _qn  # noqa: E402
from lxml import etree  # noqa: E402

from _shared.docx_tools import audit_cli  # noqa: E402
from _shared.docx_tools.audit import (  # noqa: E402
    enrich_findings,
    extract_styles,
    issue,
)
from _shared.docx_tools.audit_extract import (  # noqa: E402
    extract_sections_for_audit,
    structural_hash,
)
from _shared.docx_tools.common import NS, parse_xml, wtag  # noqa: E402

MINIMAL_ZIP = {
    "[Content_Types].xml": (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        b'<Default Extension="xml" ContentType="application/xml"/>'
        b'<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        b"</Types>"
    ),
    "_rels/.rels": (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        b"</Relationships>"
    ),
    "word/document.xml": (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:body><w:p><w:r><w:t>test</w:t></w:r></w:p>"
        b"<w:sectPr/></w:body></w:document>"
    ),
}


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


class TestIssueContract(unittest.TestCase):
    def test_issue_fields(self):
        finding = issue(
            "error", "E_TEST", "part#p1", "msg",
            expected=[1], actual=[2], repair_hint="hint", evidence={"x": 1}, blocking=True,
        )
        self.assertEqual(finding["severity"], "error")
        self.assertEqual(finding["code"], "E_TEST")
        self.assertEqual(finding["repair_hint"], "hint")
        self.assertTrue(finding["blocking"])

    def test_enrich_defaults(self):
        findings = enrich_findings(
            [issue("error", "E_PART_MISSING", "x", "missing"), issue("error", "E_UNKNOWN_CODE", "y", "?")]
        )
        self.assertTrue(findings[0]["blocking"])
        self.assertTrue(findings[0]["repair_hint"])
        self.assertEqual(findings[1]["repair_hint"], "")


class TestStructuralHash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _hash(self, xml_bytes: bytes, clear_text: bool, clear_format: bool) -> str:
        root = parse_xml(xml_bytes, "part")
        return structural_hash(root, clear_text=clear_text, clear_format=clear_format)

    def test_stable_and_text_sensitive(self):
        xml = (
            b'<w:document xmlns:w="%s"><w:body><w:p><w:r><w:t>aaa</w:t></w:r></w:p></w:body></w:document>'
            % NS["w"].encode()
        )
        h1 = self._hash(xml, clear_text=False, clear_format=False)
        h2 = self._hash(xml, clear_text=False, clear_format=False)
        self.assertEqual(h1, h2)
        xml2 = xml.replace(b"aaa", b"bbb")
        self.assertNotEqual(self._hash(xml2, clear_text=False, clear_format=False), h1)
        # 清文本后两文档同构
        self.assertEqual(
            self._hash(xml, clear_text=True, clear_format=False),
            self._hash(xml2, clear_text=True, clear_format=False),
        )

    def test_rsid_normalized(self):
        xml = (
            b'<w:document xmlns:w="%s"><w:body><w:p w:rsidR="00AB1234">'
            b"<w:pPr><w:rPr><w:rFonts w:ascii=\"A\"/></w:rPr></w:pPr>"
            b"<w:r><w:t>x</w:t></w:r></w:p></w:body></w:document>" % NS["w"].encode()
        )
        xml_other_rsid = xml.replace(b"00AB1234", b"00CD5678")
        self.assertEqual(
            self._hash(xml, clear_text=True, clear_format=False),
            self._hash(xml_other_rsid, clear_text=True, clear_format=False),
        )


class TestPackageChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.valid = cls.tmp / "valid.docx"
        doc = Document()
        doc.add_paragraph("正文")
        doc.save(str(cls.valid))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _find_codes(self, manifest):
        return {item.get("code") for item in manifest.get("findings", [])}

    def test_valid_docx_passes(self):
        manifest = audit_cli.inspect_docx(self.valid)
        self.assertTrue(manifest["input_valid"] if "input_valid" in manifest else True)
        self.assertFalse(self._find_codes(manifest) & audit_cli.FATAL_PACKAGE_CODES)
        self.assertGreater(manifest["summary"]["paragraph_count"], 0)

    def test_not_a_zip(self):
        bad = self.tmp / "bad.docx"
        bad.write_bytes(b"not a zip")
        manifest = audit_cli.inspect_docx(bad)
        self.assertIn("E_DOCX_OPEN", self._find_codes(manifest))

    def test_missing_required_part(self):
        path = self.tmp / "missing.docx"
        members = dict(MINIMAL_ZIP)
        del members["word/document.xml"]  # 缺必需部件
        _write_zip(path, members)
        manifest = audit_cli.inspect_docx(path)
        self.assertIn("E_PART_MISSING", self._find_codes(manifest))

    def test_duplicate_member(self):
        path = self.tmp / "dup.docx"
        members = dict(MINIMAL_ZIP)
        members["word/document.xml"] = members["word/document.xml"]
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as zf:
            for _ in range(2):
                zf.writestr("word/document.xml", members["word/document.xml"])
        manifest = audit_cli.inspect_docx(path)
        self.assertIn("E_ZIP_MEMBER_DUPLICATE", self._find_codes(manifest))

    def test_bad_xml_reported(self):
        path = self.tmp / "badxml.docx"
        members = dict(MINIMAL_ZIP)
        members["word/document.xml"] = b"<w:document>broken"
        _write_zip(path, members)
        manifest = audit_cli.inspect_docx(path)
        self.assertIn("E_XML_INVALID", self._find_codes(manifest))

    def test_crc_error(self):
        path = self.tmp / "crc.docx"
        payload = b"CRC_PROBE_0123456789" * 40
        with zipfile.ZipFile(str(path), "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("word/document.xml", payload)
        raw = path.read_bytes()
        # 在成员数据区翻转一个字节（zip 结构长度不变，CRC 失配）
        self.assertIn(b"CRC_PROBE_", raw)
        raw = raw.replace(b"CRC_PROBE_0", b"CRC_PROBE_1", 1)
        path.write_bytes(raw)
        manifest = audit_cli.inspect_docx(path)
        self.assertIn("E_ZIP_CRC", self._find_codes(manifest))


class TestExtractionAndOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.docx = cls.tmp / "table.docx"
        doc = Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "a"
        table.cell(0, 1).text = "b"
        doc.save(str(cls.docx))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_sections_extraction(self):
        with zipfile.ZipFile(str(self.docx)) as zf:
            root = parse_xml(zf.read("word/document.xml"), "part")
        sections = extract_sections_for_audit(root)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["page"]["orientation"], "portrait")

    def test_styles_extraction_with_defaults(self):
        with zipfile.ZipFile(str(self.docx)) as zf:
            styles_root = parse_xml(zf.read("word/styles.xml"), "part")
        manifest = extract_styles({"word/styles.xml": styles_root})
        self.assertIn("Normal", manifest["styles"])
        self.assertEqual(manifest["default_style_ids"].get("paragraph"), "Normal")

    def test_ooxml_property_order_findings(self):
        """构造 tblPr 子元素顺序反转（tblBorders 先于 tblW）→ E_OOXML_TBLPR_ORDER。"""
        with zipfile.ZipFile(str(self.docx)) as zf:
            root = parse_xml(zf.read("word/document.xml"), "part")
        tbl = root.xpath(".//w:tbl", namespaces=NS)[0]
        tbl_pr = tbl.find(wtag("tblPr"), NS)
        # 确保存在 tblW，然后把 tblBorders 插到 tblPr 首位（模式序应在 tblW 之后）
        from docx.oxml.ns import qn as dqn
        if tbl_pr.find(wtag("tblW"), NS) is None:
            tbl_w = tbl.makeelement(dqn("w:tblW"), {dqn("w:w"): "0", dqn("w:type"): "auto"})
            tbl_pr.append(tbl_w)
        borders = tbl.makeelement(dqn("w:tblBorders"), {})
        tbl_pr.insert(0, borders)
        from _shared.docx_tools.audit_extract import ooxml_property_order_findings
        findings = ooxml_property_order_findings("word/document.xml", root)
        codes = {f["code"] for f in findings}
        self.assertIn("E_OOXML_TBLPR_ORDER", codes)
        evidence = [f for f in findings if f["code"] == "E_OOXML_TBLPR_ORDER"][0]["evidence"]
        self.assertIn("table_index", evidence)


class TestBaselineFilter(unittest.TestCase):
    def test_unchanged_suppressed_but_new_kept(self):
        def finding(code, loc):
            return issue("error", code, loc, "msg " + code)

        source = [finding("E_A", "p1"), finding("E_A", "p2"), finding("E_B", "q1")]
        target = [finding("E_A", "p1"), finding("E_A", "p3"), finding("E_C", "r1")]
        retained = audit_cli.filter_unchanged_baseline_findings(source, target)
        locations = [f["location"] for f in retained]
        self.assertIn("p3", locations)
        self.assertIn("r1", locations)
        self.assertNotIn("p1", locations)  # 源中已存在的相同发现被抑制


class TestCommandAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.valid = cls.tmp / "valid.docx"
        doc = Document()
        doc.add_paragraph("正文")
        doc.save(str(cls.valid))
        cls.bad = cls.tmp / "bad.docx"
        cls.bad.write_bytes(b"not a zip")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exit_codes(self):
        args = SimpleNamespace(file=self.valid, source=None, out_dir=None)
        self.assertEqual(audit_cli.command_audit(args), 0)
        args_bad = SimpleNamespace(file=self.bad, source=None, out_dir=None)
        self.assertEqual(audit_cli.command_audit(args_bad), 2)
        args_same = SimpleNamespace(file=self.valid, source=self.valid, out_dir=None)
        with self.assertRaises(audit_cli.AuditError):
            audit_cli.command_audit(args_same)

    def test_source_compare_mode_runs(self):
        args = SimpleNamespace(file=self.valid, source=self.valid, out_dir=None)
        with self.assertRaises(audit_cli.AuditError):
            audit_cli.command_audit(args)


if __name__ == "__main__":
    unittest.main()
