# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, r'E:\bidcraft_skill\dev')
from docx import Document
from docx.oxml.ns import qn

f = r'E:\天翼同步盘\投标文件\2025年\和县党校房屋立面、屋顶防水及智慧校园等基础设施维修改造建设项目监理\和县\投标文件（有章版）.docx'
doc = Document(f)
body = doc.element.body
page_break_after = []
cur_sect = 1
sect_locs = []
for idx, child in enumerate(body.iterchildren()):
    tag = child.tag.split('}')[-1]
    if tag == 'p':
        xml = child.xml
        has_page_break = 'w:type="page"' in xml
        t = ''.join(n.text or '' for n in child.iter(qn('w:t')))
        if has_page_break and t.strip():
            page_break_after.append(t.strip()[:50])
    elif tag == 'sectPr':
        sect_locs.append(idx)
        cur_sect += 1

print('总元素=%d，分节符=%d，分页符后首段=%d' % (len(list(body.iterchildren())), cur_sect-1, len(page_break_after)))
print('=== 分页符后首段（新页开头）===')
for t in page_break_after:
    print('  |', t)
