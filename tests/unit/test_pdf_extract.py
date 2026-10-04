# -*- coding: utf-8 -*-
"""L1 单元测试：M4 PDF 结构化提取（④）——文本/表格/多栏/降级。
PyMuPDF 为可选依赖：未安装时整模块跳过（CI 双平台无 fitz 也不红）。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None

from m4_tender import pdf_extract  # noqa: E402
from _shared import core           # noqa: E402

HAVE_FITZ = pdf_extract.HAVE_FITZ


@unittest.skipUnless(HAVE_FITZ, "未安装 PyMuPDF，跳过 PDF 结构化提取测试")
class PdfExtractTest(unittest.TestCase):
    def _new_pdf(self):
        d = fitz.open()
        return d

    def _make_two_page_pdf(self, path):
        d = self._new_pdf()
        p1 = d.new_page()
        p1.insert_text((72, 72), "第一章 招标公告", fontname="china-s")
        p1.insert_text((72, 96), "项目名称：测试项目监理", fontname="china-s")
        p2 = d.new_page()
        p2.insert_text((72, 72), "第二章 投标人须知", fontname="china-s")
        d.save(path)
        d.close()

    def test_text_with_page_markers(self):
        path = Path(tempfile.mkdtemp(prefix="bid_pdf_")) / "t.pdf"
        self._make_two_page_pdf(str(path))
        text, blocks = pdf_extract.extract_pdf(str(path))
        self.assertIn("第一章 招标公告", text)
        self.assertIn("项目名称：测试项目监理", text)
        self.assertIn("第二章 投标人须知", text)
        self.assertIn("【第 1 页】", text)
        self.assertIn("【第 2 页】", text)
        self.assertGreaterEqual(len(blocks), 3)
        self.assertTrue(all(b["kind"] in ("para", "table") for b in blocks))
        path.unlink(missing_ok=True)

    def test_multi_column_split_order(self):
        """双栏版面：同基线左右两栏 → 输出先左栏后右栏。"""
        path = Path(tempfile.mkdtemp(prefix="bid_pdf_")) / "col.pdf"
        d = self._new_pdf()
        p = d.new_page()
        p.insert_text((50, 100), "左栏第一行内容AAAA", fontname="china-s")
        p.insert_text((400, 100), "右栏第一行内容BBBB", fontname="china-s")
        p.insert_text((50, 120), "左栏第二行内容CCCC", fontname="china-s")
        p.insert_text((400, 120), "右栏第二行内容DDDD", fontname="china-s")
        d.save(str(path))
        d.close()
        text, _ = pdf_extract.extract_pdf(str(path))
        i_left1 = text.find("左栏第一行")
        i_right1 = text.find("右栏第一行")
        i_left2 = text.find("左栏第二行")
        i_right2 = text.find("右栏第二行")
        self.assertGreaterEqual(i_left1, 0)
        # 左栏两行先于右栏两行（先左后右列序）
        self.assertLess(i_left1, i_right1)
        self.assertLess(i_left2, i_right2)
        self.assertLess(i_right1, i_left2)  # 左栏行连续（同栏内按 y 序）
        path.unlink(missing_ok=True)

    def test_ruled_table_becomes_markdown(self):
        """带框表格 → Markdown 表格（含表头分隔行，单元格文字不丢）。"""
        path = Path(tempfile.mkdtemp(prefix="bid_pdf_")) / "tab.pdf"
        d = self._new_pdf()
        p = d.new_page()
        # 2 行 3 列闭合网格（4 条横线 + 3 条竖线）
        cols = [72, 250, 420]
        rows = [72, 102, 132]
        for x in cols:
            p.draw_line((x, rows[0]), (x, rows[-1]))
        for y in rows:
            p.draw_line((cols[0], y), (cols[-1], y))
        cells = [("项目名称", "监理服务期"), ("示例园区尾水", "365 天"), ("招标人", "示例某单位")]
        for (r, c), txt in zip([(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (2, 1)],
                               ["项目名称", "监理服务期", "示例园区尾水", "365 天", "招标人", "示例某单位"]):
            p.insert_text((cols[c] + 8, rows[r] + 24), txt, fontname="china-s")
        d.save(str(path))
        d.close()
        text, blocks = pdf_extract.extract_pdf(str(path))
        for cell in ("项目名称", "监理服务期", "示例园区尾水", "365 天", "招标人", "示例某单位"):
            self.assertIn(cell, text, "单元格文字不应丢失：%s" % cell)
        # 出现 Markdown 表格标记（表头分隔行）
        self.assertIn("| --- | --- |", text)
        has_table_block = any(b["kind"] == "table" for b in blocks)
        self.assertTrue(has_table_block, "应识别出表格切片")
        # 表内文字不重复（正文不二次输出）
        self.assertEqual(text.count("监理服务期"), 1, "表内文字不应在正文重复")
        path.unlink(missing_ok=True)

    def test_empty_table_rows_dropped(self):
        md = pdf_extract._rows_to_markdown([["", ""], ["a", "b"], ["x", "y"]])
        self.assertEqual(md.splitlines()[0], "| a | b |", "全空行被剔除后首个非空行作表头")
        self.assertIn("| x | y |", md)

    def test_cell_escape_pipe(self):
        md = pdf_extract._rows_to_markdown([["甲|乙", "丙"], ["1", "2"]])
        self.assertIn("甲｜乙", md)
        self.assertNotIn("| 甲|乙", md)


@unittest.skipUnless(HAVE_FITZ, "未安装 PyMuPDF，跳过")
class PdfExtractDegradeTest(unittest.TestCase):
    def test_garbage_pdf_raises_library_error(self):
        path = Path(tempfile.mkdtemp(prefix="bid_pdf_")) / "bad.pdf"
        path.write_bytes(b"%PDF-1.4 not really a pdf")
        with self.assertRaises(core.LibraryError):
            pdf_extract.extract_pdf_text(str(path))
        path.unlink(missing_ok=True)

    def test_empty_text_pdf_raises(self):
        """有页面但无文字层 → 明确报错（引导 --text-file OCR）。"""
        path = Path(tempfile.mkdtemp(prefix="bid_pdf_")) / "scan.pdf"
        d = fitz.open()
        p = d.new_page()
        p.draw_rect((72, 72, 400, 500), color=(0, 0, 0))
        d.save(str(path))
        d.close()
        with self.assertRaises(core.LibraryError):
            pdf_extract.extract_pdf_text(str(path))
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
