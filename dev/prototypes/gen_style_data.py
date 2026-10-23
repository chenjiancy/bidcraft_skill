# -*- coding: utf-8 -*-
"""从 layout-presets.json v1.4 生成风格配置屏内联 JS 数据（精简字段）"""
import json

SRC = r"E:\bidcraft_skill\共享资源\技术标风格\layout-presets.json"
OUT = r"E:\bidcraft_skill\dev\prototypes\_style_data.js.txt"

d = json.load(open(SRC, encoding="utf-8"))

GROUPS = [
    ("presets", "版面版式"), ("palettes", "配色方案"), ("covers", "封面样式"),
    ("decorations", "装饰风格"), ("fontSchemes", "字体方案"), ("imageRatios", "图文比例"),
    ("imageRules", "配图规则"), ("imageLayouts", "配图排版"), ("pageSetups", "页面设置"),
    ("headingSystems", "标题体系"), ("tocStyles", "目录版式"), ("tableStyles", "表格样式"),
    ("captionSystems", "图表编号"), ("paragraphStyles", "段落样式"), ("headerFooters", "页眉页脚"),
]

def pick(it):
    return {
        "id": it.get("id", ""),
        "n": it.get("name", ""),
        "p": it.get("primary", ""),
        "a": it.get("accent", ""),
        "do": it.get("darkOk", None),
    }

lines = []
lines.append("window.STYLE_DATA={groups:[")
for key, label in GROUPS:
    items = d.get(key, [])
    arr = ", ".join(
        '{"id":"%s","n":"%s","p":"%s","a":"%s","do":%s}'
        % (it.get("id", ""), it.get("name", "").replace('"', "'"),
           it.get("primary", "") or "", it.get("accent", "") or "",
           "null" if it.get("darkOk") is None else ("true" if it.get("darkOk") else "false"))
        for it in items
    )
    lines.append('{key:"%s",label:"%s",items:[%s]},' % (key, label, arr))
lines.append("],default:")
lines.append(json.dumps(d.get("default", {}), ensure_ascii=False))
lines.append("};")

open(OUT, "w", encoding="utf-8").write("".join(lines))
print("OK", len("".join(lines)), "chars ->", OUT)
