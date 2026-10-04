# -*- coding: utf-8 -*-
import re

src = open(r"E:\bidcraft_skill\dev\docxtpl_eval\_deps\docxtpl\template.py", encoding="utf-8").read()
for i, line in enumerate(src.splitlines(), 1):
    if re.search(r"[\"']tr[\"']|TR_|row", line) and ("tag" in line or "xml" in line or "re." in line or "replace" in line):
        print(i, line[:200])
