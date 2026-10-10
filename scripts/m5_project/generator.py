# -*- coding: utf-8 -*-
"""
bidcraft · M5 项目模板生成器 —— 编排/生成层（确定性文件操作）

一句话职责
----------
把「企业模板（格式与排版契约，基底）+ 内容契约（招标解析投标文件格式，文字更新源）
+ 素材清单（占位符键/行数/份数）」合成为项目模板 docx 集，落盘 项目级/<项目>/项目模板/，
并登记产物基线（fb.register）。

动态语义（需求对齐 D4/D10/D12，用户 2026-10-10 纠正）：
  ① 格式与排版以企业模板为基底——项目模板从企业模板深拷贝，图片位置/大小随模板；
  ② 文字更新以内容契约为源——模板占位或模板已有内容除外，差异清单（proj-diff）
     列示后由用户决策（update=契约文字 / keep=模板文字），铁律 D25；
  ③ 素材占位按素材清单增减——简历表按人员份数复制、业绩表按素材行数增减、
     证书页数/行数动态调整。

本文件只做确定性操作；「哪些契约项生成/跳过、占位键怎么定」等语义判断
集中在 RULES 表（可增行），agent 维护，人工可审。

⑦ 超行数拆分：本文件为薄门面（facade），按职责拆至 gen_common（常量/RULES表）、
gen_text（段落占位）、gen_images（图片占位+预览框）、gen_tables（表格）、
gen_blocks（块抽取+单文件构建）、gen_paths（默认路径）、gen_main（generate 主流程）、
tpl_select（企业模板选择）、gen_diff（内容校验差异）；
对外符号（generate/_clean_tag/FILE_MAP/_extract_blocks 等）全部原样再导出。

依赖：python-docx（本项目运行环境已装，内容契约解析同款）。
"""
from . import ph_preview as phprev           # noqa: F401 图片占位预览框（方案A）
from _shared import core                     # noqa: F401 兼容 gen.core.xxx
from m_feedback import feedback as fb        # noqa: F401

from .gen_common import (                    # noqa: F401
    GenError, GEN_ID, GEN_VERSION, FILE_MAP, FILE_FONT, GLOBAL_PH, ROW_RULES,
    TAG_NOISE, TPL_KEY_MAP, TABLE_ROW_VALUE_PH, PARA_LABEL_RULES, DATE_PH_FILES,
    IMAGE_PH_AFTER_TABLE, IMAGE_PH_AFTER_PARA, SME_SAMPLE, HAVE_DOCX, Document, qn,
)
from .gen_text import *                      # noqa: F401,F403
from .gen_images import *                    # noqa: F401,F403
from .gen_tables import *                    # noqa: F401,F403
from .gen_blocks import *                    # noqa: F401,F403
from .gen_paths import *                     # noqa: F401,F403
from .gen_main import *                      # noqa: F401,F403
