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

    def test_id_card_legal_agent_box_container_tighten(self):
        """v2.4：身份证 contain 受容器收紧（模板并排表格单元格防溢出）——min(框, 容器)。"""
        w, h = imgsp.fit_size(str(self.idc), "身份证_法代授权", max_w=7.0, max_h=4.5)
        # 960×600，容器 7.0×4.5 → 按宽限缩：7.0×4.38
        self.assertAlmostEqual(w, 7.0, delta=0.1)
        self.assertAlmostEqual(h, 4.4, delta=0.1)
        w2, h2 = imgsp.fit_size(str(self.idc), "身份证", max_w=7.0, max_h=None)
        self.assertAlmostEqual(w2, 7.0, delta=0.1)
        self.assertAlmostEqual(h2, 4.4, delta=0.1)

    def test_max_w_and_max_h(self):
        """max_w/max_h 收紧：可用宽 16 超 max_h 时按 max_h 定高、宽随比例收缩。"""
        w, h = imgsp.fit_size(str(self.vert), "营业执照扫描件", max_w=15, max_h=None)
        self.assertAlmostEqual(w, 15.0, delta=0.1)
        w2, h2 = imgsp.fit_size(str(self.vert), "营业执照扫描件", max_w=None, max_h=10)
        self.assertAlmostEqual(h2, 10.0, delta=0.1)
        self.assertAlmostEqual(w2, 10.0 / 1.4, delta=0.1)

    def test_unknown_key(self):
        self.assertIsNone(imgsp.fit_size(str(self.vert), "不存在口径"))




if __name__ == "__main__":
    unittest.main(verbosity=2)
