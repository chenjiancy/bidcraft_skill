# -*- coding: utf-8 -*-
"""⑦ filler 拆包 · 公共：常量 / FillError / docx 依赖探测。"""
import re

FILL_ID = "m5-bid-fill"
FILL_VERSION = "v1.0"

try:
    from docx import Document
    from docx.shared import Cm
    from docx.oxml.ns import qn
    HAVE_DOCX = True
except Exception:                                    # pragma: no cover
    Document = Cm = qn = None
    HAVE_DOCX = False


class FillError(RuntimeError):
    pass


DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
