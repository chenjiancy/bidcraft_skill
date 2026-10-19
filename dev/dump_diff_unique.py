# -*- coding: utf-8 -*-
"""去重：位置+类别+模板+契约 相同的差异合并计数 → 唯一差异项清单（会话展示）。"""
import json, io, sys, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理"
d = json.load(open(BASE + r"\招标解析\差异清单.json", encoding="utf-8"))
diffs = d["差异"]

files = []
seen = set()
for x in diffs:
    if x["文件"] not in seen:
        seen.add(x["文件"]); files.append(x["文件"])

CAT_SHORT = {"content_diff": "固定文字差异", "placeholder_zone": "填写位置",
             "only_template": "模板独有", "only_contract": "契约独有"}

for f in files:
    fr = [x for x in diffs if x["文件"] == f]
    key = lambda x: (x["位置"], x["类别"], (x["模板"] or "").strip(), (x["契约"] or "").strip(), x["建议"])
    grp = collections.OrderedDict()
    for x in fr:
        grp.setdefault(key(x), []).append(x)
    print("### %s | 原始 %d 项 → 去重唯一 %d 项（update %d / keep %d）" % (
        f, len(fr), len(grp),
        sum(1 for k in grp if k[4] == "update"),
        sum(1 for k in grp if k[4] == "keep")))
    for k, xs in grp.items():
        pos, cat, tpl, ctr, sug = k
        n = len(xs)
        dup = (" ×%d" % n) if n > 1 else ""
        print("  [%s%s] %s | %s | 建议:%s" % (pos, dup, CAT_SHORT[cat], ",".join(sorted({x["契约项"] for x in xs})), sug))
        if tpl: print("      模板: %s" % tpl[:100])
        if ctr: print("      契约: %s" % ctr[:100])
