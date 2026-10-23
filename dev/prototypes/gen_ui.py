# -*- coding: utf-8 -*-
"""标书匠软件 UI 可复跑生成器 v1

用法:
  python gen_ui.py                     # 用默认数据源生成默认产物
  python gen_ui.py --data <json路径>   # 换数据源（如 layout-presets.json 其他版本）
  python gen_ui.py --out <html路径>    # 指定输出
  python gen_ui.py --check             # 生成后自动跑 shot.py 自检

设计原则:
  - 数据源唯一真值 = layout-presets.json（JSON 升级后重跑本脚本即同步 UI）
  - 模板 = _template_ui.html（骨架固定，数据段为 /*__STYLE_DATA__*/ 占位符）
  - 产物 = 标书匠软件UI.html（交付物，单文件自包含，可分发）
"""
import argparse
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TMPL = os.path.join(HERE, "_template_ui.html")
DEFAULT_DATA = r"E:\bidcraft_skill\共享资源\技术标风格\layout-presets.json"
DEFAULT_OUT = os.path.join(HERE, "标书匠软件UI.html")
SHOT = r"C:\Users\hxjlcj\AppData\Local\Doubao\User Data\Default\.doubao\agent_mode\workspace\.skills\html\scripts\shot.py"

GROUPS = [
    ("presets", "版面版式"), ("palettes", "配色方案"), ("covers", "封面样式"),
    ("decorations", "装饰风格"), ("fontSchemes", "字体方案"), ("imageRatios", "图文比例"),
    ("imageRules", "配图规则"), ("imageLayouts", "配图排版"), ("pageSetups", "页面设置"),
    ("headingSystems", "标题体系"), ("tocStyles", "目录版式"), ("tableStyles", "表格样式"),
    ("captionSystems", "图表编号"), ("paragraphStyles", "段落样式"), ("headerFooters", "页眉页脚"),
]


def build_style_data(d):
    """从 layout-presets.json 生成 STYLE_DATA 中间串（不含 window.STYLE_DATA= 前缀）"""
    lines = ["{groups:["]
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
    lines.append("}")
    return "".join(lines)


def generate(data_path, out_path):
    d = json.load(io.open(data_path, encoding="utf-8"))
    sd = build_style_data(d)
    tmpl = io.open(TMPL, encoding="utf-8").read()
    if "__STYLE_DATA__" not in tmpl:
        sys.exit("模板缺少 /*__STYLE_DATA__*/ 占位符：" + TMPL)
    html = tmpl.replace("/*__STYLE_DATA__*/", "window.STYLE_DATA=" + sd + ";")
    io.open(out_path, "w", encoding="utf-8", newline="").write(html)
    print("GENERATED", out_path, len(html), "chars")
    print("  data:", data_path)
    print("  groups:", len(GROUPS), "default keys:", len(d.get("default", {})))
    return out_path


def run_check(path):
    print("== shot.py 自检 ==")
    subprocess.run([sys.executable, SHOT, path])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="标书匠软件 UI 生成器")
    ap.add_argument("--data", default=DEFAULT_DATA, help="layout-presets.json 路径")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 HTML 路径")
    ap.add_argument("--check", action="store_true", help="生成后自动跑 shot.py 自检")
    a = ap.parse_args()
    p = generate(a.data, a.out)
    if a.check:
        run_check(p)
