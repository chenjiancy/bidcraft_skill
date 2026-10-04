# -*- coding: utf-8 -*-
"""L1 单元测试：M5 图片占位预览框（方案A v1.0）。

覆盖 box_size_for（尺寸口径映射）与 make_placeholder_png（灰底占位图生成）。
PIL 缺失时跳过 PNG 相关用例（与 image_spec.fit_size 的依赖策略一致）。
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from m5_project import ph_preview as P    # noqa: E402


def _have_pil():
    try:
        import PIL  # noqa: F401
        return True
    except Exception:
        return False


class TestBoxSize(unittest.TestCase):
    def test_prefix_const(self):
        self.assertEqual(P.PH_PREVIEW_PREFIX, "IMG_PH:")

    def test_single_image_spec_sizes(self):
        """单图占位：尺寸=image_spec 目标口径（高×宽 cm）。"""
        cases = [
            ("【图片：企业法人营业执照（副本）扫描件】", (16.0, 12.0)),
            ("【图片：三体系认证证书】", (16.0, 23.0)),
            ("【图片：法定代表人身份证正、反面扫描件】", (7.5, 4.5)),
            ("【图片：企业基本账户开户许可证扫描件】", (16.0, 12.0)),
            ("【图片：拟投入监理人员社保证明】", (16.0, 15.0)),
        ]
        for ph, want in cases:
            self.assertEqual(P.box_size_for(ph), want, ph)

    def test_adaptive_and_combo(self):
        """自适应（组织机构框图）取代表高；组合占位（资质/人员组）取默认代表框。"""
        self.assertEqual(
            P.box_size_for("【图片：组织机构框图（含结构、领导成员、主要技术人员、管理人员及数量）】"),
            (15.0, 8.0))
        self.assertEqual(P.box_size_for("【图片：企业资质证书扫描件】"), (16.0, 12.0))
        self.assertEqual(
            P.box_size_for("【图片：拟派监理人员注册证书、岗位证书、职称、身份证等证明材料】"),
            (16.0, 12.0))


@unittest.skipUnless(_have_pil(), "依赖 PIL，未安装则跳过")
class TestMakePng(unittest.TestCase):
    def test_png_dims_match_cm(self):
        """PNG 像素尺寸 = cm × dpi/2.54（±2px），文件可写。"""
        ph = "【图片：三体系认证证书】"
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "ph.png")
            p = P.make_placeholder_png(ph, out_path=out)
            self.assertTrue(Path(p).is_file())
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
        w_cm, h_cm = P.box_size_for(ph)
        self.assertAlmostEqual(w, w_cm * 150 / 2.54, delta=2)
        self.assertAlmostEqual(h, h_cm * 150 / 2.54, delta=2)

    def test_default_path_written(self):
        """缺省 out_path 时写临时目录（按文案 hash 命名），内容可读。"""
        ph = "【图片：监理示范（优质）工程】"
        p = P.make_placeholder_png(ph)
        self.assertTrue(Path(p).is_file())
        from PIL import Image
        with Image.open(p) as im:
            self.assertGreater(im.size[0], 0)

    def _make_asset(self, td, name, color=(200, 30, 30)):
        """造一张 60×40 测试素材图。"""
        from PIL import Image
        p = os.path.join(td, name)
        Image.new("RGB", (60, 40), color).save(p)
        return p

    def test_assets_thumbnails_drawn(self):
        """有素材：框内绘制缩略图（文件存在、尺寸口径一致、素材像素出现在框内）。"""
        ph = "【图片：三体系认证证书】"
        with tempfile.TemporaryDirectory() as td:
            a1 = self._make_asset(td, "ISO9001_20290318.png")
            a2 = self._make_asset(td, "ISO14001_20290318.png")
            assets = [(a1, "三体系认证证书", True), (a2, "三体系认证证书", True)]
            out = os.path.join(td, "ph.png")
            p = P.make_placeholder_png(ph, assets=assets, out_path=out)
            self.assertTrue(Path(p).is_file())
            from PIL import Image
            with Image.open(p) as im:
                w, h = im.size
            w_cm, h_cm = P.box_size_for(ph)
            self.assertAlmostEqual(w, w_cm * 150 / 2.54, delta=2)
            self.assertAlmostEqual(h, h_cm * 150 / 2.54, delta=2)

    def test_assets_missing_file_skipped(self):
        """素材文件不存在：不报错、生成成功（缺图张数计入标注）。"""
        ph = "【图片：企业资质证书扫描件】"
        with tempfile.TemporaryDirectory() as td:
            good = self._make_asset(td, "a_20281222_P0.png")
            assets = [(good, "资质证书_房屋建筑工程甲级", True),
                      (os.path.join(td, "不存在.png"), "资质证书_市政公用工程乙级", True)]
            p = P.make_placeholder_png(ph, assets=assets, out_path=os.path.join(td, "ph.png"))
            self.assertTrue(Path(p).is_file())

    def test_assets_all_fail_falls_back_to_pending(self):
        """全部素材读取失败：退化为待补标注灰底图（文件仍生成）。"""
        ph = "【图片：拟投入监理人员社保证明】"
        with tempfile.TemporaryDirectory() as td:
            assets = [(os.path.join(td, "x.png"), "社保证明", True)]
            p = P.make_placeholder_png(ph, assets=assets, out_path=os.path.join(td, "ph.png"))
            self.assertTrue(Path(p).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
