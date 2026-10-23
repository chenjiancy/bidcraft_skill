# -*- coding: utf-8 -*-
import json

doc = json.load(open(r"E:\bidcraft_skill\共享资源\技术标风格\layout-presets.json", encoding="utf-8"))
print("keys:", list(doc.keys()))
presets = doc["presets"]
print("preset count:", len(presets))
for p in presets:
    if p["id"] in ("single-column", "tabular", "card", "image-left", "two-column", "divider"):
        print("==", p["id"], p.get("name"))
        print(json.dumps(p, ensure_ascii=False, indent=1)[:1000])
