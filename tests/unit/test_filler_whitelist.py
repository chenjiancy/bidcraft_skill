# -*- coding: utf-8 -*-
"""③ 素材清单白名单单测：组合构建只允许清单列明素材，清单外报错不插入。"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))

from m5_project import filler  # noqa: E402


def _mkimg(d, rel):
    p = d / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    # 用极小的合法 PNG 头占位（_build_combo 只做路径收集，不做解码）
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return p


class TestBuildWhitelist(unittest.TestCase):
    def test_paths_and_persons_extracted(self):
        mat = {
            "qualification_required": [
                {"name": "营业执照", "path": "资质/营业执照_副本_长期.png"},
                {"name": "甲级", "path": "资质/房屋建筑工程监理甲级_20281222_P0.png、资质/房屋建筑工程监理甲级_20281222_P1.png"},
            ],
            "iso_certificates": [{"name": "ISO9001", "path": "资质/ISO9001_20290318.png"}],
            "honors": [{"name": "优秀", "path": "荣誉/优秀监理企业_20230201.png"}],
            "performance": [{"name": "横江", "path": "业绩/和县横江片区污水管网整治工程_20260201_邵章华/"}],
            "social_security_required": {"status": "已上传", "path": "项目资料/社保_P0.png、社保_P1.png"},
            "personnel": [{"name": "陈云"}, {"name": "阮旭"}],
            "企业基础信息": {"法定代表人姓名": "邵章华", "委托代理人姓名": "孙婧"},
        }
        allowed, person_dirs, prefixes = filler._build_whitelist(mat)
        self.assertIn("资质/营业执照_副本_长期.png", allowed)
        self.assertIn("资质/房屋建筑工程监理甲级_20281222_P0.png", allowed)
        self.assertIn("资质/房屋建筑工程监理甲级_20281222_P1.png", allowed)   # 顿号拆出
        self.assertIn("资质/ISO9001_20290318.png", allowed)
        self.assertIn("荣誉/优秀监理企业_20230201.png", allowed)
        self.assertIn("业绩/和县横江片区污水管网整治工程_20260201_邵章华/", prefixes)  # 目录型前缀
        self.assertIn("人员/陈云", person_dirs)
        self.assertIn("人员/邵章华", person_dirs)
        self.assertIn("人员/孙婧", person_dirs)
        self.assertTrue(any(p.startswith("项目资料/") for p in prefixes))

    def test_is_whitelisted(self):
        wl = ({"资质/营业执照.png"}, {"人员/陈云"}, {"项目资料/"})
        self.assertTrue(filler._is_whitelisted("资质/营业执照.png", wl))
        self.assertTrue(filler._is_whitelisted("人员/陈云/职称证书/高级工程师_P0.png", wl))
        self.assertTrue(filler._is_whitelisted("项目资料/社保_P0.png", wl))
        self.assertFalse(filler._is_whitelisted("荣誉/先进监理企业_20250101.png", wl))
        self.assertFalse(filler._is_whitelisted("人员/陈云2/身份证/1.png", wl))  # 目录边界


class TestFilterWhitelist(unittest.TestCase):
    def test_listed_kept_unlisted_outside(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            a = _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            b = _mkimg(base, "荣誉/先进监理企业_20250101.png")  # 未列明
            wl = ({"荣誉/优秀监理企业_20250101.png"}, {"人员/陈云"}, {"项目资料/"})
            ok, out = filler._filter_whitelist([a, b], base, wl)
            self.assertEqual(ok, [a])
            self.assertEqual(out, ["荣誉/先进监理企业_20250101.png"])


class TestBuildComboWhitelist(unittest.TestCase):
    def test_advanced_honor_skips_unlisted(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            listed = _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            unlisted = _mkimg(base, "荣誉/先进监理企业_20250101.png")
            mat = {"honors": [{"path": "荣誉/优秀监理企业_20250101.png"}]}
            wl = filler._build_whitelist(mat)
            items, missing, out = filler._build_combo(
                "【图片：先进（优秀）监理企业证书】", base, base, [], wl)
            self.assertIn("荣誉/先进监理企业_20250101.png", out)
            rels = [i[0].replace("\\", "/") for i in items]
            self.assertTrue(any(r.endswith("荣誉/优秀监理企业_20250101.png") for r in rels))
            self.assertFalse(any(r.endswith("荣誉/先进监理企业_20250101.png") for r in rels))

    def test_no_whitelist_backward_compat(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            _mkimg(base, "荣誉/先进监理企业_20250101.png")
            items, missing, out = filler._build_combo(
                "【图片：先进（优秀）监理企业证书】", base, base, [], None)
            self.assertEqual(out, [])           # 旧调用不检查
            self.assertEqual(len(items), 2)     # 全部 glob 结果插入


if __name__ == "__main__":
    unittest.main()
