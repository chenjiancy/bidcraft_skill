# -*- coding: utf-8 -*-
"""一次性：从 标书匠软件UI-原型V3.html 制作模板 _template_ui.html
把内联 STYLE_DATA 数据段替换为占位符 /*__STYLE_DATA__*/，其余骨架原样保留。
"""
import io

SRC = r"E:\bidcraft_skill\dev\prototypes\标书匠软件UI-原型V3.html"
DST = r"E:\bidcraft_skill\dev\prototypes\_template_ui.html"

h = io.open(SRC, encoding="utf-8").read()
start = h.index("window.STYLE_DATA={groups:[")
end = h.index("(function(){", start)
new = h[:start] + "/*__STYLE_DATA__*/\n" + h[end:]
io.open(DST, "w", encoding="utf-8", newline="").write(new)
print("TEMPLATE OK", DST, len(new), "chars")
