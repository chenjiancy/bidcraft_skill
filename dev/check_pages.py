# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r'E:\bidcraft_skill\dev')
from docx import Document
from docx.oxml.ns import qn

def scan(f, label, cap_paras=4000):
    print('==== %s ====' % label)
    doc = Document(f)
    body = doc.element.body
    # 遍历 body 直接子元素，识别分页符/分节符边界
    page_break_after = []
    import re
    idx = 0
    cur_sect = 1
    texts = []
    for child in body.iterchildren():
        tag = child.tag.split('}')[-1]
        if tag == 'p':
            xml = child.xml
            has_page_break = 'w:type="page"' in xml
            # 段落文本
            t = ''.join(n.text or '' for n in child.iter(qn('w:t')))
            if has_page_break and t.strip():
                page_break_after.append(t.strip()[:40])
            texts.append(t)
        elif tag == 'sectPr':
            cur_sect += 1
    print('分节符数量: %d-1=%d（多节即分页）' % (cur_sect, cur_sect-1))
    print('分页符后首段（新页开头内容）:')
    for t in page_break_after[:40]:
        print('  |', t)
    # 每个分页符之间的段落首文本 = 新页内容
    return page_break_after

# 整本制文件
f1 = r'E:\天翼同步盘\投标文件\2025年\和县党校房屋立面、屋顶防水及智慧校园等基础设施维修改造建设项目监理\投标文件（有章版）.docx'
scan(f1, '和县党校 投标文件（有章版）')
