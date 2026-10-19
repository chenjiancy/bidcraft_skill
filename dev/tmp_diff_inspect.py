# -*- coding: utf-8 -*-
import json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = r"E:\监理标书制作\和县建设工程监理有限公司\项目级\和县2026年老旧小区改造项目（EPC总承包）监理\招标解析\差异清单.json"
d = json.load(open(p, encoding="utf-8"))
print("顶层键:", list(d.keys()))
diffs = d["差异"]
print("差异数:", len(diffs))
print("首项字段:", list(diffs[0].keys()))
for f in diffs[0].keys():
    vals = [str(x.get(f))[:50] for x in diffs[:5]]
    print(f, "=>", vals)
