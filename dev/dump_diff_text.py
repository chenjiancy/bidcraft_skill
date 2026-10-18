# -*- coding: utf-8 -*-
"""导出差异逐项文本：小文件全量 + 资格证明表摘要。"""
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理"
d = json.load(open(BASE + r"\招标解析\差异清单.json", encoding="utf-8"))
diffs = d["差异"]

# 资格证明表以外的文件逐项输出
big = "资格证明及辅助资料表.docx"
for f in [x["文件"] for x in diffs]:
    pass
files_order = []
seen = set()
for x in diffs:
    if x["文件"] not in seen:
        seen.add(x["文件"]); files_order.append(x["文件"])

CAT_SHORT = {"content_diff": "固定文字差异", "placeholder_zone": "填写位置",
             "only_template": "模板独有", "only_contract": "契约独有"}

for f in files_order:
    fr = [x for x in diffs if x["文件"] == f]
    print("=" * 100)
    print("【%s】共 %d 项（update %d / keep %d）" % (f, len(fr),
          sum(1 for x in fr if x["建议"] == "update"), sum(1 for x in fr if x["建议"] == "keep")))
    if f == big:
        # 摘要：按位置段统计 + 代表性项
        import collections
        pos_cat = collections.Counter((x["位置"][:12], x["类别"]) for x in fr)
        print("  位置段×类别分布（前 40 个段）：")
        for (pos, c), n in sorted(pos_cat.items(), key=lambda kv: -kv[1])[:40]:
            print("    [%s] %s × %d" % (pos, CAT_SHORT[c], n))
        # 有文本的代表性差异（模板或契约非空且长度>1）
        shown = 0
        for x in fr:
            t, c = (x["模板"] or "").strip(), (x["契约"] or "").strip()
            if len(t) > 1 or len(c) > 1:
                print("    例 %s | %s | 建议%s" % (x["位置"], CAT_SHORT[x["类别"]], x["建议"]))
                if t: print("      模板: %s" % t[:90])
                if c: print("      契约: %s" % c[:90])
                shown += 1
                if shown >= 25: break
        print("    ……（其余见审阅页）")
        continue
    for x in fr:
        t = (x["模板"] or "").strip() or "（模板无此内容）"
        c = (x["契约"] or "").strip() or "（招标无此内容）"
        print("  %s | %s | 建议:%s" % (x["位置"], CAT_SHORT[x["类别"]], x["建议"]))
        print("    模板: %s" % t[:120])
        print("    契约: %s" % c[:120])
