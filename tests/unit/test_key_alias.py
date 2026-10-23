# -*- coding: utf-8 -*-
"""L1 单测：键名规范表（key_alias）——白名单完整性、别名冲突、行级键判定。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

from m5_project import key_alias  # noqa: E402


class TestKeySpec(unittest.TestCase):
    def test_spec_self_check_clean(self):
        """别名冲突/撞名自检必须通过。"""
        self.assertEqual(key_alias.check_spec(), [])

    def test_key_spec_covers_fill_v_keys(self):
        """键名规范表必须覆盖 fill-tpl V 字典的全部现行键（防漂移）。"""
        for mk in (
            "project_name", "project_code", "bid_date", "buyer_name",
            "company_name", "company_nature", "company_address",
            "bank_name", "bank_account", "姓名", "性别", "年龄", "职务",
            "agent_name", "agent_gender", "agent_age", "agent_title",
            "agent_id", "license_no", "日期", "项目说明",
            "supervisor_name", "supervisor_major", "bid_price_num",
        ):
            self.assertIn(mk, key_alias.KEY_SPEC, "V 键未登记：%s" % mk)

    def test_aliases_no_collision(self):
        """别名不得与行级键/机器键冲突。"""
        al = key_alias.aliases()
        self.assertNotIn("人员姓名", al, "人员姓名是行级键，不得作别名")
        self.assertNotIn("业绩项目名称", al, "业绩项目名称是行级键，不得作别名")
        self.assertNotIn("姓名", al, "姓名是机器键，别名不能撞机器键")


class TestRegistered(unittest.TestCase):
    def test_is_registered(self):
        self.assertTrue(key_alias.is_registered("project_name"))
        self.assertTrue(key_alias.is_registered("企业名称"))       # 别名
        self.assertTrue(key_alias.is_registered("人员姓名"))       # 行级键
        self.assertTrue(key_alias.is_registered("业绩联系人"))     # 行级键
        self.assertFalse(key_alias.is_registered("project_name_typo"))
        self.assertFalse(key_alias.is_registered("未知键"))

    def test_registered_keys_contains_all_sources(self):
        reg = key_alias.registered_keys()
        self.assertIn("project_name", reg)
        self.assertIn("企业名称", reg)
        self.assertIn("人员姓名", reg)
        self.assertIn("业绩合同金额", reg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
