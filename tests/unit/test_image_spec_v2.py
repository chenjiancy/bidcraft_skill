# -*- coding: utf-8 -*-
"""L1 单元测试：M5 图片尺寸统一等比（image_spec v2.0）+ 独立段内联插入（v2.1）。

v2.1 修正（2026-10-04）：图片插入由浮动 anchor 改回**独立段内联**——
浮动 anchor 在 Word 下连续图重叠/空白页/页序错乱不可控（实测 p46 空白），
独立段内联图顺序/分页由文档流天然保证，视觉同为「图独立成段、不挤占正文」。

覆盖：
  - fit_size 统一等比：竖版原图 → 宽=16、高按比例；横版原图 → 宽=16、高收缩；
    身份证保留固定框 8×5（contain）；max_w/max_h 收紧；
  - _insert_image 保持内联（独立段），floating 参数无行为差异；
  - _insert_images_before 顺序=items 顺序、分页=pageBreakBefore；
  - _to_floating_anchor 保留为工具函数：inline → anchor（元素顺序合法、r:embed 复用）。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402

from m5_project import image_spec as imgsp  # noqa: E402
from m5_project.fill_images import (_insert_image, _insert_images_before, _to_floating_anchor)  # noqa: E402


def _mkimg(path, w, h, color=(200, 0, 0)):
    from PIL import Image
    im = Image.new("RGB", (w, h), color)
    im.save(str(path))
    return path


class TestFitSize(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.vert = _mkimg(Path(self._td.name) / "v.png", 1000, 1400)      # 竖版 1:1.4
        self.horiz = _mkimg(Path(self._td.name) / "h.png", 1400, 950)     # 横版 ~1:0.68
        self.idc = _mkimg(Path(self._td.name) / "idc.png", 960, 600)      # 身份证 1.6:1

    def tearDown(self):
        self._td.cleanup()

    def test_vertical_uniform_ratio(self):
        """竖版原图：宽=16、高按比例（约 22.4）。"""
        w, h = imgsp.fit_size(str(self.vert), "营业执照扫描件")
        self.assertAlmostEqual(w, 16.0, delta=0.1)
        self.assertAlmostEqual(h, 22.4, delta=0.1)

    def test_horizontal_uniform_ratio(self):
        """横版原图：宽=16、高按比例收缩（约 10.9）。"""
        w, h = imgsp.fit_size(str(self.horiz), "职称证")
        self.assertAlmostEqual(w, 16.0, delta=0.1)
        self.assertAlmostEqual(h, 10.9, delta=0.1)

    def test_id_card_fixed_box(self):
        """身份证保留固定框 8×5（contain：960×600 → 8.0×5.0）。"""
        w, h = imgsp.fit_size(str(self.idc), "身份证")
        self.assertAlmostEqual(w, 8.0, delta=0.1)
        self.assertAlmostEqual(h, 5.0, delta=0.1)

    def test_id_card_legal_agent_box(self):
        """法代/授权身份证固定框 7.5×4.5（用户 2026-10-05 确认）：contain 等比置框内。"""
        w, h = imgsp.fit_size(str(self.idc), "身份证_法代授权")
        # 960×600 在 7.5×4.5 框内 → 按高限缩：7.2×4.5
        self.assertAlmostEqual(w, 7.2, delta=0.1)
        self.assertAlmostEqual(h, 4.5, delta=0.1)
        # 占位文案映射正确
        self.assertEqual(imgsp.spec_for("【图片：法定代表人身份证正、反面扫描件】"),
                         "身份证_法代授权")
        self.assertEqual(imgsp.spec_for("【图片：委托代理人身份证正、反面扫描件】"),
                         "身份证_法代授权")

    def test_max_w_and_max_h(self):
        """max_w/max_h 收紧：可用宽 16 超 max_h 时按 max_h 定高、宽随比例收缩。"""
        w, h = imgsp.fit_size(str(self.vert), "营业执照扫描件", max_w=15, max_h=None)
        self.assertAlmostEqual(w, 15.0, delta=0.1)
        w2, h2 = imgsp.fit_size(str(self.vert), "营业执照扫描件", max_w=None, max_h=10)
        self.assertAlmostEqual(h2, 10.0, delta=0.1)
        self.assertAlmostEqual(w2, 10.0 / 1.4, delta=0.1)

    def test_unknown_key(self):
        self.assertIsNone(imgsp.fit_size(str(self.vert), "不存在口径"))


class TestInsertInline(unittest.TestCase):
    def test_insert_image_keeps_inline(self):
        """_insert_image 保持内联（独立段），不再转浮动 anchor。"""
        with tempfile.TemporaryDirectory() as td:
            img = _mkimg(Path(td) / "a.png", 1000, 700)
            doc = Document()
            p = doc.add_paragraph()
            _insert_image(p, str(img), 16.0, 11.2)
            drawing = p._p.find(".//" + qn("w:drawing"))
            self.assertIsNotNone(drawing)
            self.assertIsNotNone(drawing.find(qn("wp:inline")), "应保持 wp:inline")
            self.assertIsNone(drawing.find(qn("wp:anchor")), "不应转 wp:anchor")
            # 独立成段：段内含图（run 数 ≥1，清文本后 add_run）
            self.assertGreaterEqual(len(p._p.findall(qn("w:r"))), 1)

    def test_insert_image_floating_flag_no_difference(self):
        """floating 参数保留兼容，行为无差异（均内联）。"""
        with tempfile.TemporaryDirectory() as td:
            img = _mkimg(Path(td) / "b.png", 800, 500)
            doc = Document()
            p = doc.add_paragraph()
            _insert_image(p, str(img), 15.0, 9.4, floating=False)
            drawing = p._p.find(".//" + qn("w:drawing"))
            self.assertIsNotNone(drawing.find(qn("wp:inline")))
            self.assertIsNone(drawing.find(qn("wp:anchor")))


class TestInsertImagesBefore(unittest.TestCase):
    def test_order_and_page_break(self):
        """_insert_images_before：段序 = items 顺序；pb=True 的图设段前分页。"""
        with tempfile.TemporaryDirectory() as td:
            # 三张图内容不同（颜色/尺寸不同），避免 python-docx 图片 part 按内容 hash 合并
            files = [str(_mkimg(Path(td) / ("f%d.png" % i), 1000, 700, color=(30 * i, 60, 90)))
                     for i in range(3)]
            doc = Document()
            para = doc.add_paragraph("【占位】")
            items = [(files[0], "职称证", True), (files[1], "职称证", False), (files[2], "职称证", True)]
            n = _insert_images_before(doc, para, items)
            self.assertEqual(n, 3)
            # 占位段前三个兄弟段 = 3 张图段，顺序与 items 一致
            sib = [el for el in para._p.itersiblings(preceding=True)]
            sib.reverse()
            self.assertEqual(len(sib), 3)
            pics = []
            for el in sib:
                blip = el.find(".//" + qn("a:blip"))
                self.assertIsNotNone(blip, "图片段应含 blip")
                rid = blip.get(qn("r:embed"))
                pics.append(doc.part.related_parts[rid].partname)
            # partname 顺序与 items 顺序一致（image1→f0、image2→f1、image3→f2）
            self.assertEqual(pics, ["/word/media/image%d.png" % (i + 1) for i in range(3)])
            # pb 检查
            pbb = []
            for el in sib:
                ppr = el.find(qn("w:pPr"))
                pbb.append(ppr is not None and ppr.find(qn("w:pageBreakBefore")) is not None)
            self.assertEqual(pbb, [True, False, True])

    def test_empty_items(self):
        with tempfile.TemporaryDirectory() as td:
            doc = Document()
            para = doc.add_paragraph("【占位】")
            self.assertEqual(_insert_images_before(doc, para, []), 0)


class TestFloatingAnchorTool(unittest.TestCase):
    def test_to_floating_anchor_element_order(self):
        """工具函数 _to_floating_anchor：inline → anchor，元素顺序符合 CT_Anchor：
        simplePos, positionH, positionV, extent, effectExtent, wrapNone, docPr,
        cNvGraphicFramePr, graphic；r:embed 复用（blip 仍在）。"""
        from lxml import etree
        with tempfile.TemporaryDirectory() as td:
            img = _mkimg(Path(td) / "c.png", 1000, 800)
            doc = Document()
            p = doc.add_paragraph()
            _insert_image(p, str(img), 16.0, 12.8)
            drawing = p._p.find(".//" + qn("w:drawing"))
            self.assertIsNotNone(drawing.find(qn("wp:inline")))
            _to_floating_anchor(drawing)
            anchor = drawing.find(qn("wp:anchor"))
            self.assertIsNotNone(anchor)
            self.assertIsNone(drawing.find(qn("wp:inline")))
            tags = [etree.QName(ch).localname for ch in anchor]
            expect = ["simplePos", "positionH", "positionV", "extent", "effectExtent",
                      "wrapNone", "docPr", "cNvGraphicFramePr", "graphic"]
            self.assertEqual(tags, expect)
            blip = anchor.find(".//" + qn("a:blip"))
            self.assertIsNotNone(blip)
            self.assertTrue(blip.get(qn("r:embed")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
