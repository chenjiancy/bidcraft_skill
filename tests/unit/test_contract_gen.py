# -*- coding: utf-8 -*-
"""unit · M5 内容契约 JSON 生成规则（contract_gen 锚点定位）。

样例 docx 复刻「第七章 响应文件格式」真实结构（封面→开标一览表→投标函→
附录→法代→授权→监理大纲→资格证明附表1-10→承诺函），验证各契约项块范围。
"""
import os
import sys
import tempfile
import unittest

from docx import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from m5_project import contract_gen as cg  # noqa: E402
from m5_project.gen_blocks import _extract_blocks  # noqa: E402


def _build_sample_docx(path):
    """按真实格式章节结构构造样例 docx（段落级复刻）。"""
    doc = Document()
    lines = [
        # —— 招标文件前置内容 ——
        "第一章 采购公告",
        "安徽恒信腾达项目管理咨询有限公司受和县住房和城乡建设局委托…",
        # —— 目录条目（带页码尾，不得被误认为格式章节）——
        "目录",
        "第一章采购公告3",
        "第六章响应文件格式42",
        # —— 正文章节导航列表（无页码，位于供应商须知内，离锚点远）——
        "第一章采购公告",
        "第六章响应文件格式",
        "第七章附件",
        "13.2供应商应认真阅读和充分理解采购文件中所有的内容",
        # —— 格式章节 ——
        "第七章 响应文件格式",
        "注明正本或副本",
        "项目名称：和县2026年老旧小区改造项目（EPC总承包）监理",
        "项目编号：HXTD-2026-018",
        "响",
        "应",
        "文",
        "件",
        "供应商名称(盖章)：______________",
        "日期：    年  月   日",
        "开标一览表",
        "项目名称",
        "项目编号",
        "投标总价（人民币）",
        "本项目的监理费用投标报价为       元",
        "项目总监理工程师",
        "供应商：（盖单位公章）",
        "一、投标函及投标函附录",
        "（一）投 标 函（格式）",
        "致采购人：（单位名称）",
        "1、根据（项目名称）采购文件，经考察现场…",
        "我方愿以《开标一览表》中所报的投标报价进行投标",
        "供应商：（盖单位公章）",
        "（二）投标函附录",
        "序号",
        "项目",
        "内容",
        "1",
        "履约保证金",
        "见投标函",
        "二、法人代表资格证明（格式）",
        "（一）法定代表人资格证明书",
        "单位名称：",
        "供应商：（盖单位公章）",
        "（二）授权委托书（若无授权代理人，则不需提供）",
        "本授权委托书声明：",
        "授权代理人：",
        "三、监理管理文件（监理大纲）",
        "1、供应商对监理大纲内容的阐述",
        "监理管理文件（监理大纲）正文部分",
        "四、资格证明及辅助资料表",
        "资格证明和辅助资料表包括 表1 组织机构",
        "表2 已完成类似工程监理项目情况汇总表",
        "表3 已完成类似工程监理项目情况表",
        "表4 正在监理类似工程监理项目情况汇总表",
        "表5 正在监理类似工程监理项目情况表",
        "表6 监理人员资质表",
        "表7 监理机构监理人员配备表",
        "表8 拟投入监理人员简历表",
        "表9 现场监理机构配备仪器设备表",
        "表10 其他资料（如各种奖励和处罚）表",
        "附表 1:",
        "组  织  机  构",
        "企业名称",
        "组织机构框图",
        "附表 2：",
        "已 完 类 似 工 程 监 理 项 目 情 况 汇 总 表",
        "序号",
        "业主名称",
        "附表 3：",
        "已 完 类 似 工 程 监 理 项 目 情 况 表",
        "业主单位",
        "附表 4：",
        "正 在 监 理 类 似 工 程 监 理 项 目 情 况 汇 总 表",
        "附表 5：",
        "正 在 监 理 类 似 工 程 监 理 项 目 情 况 表",
        "附表 6：",
        "监 理 人 员 资 质 表",
        "项目总监理工程师",
        "附表 7：",
        "监 理 机 构 监 理 人 员 配 备 表",
        "序号",
        "附表 8：",
        "拟 投 入 监 理 人 员 简 历 表",
        "附表 9：",
        "现 场 监 理 机 构 配 备 仪 器 设 备 表",
        "附表 10：",
        "其 他 资 料 （ 如 各 种 奖 励 和 处 罚 ） 表",
        "项目总监到岗履约约束条款：",
        "承诺函",
        "在本项目中标后,合同签订前,拟派本次项目的项目总监能够从其他项目变更至本项目",
        "供应商单位（盖章）：",
    ]
    for ln in lines:
        doc.add_paragraph(ln)
    doc.save(path)
    return path


