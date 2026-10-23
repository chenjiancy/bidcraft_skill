# -*- coding: utf-8 -*-
"""从 layout-presets.json v1.4 提取版面设计器原型内联数据（精简字段，保真：数量/默认位/暗标标记）。"""
import json
from pathlib import Path

SRC = Path(r"E:\bidcraft_skill\共享资源\技术标风格\layout-presets.json")
OUT = Path(r"E:\bidcraft_skill\dev\prototypes\_designer_data.json")

doc = json.loads(SRC.read_text(encoding="utf-8"))

GROUPS = [
    ("preset", "presets", "版面范式", ["id", "name", "docx"]),
    ("palette", "palettes", "配色方案", ["id", "name", "primary", "accent", "heading", "tableFill", "coverBg", "coverBgEnd", "darkOk", "recommendedFor"]),
    ("cover", "covers", "封面版式", ["id", "name", "docx", "darkOk"]),
    ("decoration", "decorations", "装饰强度", ["id", "name", "docx", "darkOk"]),
    ("font", "fontSchemes", "字体方案", ["id", "name", "heading", "body", "sizes", "lineSpacing", "darkOk"]),
    ("imageRatio", "imageRatios", "图文比例", ["id", "name", "ratio", "darkOk"]),
    ("imageRule", "imageRules", "配图规则", ["id", "name", "source", "darkOk"]),
    ("imageLayout", "imageLayouts", "配图排版", ["id", "name", "darkOk"]),
    ("pageSetup", "pageSetups", "页面设置", ["id", "name", "margin", "darkOk"]),
    ("headingSystem", "headingSystems", "标题体系", ["id", "name", "levels", "numbering", "darkOk"]),
    ("tocStyle", "tocStyles", "目录版式", ["id", "name", "leading", "darkOk"]),
    ("tableStyle", "tableStyles", "表格样式", ["id", "name", "lines", "headerFill", "darkOk"]),
    ("captionSystem", "captionSystems", "图表编号", ["id", "name", "numbering", "darkOk"]),
    ("paragraphStyle", "paragraphStyles", "段落样式", ["id", "name", "lineSpacing", "align", "darkOk"]),
    ("headerFooter", "headerFooters", "页眉页脚", ["id", "name", "header", "footer", "pageMode", "darkOk"]),
]

out = {"schema": doc.get("schema"), "version": doc.get("version"),
       "default": doc.get("default") or {}, "fontDefaults": doc.get("fontDefaults") or {},
       "darkInject": {"font": "dark-safe", "imageRatio": "none", "pageSetup": "p7-hb-25-20",
                      "headingSystem": "h2-tender-arabic", "tocStyle": "t3-qinghai-nopage",
                      "tableStyle": "tb7-dark-0.5", "captionSystem": "c9-dark-appendix",
                      "paragraphStyle": "pa3-hebei-30", "headerFooter": "hf9-dark-none"},
       "groups": [], "combos": []}

for key, arr_key, label, fields in GROUPS:
    rows = doc.get(arr_key) or []
    items = []
    for r in rows:
        it = {}
        for f in fields:
            v = r.get(f)
            if v is not None:
                it[f] = v
        items.append(it)
    out["groups"].append({"key": key, "arr": arr_key, "label": label, "items": items})

for c in doc.get("recommendedCombos") or []:
    out["combos"].append({"id": c.get("id"), "name": c.get("name"),
                          "bidType": c.get("bidType"), "why": c.get("why"),
                          "layoutCombo": c.get("layoutCombo") or {}})

OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
print("groups:", len(out["groups"]), "| combos:", len(out["combos"]), "| bytes:", OUT.stat().st_size)
for g in out["groups"]:
    print(" ", g["key"], len(g["items"]))
