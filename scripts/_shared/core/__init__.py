# -*- coding: utf-8 -*-
"""
bidcraft · M1 素材库 —— 存储层（企业目录 / 台账 / 收件箱批次 / 回收站 / 巡检 / 检索）

职责边界
--------
- 只做确定性的文件系统操作与数据读写，不做「看懂内容」的判断。
- 「图片/PDF 正文里写的是哪家企业」「这几页是不是同一份证书」这类语义判断，
  由 agent（多模态）完成，然后把结论作为参数传进来执行。

⑦ 超行数拆分：本包为薄门面（facade），按职责拆至
  basic（常量/工具/LibraryError）· lib（Library 多企业容器）· ledger（台账单源）
  · trash（回收站）· inbox（收件箱/归属校验/propose/apply）· ops（巡检/检索/概览）；
  对外符号（Library/Inbox/propose/apply/query 等）全部原样再导出。
"""
from .basic import *          # noqa: F401,F403
from .lib import *            # noqa: F401,F403
from .ledger import *         # noqa: F401,F403
from .batch import *          # noqa: F401,F403
from .trash import *          # noqa: F401,F403
from .inbox import *          # noqa: F401,F403
from .ops import *            # noqa: F401,F403
