# -*- coding: utf-8 -*-
"""下载新增施工实景图（混凝土泵车/挖掘机/钢筋绑扎），供配图排版效果展示"""
import urllib.request, os

BASE = r"E:\bidcraft_skill\dev\prototypes\assets"
JOBS = [
    ("施工照片-混凝土泵车.jpg", "https://aka.doubaocdn.com/s/uJeG5JIuv0"),
    ("施工照片-挖掘机.jpg",     "https://aka.doubaocdn.com/s/LqFZd7tkvm"),
    ("施工照片-钢筋绑扎.jpg",   "https://aka.doubaocdn.com/s/YU25rywO2R"),
]
os.makedirs(BASE, exist_ok=True)
for name, url in JOBS:
    path = os.path.join(BASE, name)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    print(name, os.path.getsize(path))
