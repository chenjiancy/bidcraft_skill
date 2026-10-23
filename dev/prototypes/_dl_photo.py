# -*- coding: utf-8 -*-
"""下载素材库现场照片到原型 assets（本地相对路径引用，file:// 可用）。"""
import urllib.request
import ssl
from pathlib import Path

URL = "https://aka.doubaocdn.com/s/9TIjSr9tTI"
OUT = Path(r"E:\bidcraft_skill\dev\prototypes\assets") / "现场施工照片.jpg"

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
data = urllib.request.urlopen(req, timeout=60, context=ctx).read()
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_bytes(data)
print("saved:", OUT, len(data), "bytes")
