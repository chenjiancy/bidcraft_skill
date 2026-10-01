# -*- coding: utf-8 -*-
"""L1 单元测试：命名规范引擎（纯逻辑，无 I/O，数量最多、速度最快）"""
import sys
import os
import unittest
from datetime import date

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from _shared import naming as nm  # noqa: E402


class TestSanitizeKeyword(unittest.TestCase):
    def test_windows_illegal_replaced(self):
        self.assertEqual(nm.sanitize_keyword('a/b\\c:*?"<>|d'), "a-b-c-d")

    def test_underscore_replaced(self):
        self.assertEqual(nm.sanitize_keyword("iso_9001"), "iso-9001")

    def test_collapse_spaces_and_dashes(self):
        self.assertEqual(nm.sanitize_keyword("  甲级    资质  "), "甲级 资质")
        self.assertEqual(nm.sanitize_keyword("a--b--c"), "a-b-c")

    def test_none_and_empty(self):
        self.assertEqual(nm.sanitize_keyword(None), "")
        self.assertEqual(nm.sanitize_keyword("  "), "")


class TestNormalizeDate(unittest.TestCase):
    def test_8digit(self):
        self.assertEqual(nm.normalize_date("20281231"), "20281231")

    def test_6digit_becomes_month_first(self):
        self.assertEqual(nm.normalize_date("202812"), "20281201")

    def test_long_term_variants(self):
        for v in ["长期", "长期有效", "无固定期限", "永久", "无期限"]:
            self.assertEqual(nm.normalize_date(v), "长期")

    def test_unknown_variants(self):
        for v in ["日期不详", "不详", "未知", "无"]:
            self.assertEqual(nm.normalize_date(v), "日期不详")

    def test_datetime_object(self):
        self.assertEqual(nm.normalize_date(date(2026, 5, 1)), "20260501")

    def test_invalid_raises(self):
        with self.assertRaises(nm.NamingError):
            nm.normalize_date("abc")
        with self.assertRaises(nm.NamingError):
            nm.normalize_date(None)


class TestSplit(unittest.TestCase):
    def test_split_ext(self):
        self.assertEqual(nm.split_ext("a.pdf"), ("a", ".pdf"))
        self.assertEqual(nm.split_ext("a.PNG"), ("a", ".png"))
        self.assertEqual(nm.split_ext("noext"), ("noext", ""))

    def test_split_page(self):
        self.assertEqual(nm.split_page("监理合同_P0"), ("监理合同", 0))
        self.assertEqual(nm.split_page("监理合同_P1"), ("监理合同", 1))
        self.assertEqual(nm.split_page("监理合同"), ("监理合同", None))


class TestBuildName(unittest.TestCase):
    def test_license(self):
        self.assertEqual(
            nm.build_name("资质", "营业执照", dates=["20281231"], ext=".jpg"),
            "营业执照_20281231.jpg")

    def test_id_card(self):
        self.assertEqual(
            nm.build_name("人员", "身份证", keywords=["人像面"], dates=["20350101"]),
            "身份证_人像面_20350101")

    def test_register_cert_two_dates(self):
        self.assertEqual(
            nm.build_name("人员", "注册证书", keywords=["监理工程师"],
                          dates=["20270101", "20280101"]),
            "监理工程师_20270101_20280101")

    def test_project_file_with_page(self):
        self.assertEqual(
            nm.build_name("业绩", "业绩文件", keywords=["监理合同"], page=0),
            "监理合同_P0")

    def test_keyword_sanitized(self):
        self.assertEqual(
            nm.build_name("资质", "资质证书", keywords=["ISO9001/质量"], dates=["20280101"]),
            "ISO9001-质量_20280101")

    def test_missing_keyword_raises(self):
        with self.assertRaises(nm.NamingError):
            nm.build_name("资质", "资质证书", dates=["20280101"])

    def test_bad_enum_raises(self):
        with self.assertRaises(nm.NamingError):
            nm.build_name("人员", "身份证", keywords=["正面"], dates=["20350101"])

    def test_unknown_subtype_raises(self):
        with self.assertRaises(nm.NamingError):
            nm.build_name("资质", "不存在的子类")


class TestValidate(unittest.TestCase):
    def test_ok(self):
        ok, issues = nm.validate("资质", "营业执照", "营业执照_20281231.jpg")
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_bad_format(self):
        ok, issues = nm.validate("资质", "营业执照", "随便写.jpg")
        self.assertFalse(ok)
        self.assertTrue(any("主体名不符合规范" in i for i in issues))

    def test_ext_warn_only(self):
        ok, issues = nm.validate("资质", "营业执照", "营业执照_20281231.bmp")
        self.assertTrue(ok)  # 扩展名仅提示不致命
        self.assertTrue(any("仅提示" in i for i in issues))


class TestClassifyAndGuess(unittest.TestCase):
    def test_license(self):
        self.assertEqual(nm.classify("营业执照_20280101.jpg")[:2], ("资质", "营业执照"))

    def test_id_card(self):
        self.assertEqual(nm.classify("身份证_人像面.jpg")[:2], ("人员", "身份证"))

    def test_iso_cert(self):
        self.assertEqual(nm.classify("ISO9001_20280101.pdf")[:2], ("资质", "体系认证"))

    def test_register_cert(self):
        self.assertEqual(nm.classify("监理工程师_20270101_20280101.pdf")[:2], ("人员", "注册证书"))

    def test_unknown(self):
        self.assertEqual(nm.classify("随便一个名字"), (None, None, None))

    def test_guess_subtype(self):
        self.assertEqual(nm.guess_subtype("人员", "身份证_人像面_20350101.jpg"), "身份证")


class TestProjectFolder(unittest.TestCase):
    def test_build(self):
        self.assertEqual(
            nm.build_project_folder("示例某安置房监理", "20260101", "张三"),
            "示例某安置房监理_20260101_张三")

    def test_no_director(self):
        self.assertEqual(
            nm.build_project_folder("示例某项目监理", "20260101"),
            "示例某项目监理_20260101_无总监")

    def test_validate_ok_and_bad(self):
        self.assertTrue(nm.validate_project_folder("某项目_20260101_李四")[0])
        self.assertFalse(nm.validate_project_folder("乱写的名字")[0])


class TestDates(unittest.TestCase):
    def test_extract_date(self):
        self.assertEqual(nm.extract_date("签发2026年3月5日"), "20260305")
        self.assertEqual(nm.extract_date("有效期至20281231"), "20281231")

    def test_extract_dates_unique(self):
        self.assertEqual(nm.extract_dates("20260101 20260101 20260202"), ["20260101", "20260202"])


class TestParseName(unittest.TestCase):
    def test_parse_license(self):
        r = nm.parse_name("资质", "营业执照", "营业执照_20281231.jpg")
        self.assertTrue(r["ok"])
        self.assertEqual(r["dates"], ["20281231"])
        self.assertEqual(r["ext"], ".jpg")


if __name__ == "__main__":
    unittest.main()
