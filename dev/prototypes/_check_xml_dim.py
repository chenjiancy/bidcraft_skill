# -*- coding: utf-8 -*-
"""XML 层校验：s30 section-band 底纹、s21/s22 图宽(EMU)、s27 页眉对齐。"""
import re
import zipfile

OUT = r"E:\bidcraft_skill\dev\reports\dimension-samples"


def getxml(name):
    z = zipfile.ZipFile(r"%s\%s.docx" % (OUT, name))
    return z.read("word/document.xml").decode("utf-8", "ignore")


def emu_cm(emu):
    return round(int(emu) / 360000.0, 1)


# 1) s30：含 section-band 底纹的标题段（检查 w:shd fill 出现且紧邻标题 run）
xml = getxml("s30_分隔页_章首色带")
shd = re.findall(r'<w:shd[^>]*w:fill="([0-9A-Fa-f]{6})"', xml)
print("s30 底纹数:", len(shd), "样本:", shd[:6])
# 标题段底纹：找含"一、工程概况"的 w:t 所在段落前是否有 shading
idx = xml.find("一、工程概况")
seg = xml[max(0, idx - 1200):idx]
print("s30 标题前 1200 字符内是否有 shd:", "<w:shd" in seg)

# 2) s21/s22 图片宽度（w:extent cx）
for name in ("s21_图比_高图比50", "s22_图比_低图比10", "s00_默认基线"):
    x = getxml(name)
    ext = re.findall(r'<wp:extent[^>]*cx="(\d+)"', x)
    print(name, "图宽cm:", [emu_cm(e) for e in ext])

# 3) s27 页眉对齐
x = getxml("s27_页眉页脚_居中庄重")
hdr = x[x.find("<w:headerReference"):]
print("s27 页眉存在:", bool(hdr))
# 页眉段落对齐（页眉在单独 header1.xml）
z = zipfile.ZipFile(r"%s\s27_页眉页脚_居中庄重.docx" % OUT)
h1 = z.read("word/header1.xml").decode("utf-8", "ignore")
print("s27 header1 jc=center:", 'w:jc w:val="center"' in h1)