class TestContractGen(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bidcraft_contract_")
        cls.docx = _build_sample_docx(os.path.join(cls._tmp, "sample.docx"))
        cls.blocks, _ = _extract_blocks(cls.docx)
        cls.contract = cg.build_contract(cls.blocks, "测试项目")

    def test_chapter_detected(self):
        self.assertIn("响应文件格式", self.contract["格式章节"])

    def test_toc_and_nav_noise_excluded(self):
        """目录条目（…格式42）与正文导航列表不得抢跑：章节起点=真正的格式章节。"""
        _, anchors = cg.locate_anchors(self.blocks)
        # 开标一览表锚点（F02）必须落在正文格式章节内（远离目录/导航块）
        self.assertGreater(anchors["F02"], 10)
        # 章节标题 = 「第七章 响应文件格式」（正文），非目录/导航
        chapter_title = self.contract["格式章节"]
        self.assertIn("第七章", chapter_title)
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        lo, _ = by_id["F01"]["块范围"]
        self.assertIn("响应文件格式", cg._clean(cg._para_text(self.blocks[lo]["node"])))
        self.assertIn("第七章", cg._clean(cg._para_text(self.blocks[lo]["node"])))

    def test_anchors_all_found(self):
        _, anchors = cg.locate_anchors(self.blocks)
        for aid in ["F02", "F03a", "F03b", "F04a", "F04b", "F05",
                    "F06a", "F06b", "F06c", "F06d", "F06e", "F06f",
                    "F06g", "F06h", "F06i", "F06j", "F06k", "F06l"]:
            self.assertIn(aid, anchors, "锚点 %s 未命中" % aid)

    def test_missing_anchors_empty(self):
        """本项目无 中小企业声明函/开户许可证承诺函 → F09/F13/F14 块范围留空。"""
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        self.assertEqual(by_id["F09"]["块范围"], [])
        self.assertEqual(by_id["F13"]["块范围"], [])
        self.assertEqual(by_id["F14"]["块范围"], [])

    def test_cover_span(self):
        """F01 封面：第七章标题 → 开标一览表块-1；F02 开标一览表从其块起。"""
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        lo, hi = by_id["F01"]["块范围"]
        self.assertEqual(self.blocks[lo]["type"], "para")
        self.assertIn("响应文件格式", cg._clean(cg._para_text(self.blocks[lo]["node"])))
        # 开标一览表标题块 = F01 终点+1 = F02 起点
        kb = next(i for i, blk in enumerate(self.blocks)
                  if blk.get("type") == "para"
                  and "开标一览表" in cg._clean(cg._para_text(blk["node"])))
        self.assertEqual(hi, kb - 1)
        lo2, hi2 = by_id["F02"]["块范围"]
        self.assertEqual(lo2, kb)
        # F02 终点 = 「一、投标函及投标函附录」-1
        next_a = next(i for i, blk in enumerate(self.blocks)
                      if blk.get("type") == "para"
                      and cg._clean(cg._para_text(blk["node"])) == "一、投标函及投标函附录")
        self.assertEqual(hi2, next_a - 1)

    def test_bid_letter_span(self):
        """F03a 投标函：一、投标函及投标函附录 →（二）投标函附录-1。"""
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        lo, hi = by_id["F03a"]["块范围"]
        self.assertIn("投标函", cg._clean(cg._para_text(self.blocks[lo]["node"])))
        next_a = next(i for i, blk in enumerate(self.blocks)
                      if blk.get("type") == "para"
                      and cg._clean(cg._para_text(blk["node"])) == "（二）投标函附录")
        self.assertEqual(hi, next_a - 1)

    def test_attach_table_spans(self):
        """附表1-10 依次相邻且不重叠（F06b 起点=附表1，F06k 终点=承诺函-1）。"""
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        prev_hi = None
        for i in range(10):
            it = by_id["F06%c" % (chr(ord("b") + i))]
            lo, hi = it["块范围"]
            self.assertGreater(hi, lo)
            if prev_hi is not None:
                self.assertGreaterEqual(lo, prev_hi + 1)  # 左闭右开不重叠
            prev_hi = hi
        # F06k（附表10）终点 = 承诺函块-1
        lo_k, hi_k = by_id["F06k"]["块范围"]
        c_block = next(i for i, blk in enumerate(self.blocks)
                       if blk.get("type") == "para"
                       and cg._clean(cg._para_text(blk["node"])) == "承诺函")
        self.assertEqual(hi_k, c_block - 1)
        self.assertEqual(by_id["F07"]["块范围"][0], hi_k + 1)

    def test_commitment_span(self):
        """F07 承诺函：承诺函块 → 章节尾（无声明函时到末尾）。"""
        by_id = {it["id"]: it for it in self.contract["格式文件"]}
        lo, hi = by_id["F07"]["块范围"]
        self.assertIn("承诺函", cg._para_text(self.blocks[lo]["node"]))
        self.assertEqual(hi, len(self.blocks) - 1)

    def test_no_duplicate_ids(self):
        ids = [it["id"] for it in self.contract["格式文件"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
