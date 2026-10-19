# -*- coding: utf-8 -*-
"""docx_tools.reader 单测：维度 0-7 记录提取（tempfile + python-docx 现造 fixture）。

覆盖：Markdown 正文 / 分节（纸张·方向·页边距）/ 段落布局 / run 格式 /
样式定义与继承 / 表格合并与网格 / 媒体对象锚点 / 页眉页脚。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from docx import Document  # noqa: E402
from docx.enum.section import WD_ORIENT, WD_SECTION  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml.ns import qn as _qn  # noqa: E402
from docx.shared import Inches, Mm, Pt  # noqa: E402

from _shared.docx_tools import reader_cli  # noqa: E402
from _shared.docx_tools.reader import story_paragraphs_runs, story_tables  # noqa: E402
from _shared.docx_tools.reader_sections_styles import (  # noqa: E402
    extract_styles_record,
    effective_style,
)

_PNG_1PX = None  # 运行时生成，见 _png_bytes()


def _png_bytes() -> bytes:
    """手写最小合法 1x1 8bit 灰度 PNG（python-docx Image 头解析要求完整 chunk CRC）。"""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)  # 1x1, 8bit, grayscale
    idat = zlib.compress(b"\x00\x00")  # 滤波字节 + 1 灰度像素
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_VML_NS = "urn:schemas-microsoft-com:vml"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _add_vml_pict(paragraph) -> None:
    """往段落追加一个 VML w:pict 图元（老版 Word/WPS 图锚点，走 v:imagedata/@r:id）。"""
    run = paragraph.add_run()
    pict = run._r.makeelement("{%s}pict" % _W_NS, {})
    shape = run._r.makeelement("{%s}shape" % _VML_NS, {"{%s}id" % _VML_NS: "_x0000_i1025"})
    imagedata = run._r.makeelement(
        "{%s}imagedata" % _VML_NS, {"{%s}id" % _REL_NS: "rIdVML"}
    )
    pict.append(shape)
    pict.append(imagedata)
    run._r.append(pict)


def _build_docx(tmp: Path) -> Path:
    """构造覆盖各维度特征的 fixture.docx。"""
    doc = Document()
    section0 = doc.sections[0]
    section0.page_width = Mm(210)
    section0.page_height = Mm(297)
    doc.add_heading("一、企业概况", 1)
    p = doc.add_paragraph("投标人名称：")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("和县建设工程监理有限公司")
    r.bold = True
    r.underline = True
    r.font.size = Pt(12)
    r.font.name = "仿宋"
    r._element.rPr.rFonts.set(_qn("w:eastAsia"), "仿宋")
    table = doc.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "企业名称"
    merged = table.cell(0, 1).merge(table.cell(0, 2))
    merged.text = "和县建设工程监理有限公司"
    table.cell(1, 0).text = "注册地址"
    table.cell(1, 1).text = "马鞍山市"
    table.cell(1, 2).text = "和县"
    # 手工 vMerge：合并 (1,1)-(1,2) 纵向（restart/continue）
    w_main = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    tc_restart = table.cell(1, 1)._tc
    tc_restart.get_or_add_tcPr().append(
        tc_restart.makeelement(_qn("w:vMerge"), {"{%s}val" % w_main: "restart"})
    )
    tc_continue = table.cell(1, 2)._tc
    tc_continue.get_or_add_tcPr().append(tc_continue.makeelement(_qn("w:vMerge"), {}))
    header = section0.header
    header.paragraphs[0].text = "资格证明及辅助资料表"
    footer = section0.footer
    footer.paragraphs[0].text = "第 1 页"
    new_section = doc.add_section(WD_SECTION.NEW_PAGE)
    new_section.orientation = WD_ORIENT.LANDSCAPE
    new_section.page_width = Mm(297)
    new_section.page_height = Mm(210)
    doc.add_paragraph("横向页内容")
    png = tmp / "px.png"
    png.write_bytes(_png_bytes())
    doc.add_picture(str(png), width=Inches(1))
    _add_vml_pict(doc.add_paragraph("VML图形段"))  # 老版 Word/WPS w:pict 图元
    footer.paragraphs[0].add_run()
    _add_vml_pict(footer.paragraphs[0])  # 页脚 pict（golden 实测常见）
    path = tmp / "fixture.docx"
    doc.save(str(path))
    return path


class TestReaderFixtures(unittest.TestCase):
    """各维度记录提取与输出断言。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.docx = _build_docx(cls.tmp)
        cls.data = reader_cli.build_data(cls.docx, cls.docx)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_dim0_markdown_heading_and_table(self):
        md = reader_cli.markdown_output(self.data)
        self.assertIn("# 一、企业概况", md)
        self.assertIn("企业名称", md)
        self.assertIn("和县建设工程监理有限公司", md)

    def test_dim1_sections_page_and_orientation(self):
        sections = reader_cli.build_sections_data(self.docx, self.docx)["sections"]
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["page"]["orientation"], "portrait")
        self.assertEqual(sections[1]["page"]["orientation"], "landscape")
        self.assertEqual(sections[0]["page"]["margins"]["top_dxa"] is not None, True)

    def test_dim2_paragraph_layout_and_table_context(self):
        paragraphs = self.data["paragraphs"]
        texts = [p.get("text") for p in paragraphs]
        self.assertIn("投标人名称：和县建设工程监理有限公司", texts)
        centered = [p for p in paragraphs if p.get("text") == "投标人名称：和县建设工程监理有限公司"][0]
        self.assertEqual(centered.get("alignment"), "center")
        cell_paragraphs = [p for p in paragraphs if p.get("table_index")]
        self.assertTrue(cell_paragraphs, "表格内段落应带 table_index")
        self.assertEqual(cell_paragraphs[0]["table_index"], 1)

    def test_dim3_run_format_and_drawing(self):
        runs = self.data["runs"]
        name_runs = [r for r in runs if "和县建设工程监理有限公司" in r.get("text")]
        self.assertTrue(name_runs)
        run = name_runs[0]
        self.assertIs(run.get("bold"), True)
        self.assertEqual(run.get("underline"), "single")
        self.assertEqual(run.get("size_half_points"), 24)  # Pt(12) → 12pt*2
        self.assertEqual(run.get("fonts", {}).get("eastAsia"), "仿宋")
        drawing_runs = [r for r in runs if r.get("drawings")]
        self.assertTrue(drawing_runs, "图片 run 应带 drawings 锚点")
        self.assertTrue(drawing_runs[0]["drawings"][0].get("extent"))
        vml_runs = [
            d for r in drawing_runs for d in r.get("drawings", []) if d.get("vml_pict")
        ]
        self.assertTrue(vml_runs, "VML w:pict 图元应被识别")
        self.assertEqual(vml_runs[0].get("embed"), "rIdVML")

    def test_dim4_styles_and_effective_merge(self):
        styles = self.data["styles"]
        style_ids = [s.get("style_id") for s in styles["styles"]]
        self.assertIn("Heading1", style_ids)
        merged = effective_style(styles["styles"], "Heading1")
        self.assertIsInstance(merged.get("pPr"), dict)

    def test_dim5_table_merge_and_grid(self):
        tables = self.data["tables"]
        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual(len(table.get("grid")), 3)  # 三列等宽 gridCol
        self.assertEqual(len(set(table.get("grid"))), 1)
        rows = table["rows"]
        first_row_cells = rows[0]["cells"]
        self.assertEqual(first_row_cells[1]["text"], "和县建设工程监理有限公司")
        props = first_row_cells[1]["properties"]
        self.assertEqual(props.get("grid_span"), 2)
        second_row_cells = rows[1]["cells"]
        self.assertEqual(second_row_cells[1]["properties"].get("vertical_merge"), "restart")
        self.assertEqual(second_row_cells[2]["properties"].get("vertical_merge"), "continue")

    def test_dim6_objects_and_anchors(self):
        objects = self.data["objects"]
        media = [o for o in objects if o.get("part", "").startswith("word/media/")]
        self.assertTrue(media, "至少一个媒体对象")
        self.assertTrue(media[0].get("sha256"))
        anchors = [r for r in self.data["runs"] if r.get("drawings")]
        self.assertTrue(anchors)
        self.assertTrue(anchors[0]["drawings"][0].get("docPr"))
        vml_anchors = [
            d for r in anchors for d in r.get("drawings", []) if d.get("vml_pict")
        ]
        self.assertTrue(vml_anchors, "VML 图元也应作为锚点")

    def test_dim7_headers_footers(self):
        stories = self.data["headers_footers"]
        header_texts = [s.get("text") for s in stories if s.get("record_type") == "header"]
        footer_texts = [s.get("text") for s in stories if s.get("record_type") == "footer"]
        self.assertIn("资格证明及辅助资料表", header_texts)
        self.assertIn("第 1 页", footer_texts)
        footer = [s for s in stories if s.get("record_type") == "footer"][0]
        self.assertTrue(footer.get("drawings"), "页脚 VML 图元应被识别")

    def test_output_smoke_all_dims(self):
        for dim in range(1, 8):
            records = reader_cli.records_for_dimension(self.data, dim)
            text = reader_cli.FORMATTERS[dim](records)
            self.assertTrue(text.startswith("# Dimension %d" % dim))


if __name__ == "__main__":
    unittest.main()
