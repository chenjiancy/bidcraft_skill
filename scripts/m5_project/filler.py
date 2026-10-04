# -*- coding: utf-8 -*-
"""
M5 填充引擎 v1.0：项目模板（冻结版 docx）→ 商务标（图文混排 docx）。

流程（对每个模板文件）：
  1) 扫描占位符【xxx】（段落 + 表格单元格，跨 run）；
  2) 文字占位填充：素材清单 / 企业基础信息 / 投标截止日期（【日期】=投标截止日）/ 招标人；
  3) 图片占位填充：素材库取图 → 按系统级图片尺寸口径（image_spec）插入 → 删除占位段；
     缺图 → 删除占位段 + 缺图清单；
  4) 简历表（附表8）：OCR 识别素材库「人员/<姓名>/简历/*.png」文字 → 填 17 个占位；
     无扫描件 → 占位保留 + 待补字段清单；
  5) 表格填充：附表6/7 人员表按 personnel；附表2 业绩汇总表按 performance；
     附表9 仪器设备表固定不动；
  6) 文字占位无映射/值缺失 → 占位保留 + 待补字段清单（交标前人工补）。

输出：商务标/（10 docx 同名）+ 生成记录.json + 缺图清单.md + 待补字段清单.md。

⑦ 超行数拆分：本文件为薄门面（facade），按职责拆至 fill_common（常量/依赖探测）、
fill_ocr（简历 OCR）、fill_combo（白名单/组合构建）、fill_text（文字占位）、
fill_images（图片插入）、fill_tables（表格填充）、fill_main（fill_project 主流程）；
对外符号（fill_project/_parse_cert/_fill_image_placeholders 等）全部原样再导出。
"""
from .fill_common import (FILL_ID, FILL_VERSION, HAVE_DOCX, FillError, Cm, Document, qn)  # noqa: F401
from .fill_ocr import *      # noqa: F401,F403
from .fill_combo import *    # noqa: F401,F403
from .fill_text import *     # noqa: F401,F403
from .fill_images import *   # noqa: F401,F403
from .fill_tables import *   # noqa: F401,F403
from .fill_main import *     # noqa: F401,F403
