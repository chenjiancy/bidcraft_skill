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
            nm.build_name("人员", "身份证", dates=["20350101"]),
            "身份证_20350101")
        self.assertEqual(
            nm.build_name("人员", "身份证", dates=["20350101"], page=0),
            "身份证_20350101_P0")
        self.assertEqual(
            nm.build_name("人员", "身份证", dates=["20350101"], page=1),
            "身份证_20350101_P1")
        self.assertEqual(
            nm.build_name("人员", "身份证", dates=["长期"]),
            "身份证_长期")

    def test_register_cert_two_dates(self):
        self.assertEqual(
            nm.build_name("人员", "注册证书", keywords=["监理工程师"],
                          dates=["20270101", "20280101"]),
            "监理工程师_20270101_20280101")

    def test_project_file_with_page(self):
        self.assertEqual(
            nm.build_name("业绩", "业绩文件", keywords=["监理合同"], page=0),
            "监理合同_P0")

    def test_retirement_cert_dedups_fixed_const(self):
        # 退休证 C("退休证") 固定段 + keywords=['退休证'] → 只保留一个，不再重复
        self.assertEqual(
            nm.build_name("人员", "退休证", keywords=["退休证"], dates=["长期"]),
            "退休证_长期")

    def test_retirement_cert_with_keyword(self):
        self.assertEqual(
            nm.build_name("人员", "退休证", keywords=["军转干"], dates=["长期"]),
            "退休证_军转干_长期")

    def test_rehire_agreement_dedups_fixed_const(self):
        self.assertEqual(
            nm.build_name("人员", "返聘协议", keywords=["返聘协议"], dates=["20271231"]),
            "返聘协议_20271231")

    def test_rehire_agreement_with_keyword(self):
        self.assertEqual(
            nm.build_name("人员", "返聘协议", keywords=["退休返聘"], dates=["20271231"]),
            "返聘协议_退休返聘_20271231")

    def test_rank_cert_with_year_suffix(self):
        # 职称证书支持可选年份段：同一人同等级不同评审年份的多本证书并存
        self.assertEqual(
            nm.build_name("人员", "职称证书", keywords=["工程师", "市政道桥", "2009"]),
            "工程师_市政道桥_2009")
        self.assertEqual(
            nm.build_name("人员", "职称证书", keywords=["工程师", "市政道桥"]),
            "工程师_市政道桥")

    def test_rank_cert_year_suffix_validates(self):
        ok, issues = nm.validate("人员", "职称证书", "工程师_市政道桥_2009.png")
        self.assertTrue(ok, issues)
        ok2, _ = nm.validate("人员", "职称证书", "高级工程师_建筑工程.png")
        self.assertTrue(ok2)

    def test_org_structure_name_variants(self):
        # 企业介绍/组织架构：组织机构|组织机构图，统一必带上传日期
        self.assertEqual(
            nm.build_name("企业介绍", "组织架构", keywords=["组织机构"], dates=["20261004"]),
            "组织机构_20261004")
        self.assertEqual(
            nm.build_name("企业介绍", "组织架构", keywords=["组织机构图"], dates=["20261001"]),
            "组织机构图_20261001")
        ok, issues = nm.validate("企业介绍", "组织架构", "组织机构_20261004.png")
        self.assertTrue(ok, issues)
        ok2, _ = nm.validate("企业介绍", "组织架构", "组织机构图_20261001.png")
        self.assertTrue(ok2)
        # 无日期不合法（统一规则必带上传日期）
        ok3, _ = nm.validate("企业介绍", "组织架构", "组织机构.png")
        self.assertFalse(ok3)

    def test_keyword_sanitized(self):
        self.assertEqual(
            nm.build_name("资质", "资质证书", keywords=["ISO9001/质量"], dates=["20280101"]),
            "ISO9001-质量_20280101")

    def test_missing_keyword_raises(self):
        with self.assertRaises(nm.NamingError):
            nm.build_name("资质", "资质证书", dates=["20280101"])

    def test_id_card_requires_date(self):
        with self.assertRaises(nm.NamingError):
            nm.build_name("人员", "身份证")

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

    def test_personal_honor_to_person(self):
        # 个人荣誉归人员/个人荣誉（荣誉大类仅用于企业荣誉）
        self.assertEqual(nm.classify("优秀总监理工程师陈友龙_20250101.png")[:2], ("人员", "个人荣誉"))
        self.assertEqual(nm.classify("先进工作者_20250101.png")[:2], ("人员", "个人荣誉"))

    def test_enterprise_honor_to_honor(self):
        # 企业荣誉归荣誉/荣誉证书
        self.assertEqual(nm.classify("示范工程_20250101.png")[:2], ("荣誉", "荣誉证书"))
        self.assertEqual(nm.classify("标准化工地_20250101.png")[:2], ("荣誉", "荣誉证书"))

    def test_org_chart(self):
        # 组织架构图归企业介绍/组织架构，命名 组织机构图_上传日期
        self.assertEqual(nm.classify("组织机构图_20261001.png")[:2], ("企业介绍", "组织架构"))
        self.assertIn("组织机构图_20261001", nm.build_name("企业介绍", "组织架构", dates=["20261001"]))

    def test_company_history(self):
        # 企业历史归企业介绍/企业历史，命名 企业历史_上传日期
        self.assertEqual(nm.classify("企业历史_20261001.png")[:2], ("企业介绍", "企业历史"))
        self.assertEqual(nm.build_name("企业介绍", "企业历史", dates=["20261001"]), "企业历史_20261001")
        ok, issues = nm.validate("企业介绍", "企业历史", "企业历史_20261001.png")
        self.assertTrue(ok, issues)

    def test_sme_declaration(self):
        # 中小企业声明函归财务子目录，命名取年度（4位年份）
        self.assertEqual(nm.classify("中小企业声明函_2026.png")[:2], ("财务", "中小企业声明函"))
        self.assertEqual(nm.build_name("财务", "中小企业声明函", dates=["20260831"]), "中小企业声明函_2026")
        ok, issues = nm.validate("财务", "中小企业声明函", "中小企业声明函_2026.png")
        self.assertTrue(ok, issues)

    def test_acceptance_docs_to_project(self):
        # 验收类资料（概况表/竣工验收记录/竣工验收报告）统一归业绩文件（项目归组）
        for f in ["工程概况一览表_P0.png", "单位工程质量竣工验收记录_P1.png", "工程竣工验收报告_P0.png", "监理合同_P0.png"]:
            self.assertEqual(nm.classify(f)[:2], ("业绩", "业绩文件"), f)

    def test_unknown(self):
        self.assertEqual(nm.classify("随便一个名字"), (None, None, None))

    def test_guess_subtype(self):
        # 身份证新格式（身份证_日期）与岗位证书（关键字_日期）同构，guess_subtype 无法仅凭文件名区分
        # 注册证书（关键字_两日期）格式独特，可唯一判定
        self.assertEqual(nm.guess_subtype("人员", "监理工程师_20270101_20280101.jpg"), "注册证书")


class TestProjectFolder(unittest.TestCase):
    def test_build(self):
        self.assertEqual(
            nm.build_project_folder("和县某安置房监理", "20260101", "张三"),
            "和县某安置房监理_20260101_张三")

    def test_no_director(self):
        self.assertEqual(
            nm.build_project_folder("和县某项目监理", "20260101"),
            "和县某项目监理_20260101_无总监")

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
