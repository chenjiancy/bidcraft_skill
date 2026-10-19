# -*- coding: utf-8 -*-
"""L1 image_ph_rules 单测：占位文案 = 素材清单唯一推导，gen/fill 共用同一规则树。"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
M5 = os.path.normpath(os.path.join(HERE, "..", "..", "scripts", "m5_project"))
sys.path.insert(0, M5)
from image_ph_rules import build_ph_rules, resolve_ph, iter_file_rules, PH_PREFIX  # noqa: E402

# 用和县2026真实素材清单做数据守卫（真实数据用例）
DATA_GUARD = os.path.join(HERE, "..", "..", "tests", "_data_guard.py")
MAT = os.path.join(
    "E:", os.sep, "监理标书制作", "和县建设工程监理有限公司", "项目级",
    "和县2026年老旧小区改造项目（EPC总承包）监理", "招标解析",
    "素材清单_和县2026年老旧小区改造项目（EPC总承包）监理.json")


def require_data():
    if not os.path.exists(MAT):
        raise unittest.SkipTest("真实素材清单缺失")
    with open(MAT, encoding="utf-8") as f:
        return json.load(f)


class TestPhRules(unittest.TestCase):
    def test_build_rules_with_real_material(self):
        mat = require_data()
        rules = build_ph_rules(mat)
        # 资格证明表：资质组 + 人员组×5 + 社保 + 附表10 三体系/总监职称/人员职称/示范/总监荣誉
        zgb = iter_file_rules(rules, "资格证明及辅助资料表.docx")
        self.assertGreaterEqual(len(zgb), 9, "资格表应有≥9条规则(资质/人员×5/社保/附表10×4)")
        phs = [r["ph"] for r in zgb]
        # 清单没有"先进（优秀）监理企业证书" → 不得生成该占位
        self.assertFalse(any("先进" in p for p in phs), "清单无先进证书时禁止生成占位")
        # 总监荣誉（清单有2张）→ 生成占位
        self.assertTrue(any("总监荣誉" in p for p in phs), "清单有总监荣誉应生成占位")
        # 业绩奖项文件：一三体系/二业绩/三总监职称/四人员职称/六示范/七总监荣誉（无五先进）
        award = iter_file_rules(rules, "投标单位业绩材料和奖项.docx")
        award_phs = [r["ph"] for r in award]
        self.assertTrue(any("三体系" in p for p in award_phs))
        self.assertTrue(any("业绩" in p for p in award_phs))
        self.assertTrue(any("总监" in p for p in award_phs))
        self.assertTrue(any("人员" in p and "职称" in p for p in award_phs))
        self.assertTrue(any("示范" in p for p in award_phs))
        self.assertTrue(any("总监荣誉" in p for p in award_phs))
        self.assertFalse(any("先进" in p for p in award_phs))

    def test_ph_unique_and_resolvable(self):
        mat = require_data()
        rules = build_ph_rules(mat)
        seen = set()
        for fname, phs in rules.items():
            for r in phs:
                self.assertNotIn(r["ph"], seen, "占位文案必须唯一:%s" % r["ph"])
                seen.add(r["ph"])
                self.assertEqual(r["ph"][:len(PH_PREFIX)], PH_PREFIX)
                hit = resolve_ph(r["ph"], rules)
                self.assertIsNotNone(hit, "占位必须可被 resolve_ph 解析:%s" % r["ph"])
                fname2, anchor, items, group = hit
                self.assertEqual(fname2, fname)
                self.assertIn(anchor[0], ("table", "para"))
                self.assertTrue(items, "每条规则至少1个素材:%s" % r["ph"])
                for f, spec, pb in items:
                    self.assertTrue(os.path.isfile(f), "素材文件必须存在:%s" % f)

    def test_person_group_content(self):
        mat = require_data()
        rules = build_ph_rules(mat)
        zgb = iter_file_rules(rules, "资格证明及辅助资料表.docx")
        # 每人(5人)一条人员组规则，占位文案含姓名
        person_rules = [r for r in zgb if r["group"].startswith("人员组-")]
        self.assertEqual(len(person_rules), 5)
        names = [r["group"].split("-", 1)[1] for r in person_rules]
        self.assertEqual(set(names), {"阮旭", "陈云", "陈阳", "裴友谊", "黄大海"})
        # 陈云（总监）含注册证书+高级职称+简历
        chen = [r for r in person_rules if r["group"].endswith("陈云")][0]
        specs = [spec for _, spec, _ in chen["items"]]
        self.assertIn("注册监理工程师证书", specs)
        # 陈阳含毕业证
        chenyang = [r for r in person_rules if r["group"].endswith("陈阳")][0]
        self.assertGreaterEqual(len(chenyang["items"]), 4, "陈阳应含岗位证+职称×2+简历+毕业证")

    def test_director_honor_two_places(self):
        mat = require_data()
        rules = build_ph_rules(mat)
        places = [fname for fname, phs in rules.items()
                  for r in phs if "总监荣誉" in r["ph"]]
        self.assertIn("资格证明及辅助资料表.docx", places, "附表10放总监荣誉")
        self.assertIn("投标单位业绩材料和奖项.docx", places, "业绩奖项文件放总监荣誉")
        # 两处数量一致（清单2张）
        zgb = [r for r in iter_file_rules(rules, "资格证明及辅助资料表.docx")
               if "总监荣誉" in r["ph"]][0]
        award = [r for r in iter_file_rules(rules, "投标单位业绩材料和奖项.docx")
                 if "总监荣誉" in r["ph"]][0]
        self.assertEqual(len(zgb["items"]), 2)
        self.assertEqual(len(zgb["items"]), len(award["items"]))

    def test_legal_agent_id_cards(self):
        """L2a：素材清单 企业基础信息 身份证字段 → 法代/授权占位生成（P0/P1 正反面）。"""
        mat = require_data()
        biz = mat.get("企业基础信息", {})
        if not (biz.get("法定代表人身份证") or biz.get("委托代理人身份证")):
            raise unittest.SkipTest("素材清单缺身份证字段（未重跑 proj-mat）")
        rules = build_ph_rules(mat)
        legal = iter_file_rules(rules, "法定代表人身份证明.docx")
        self.assertEqual(len(legal), 1, "法代身份证规则1条")
        self.assertIn("法定代表人身份证正、反面扫描件", legal[0]["ph"])
        self.assertEqual(len(legal[0]["items"]), 2, "法代身份证 P0/P1 两张")
        agent = iter_file_rules(rules, "授权委托书.docx")
        self.assertEqual(len(agent), 1, "代理身份证规则1条")
        self.assertEqual(len(agent[0]["items"]), 2, "代理身份证 P0/P1 两张")
        for f, spec, pb in legal[0]["items"] + agent[0]["items"]:
            self.assertTrue(os.path.isfile(f), "身份证素材存在:%s" % f)


if __name__ == "__main__":
    unittest.main(verbosity=2)
