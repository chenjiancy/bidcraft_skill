# -*- coding: utf-8 -*-
"""L1 单元测试：⑤ 混合检索 + 重排（n-gram 相似召回 + 字段加权重排）。
纯标准库，CI 双平台可跑；用临时企业 + 台账种子数据，不触碰真实素材库。"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS))
from _shared import core   # noqa: E402


class NgramTest(unittest.TestCase):
    def test_identical_is_1(self):
        self.assertAlmostEqual(core.ngram_cos("先进监理企业", "先进监理企业"), 1.0)

    def test_synonym_recall(self):
        """「先进监理企业」vs「优秀监理企业」：bigram 公共片段监理/理企/企业 → 中高相似。"""
        sim = core.ngram_cos("先进监理企业", "优秀监理企业")
        self.assertGreaterEqual(sim, 0.3, "同义变体应有明显相似度（实际 %.3f）" % sim)

    def test_unrelated_low(self):
        self.assertLess(core.ngram_cos("营业执照", "注册会计师"), 0.3)

    def test_empty(self):
        self.assertEqual(core.ngram_cos("", "营业执照"), 0.0)
        self.assertEqual(core.ngram_cos("营业执照", ""), 0.0)


class HybridQueryTest(unittest.TestCase):
    ENT = "检索测试监理有限公司"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bid_retr_")
        self.root = Path(self.tmp)
        self.lib = core.Library(self.root)
        self.ent, _ = self.lib.init_enterprise(self.ENT)
        rows = [
            core.new_ledger_row(category="荣誉", subtype="企业荣誉",
                                keywords="优秀监理企业",
                                rel_path="荣誉/优秀监理企业_20250101.png",
                                original_filename="优秀监理企业.png",
                                dates="20250101"),
            core.new_ledger_row(category="资质", subtype="营业执照",
                                keywords="营业执照",
                                rel_path="资质/营业执照_副本_长期.png",
                                original_filename="营业执照_副本_长期.png",
                                dates="长期"),
            core.new_ledger_row(category="资质", subtype="体系认证",
                                keywords="质量管理体系认证",
                                rel_path="资质/ISO9001_20260101.png",
                                original_filename="ISO9001_20260101.png",
                                dates="20260101"),
            core.new_ledger_row(category="财务", subtype="财务证明",
                                keywords="营业性收入",
                                rel_path="财务/营业性收入证明_20250101.png",
                                original_filename="营业性收入证明_20250101.png",
                                dates="20250101"),
        ]
        core.save_ledger(self.ent, rows)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_exact_outranks_fuzzy(self):
        """「营业执照」：精确命中(资质/营业执照)排第一；模糊伴行(营业性收入)也召回但排后。"""
        hits = core.query_hybrid(self.ent, keyword="营业执照")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["row"]["rel_path"], "资质/营业执照_副本_长期.png")
        self.assertIn("营业性收入", hits[1]["row"]["rel_path"])
        self.assertGreater(hits[0]["score"], hits[1]["score"])

    def test_fuzzy_recall_beyond_substring(self):
        """子串匹配 0 命中 → 混合检索仍召回「优秀监理企业」。"""
        exact = core.query(self.ent, keyword="先进监理企业")
        self.assertEqual(len(exact), 0, "in 子串匹配对同义变体漏召回")
        hits = core.query_hybrid(self.ent, keyword="先进监理企业")
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("优秀监理企业", hits[0]["row"]["rel_path"])
        self.assertGreater(hits[0]["score"], 0)

    def test_top_k_limit(self):
        hits = core.query_hybrid(self.ent, keyword="监理", top_k=1)
        self.assertLessEqual(len(hits), 1)

    def test_category_filter_applied(self):
        hits = core.query_hybrid(self.ent, category="资质", keyword="监理")
        self.assertTrue(all(h["row"]["category"] == "资质" for h in hits))
        self.assertNotIn("优秀监理企业", [h["row"]["rel_path"] for h in hits])

    def test_multi_term_sum(self):
        """多关键词取和：优秀(3 字段精确) + ISO9001(2 字段精确) 都应召回且分数>0。"""
        hits = core.query_hybrid(self.ent, keyword=["ISO9001", "优秀"])
        rels = [h["row"]["rel_path"] for h in hits]
        self.assertEqual(len(hits), 2)
        self.assertTrue(any("ISO9001" in r for r in rels))
        self.assertTrue(any("优秀监理企业" in r for r in rels))
        self.assertTrue(all(h["score"] > 0 for h in hits))
        # 「优秀」精确命中 3 字段(2.0+1.5+1.0) > 「ISO9001」精确命中 2 字段(2.0+1.0)
        self.assertIn("优秀监理企业", hits[0]["row"]["rel_path"])

    def test_no_keyword_returns_all(self):
        hits = core.query_hybrid(self.ent)
        self.assertEqual(len(hits), 4)
        self.assertTrue(all(h["score"] == 0 for h in hits))

    def test_date_filter_still_applies(self):
        hits = core.query_hybrid(self.ent, keyword="监理", expires_after="20260101")
        rels = [h["row"]["rel_path"] for h in hits]
        self.assertNotIn("荣誉/优秀监理企业_20250101.png", rels, "早于 20260101 的应被过滤")

    def test_non_hit_excluded(self):
        hits = core.query_hybrid(self.ent, keyword="完全无关词XYZ")
        self.assertEqual(len(hits), 0)


if __name__ == "__main__":
    unittest.main()
