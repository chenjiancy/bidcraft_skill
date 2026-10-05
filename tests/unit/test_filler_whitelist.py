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
            "performance": [{"name": "横江", "path": "业绩/示例横江片区污水管网整治工程_20260201_李四/"}],
            "social_security_required": {"status": "已上传", "path": "项目资料/社保_P0.png、社保_P1.png"},
            "personnel": [{"name": "张三"}, {"name": "赵六"}],
            "企业基础信息": {"法定代表人姓名": "李四", "委托代理人姓名": "王五"},
        }
        allowed, person_dirs, prefixes = filler._build_whitelist(mat)
        self.assertIn("资质/营业执照_副本_长期.png", allowed)
        self.assertIn("资质/房屋建筑工程监理甲级_20281222_P0.png", allowed)
        self.assertIn("资质/房屋建筑工程监理甲级_20281222_P1.png", allowed)   # 顿号拆出
        self.assertIn("资质/ISO9001_20290318.png", allowed)
        self.assertIn("荣誉/优秀监理企业_20230201.png", allowed)
        self.assertIn("业绩/示例横江片区污水管网整治工程_20260201_李四/", prefixes)  # 目录型前缀
        self.assertIn("人员/张三", person_dirs)
        self.assertIn("人员/李四", person_dirs)
        self.assertIn("人员/王五", person_dirs)
        self.assertTrue(any(p.startswith("项目资料/") for p in prefixes))

    def test_is_whitelisted(self):
        wl = ({"资质/营业执照.png"}, {"人员/张三"}, {"项目资料/"})
        self.assertTrue(filler._is_whitelisted("资质/营业执照.png", wl))
        self.assertTrue(filler._is_whitelisted("人员/张三/职称证书/高级工程师_P0.png", wl))
        self.assertTrue(filler._is_whitelisted("项目资料/社保_P0.png", wl))
        self.assertFalse(filler._is_whitelisted("荣誉/先进监理企业_20250101.png", wl))
        self.assertFalse(filler._is_whitelisted("人员/张三2/身份证/1.png", wl))  # 目录边界


class TestFilterWhitelist(unittest.TestCase):
    def test_listed_kept_unlisted_outside(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            a = _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            b = _mkimg(base, "荣誉/先进监理企业_20250101.png")  # 未列明
            wl = ({"荣誉/优秀监理企业_20250101.png"}, {"人员/张三"}, {"项目资料/"})
            ok, out = filler._filter_whitelist([a, b], base, wl)
            self.assertEqual(ok, [a])
            self.assertEqual(out, ["荣誉/先进监理企业_20250101.png"])


class TestBuildComboWhitelist(unittest.TestCase):
    def test_advanced_honor_only_listed_inserted(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            listed = _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            _mkimg(base, "荣誉/先进监理企业_20250101.png")  # 目录里存在但清单未列
            mat = {"honors": [{"path": "荣誉/优秀监理企业_20250101.png"}]}
            wl = filler._build_whitelist(mat)
            items, missing, out = filler._build_combo(
                "【图片：先进（优秀）监理企业证书】", base, base, mat, wl)
            rels = [i[0].replace("\\", "/") for i in items]
            self.assertTrue(any(r.endswith("荣誉/优秀监理企业_20250101.png") for r in rels))
            self.assertFalse(any(r.endswith("荣誉/先进监理企业_20250101.png") for r in rels))

    def test_qual_combo_skips_unlisted_extra(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkimg(base, "资质/市政公用工程监理乙级_20291121_P0.png")
            _mkimg(base, "资质/市政公用工程监理乙级_旧版.png")  # 前缀命中但清单未列
            mat = {"qualification_required": [
                {"path": "资质/市政公用工程监理乙级_20291121_P0.png"}]}
            wl = filler._build_whitelist(mat)
            items, missing, out = filler._build_combo(
                "【图片：企业资质证书扫描件】", base, base, mat, wl)
            self.assertIn("资质/市政公用工程监理乙级_旧版.png", out)
            self.assertTrue(any("市政公用工程监理乙级_20291121_P0.png" in i[0].replace("\\", "/")
                                for i in items))

    def test_no_whitelist_backward_compat(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkimg(base, "荣誉/优秀监理企业_20250101.png")
            _mkimg(base, "荣誉/先进监理企业_20250101.png")
            mat = {"honors": [{"path": "荣誉/优秀监理企业_20250101.png"}]}
            items, missing, out = filler._build_combo(
                "【图片：先进（优秀）监理企业证书】", base, base, mat, None)
            self.assertEqual(out, [])           # 旧调用不检查
            self.assertEqual(len(items), 1)     # ⑧ 数据驱动：仅清单列明 1 张


class TestDataDriven(TestBuildComboWhitelist):
    """⑧ 硬编码参数化：总监/法代/代理人/专业/资质等级/荣誉全部来自素材清单。"""

    def test_omit_zc_derived_from_personnel(self):
        persons = [
            {"name": "张三", "status": "齐备", "title_cert": "高工（道路与桥梁）"},
            {"name": "赵六", "status": "职称缺口", "title_cert": "库内无职称证书"},
            {"name": "黄诚", "status": "齐备", "title_cert": "无（名单—）"},
        ]
        self.assertEqual(filler._omit_zc(persons), {"赵六", "黄诚"})

    def test_director_names_from_material(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            _mkimg(base, "人员/张三/职称证书/高工_道路_P0.png")
            _mkimg(base, "人员/李四/身份证/身份证_P0.png")
            _mkimg(base, "人员/王五/身份证/身份证_P0.png")
            mat = {
                "personnel": [{"name": "张三"}],
                "企业基础信息": {"法定代表人姓名": "李四", "委托代理人姓名": "王五"},
            }
            wl = filler._build_whitelist(mat)
            items, mis, out = filler._build_combo(
                "【图片：总监高级工程师职称证书】", base, base, mat, wl)
            self.assertTrue(any("人员/张三" in i[0].replace("\\", "/") for i in items))
            items, mis, out = filler._build_combo(
                "【图片：法定代表人身份证正、反面扫描件】", base, base, mat, wl)
            self.assertTrue(any("人员/李四" in i[0].replace("\\", "/") for i in items))
            items, mis, out = filler._build_combo(
                "【图片：委托代理人身份证正、反面扫描件】", base, base, mat, wl)
            self.assertTrue(any("人员/王五" in i[0].replace("\\", "/") for i in items))

    def test_major_and_qual_level_derived(self):
        mat = {
            "投标资格专业": "市政公用工程",
            "personnel": [{"name": "张三", "cert": "注册证34008007（房建+市政公用，2028.1.23）"}],
            "qualification_required": [
                {"path": "资质/市政公用工程监理乙级_20291121_P0.png"},
                {"path": "资质/房屋建筑工程监理甲级_20281222_P0.png"},
            ],
        }
        self.assertEqual(filler._cert_major(mat), "房建+市政公用")
        self.assertEqual(filler._qual_level_from_mat(mat),
                         "房屋建筑工程监理甲级；市政公用工程监理乙级")
        self.assertEqual(filler._qual_cert_prefixes(mat),
                         ["市政公用工程监理乙级", "房屋建筑工程监理甲级"])


if __name__ == "__main__":
    unittest.main()
