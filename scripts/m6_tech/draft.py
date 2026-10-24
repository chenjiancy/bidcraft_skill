# -*- coding: utf-8 -*-
"""
bidcraft · M6 技术标制作 —— T14 自动撰写引擎（tech-draft）

规则拼装骨架草稿生成器（**确定性**；LLM 填充由调用 skill 的 agent 平台在精修链提供）：
  tech-ctx 上下文包（m6.ctx/v1）→ 句式模板库 + 评分点覆盖 + 素材注入 + 暗标口径 + 字数预算
  → 章节/ch-xx.draft.md（头部 M6-DRAFT 标记 + 末尾 M6-COVERAGE 自述块）
  自检同 tech-parse 硬校验（非空/字数≥wordCnt×0.7/无硬占位/暗标敏感词），不通过不落盘（fail fast）

落盘后的衔接（机器草稿 → 精修链）：
  1) 人工直改草稿，或 agent 平台在草稿基础上 LLM 填充润色（输出新 md）
  2) tech-parse --file 章节/ch-xx.draft.md  —— 落盘为正式正文（WRITTEN，闸门纪律不变）
  3) tech-rewrite 精修 → tech-check/tech-report（闸门②） → tech-export

边界：本引擎不做语义判断（不编造事实/条文号/人名）；素材缺失处只写 {{待填:说明}}。
暗标口径：不注入企业名/人名/业绩名称（业绩匿名描述），避免命中敏感词。
"""
import json
import re
from pathlib import Path

from _shared import core

from . import store
from . import sources
from . import rules
from . import writer

DRAFT_MARK = "M6-DRAFT"
DRAFT_SCHEMA = "m6.draft/v1"
# 目标段落字数（草稿按预算补足到 wordCnt 的 0.85~1.05；parse 下限为 0.7）
PARA_CHARS = 200
FLOOR_RATIO = 0.7
TARGET_RATIO = 0.9


# ---------------------------------------------------------------------------
# 句式模板库：keyPoints 关键词 → 小节（### 标题 + 段落模板 + 扩展点）
# 模板主语一律"监理单位"（暗标明标通用）；措施写清 谁做/怎么做/频次/工具/标准，
# 拒绝"高度重视、全面落实"空话（对齐 P3 写作要求 3）。
# ---------------------------------------------------------------------------
def _para(*segs):
    """段落模板：segs 为句段列表，拼接成一段（句间用换行，正文按段落渲染）。"""
    return "\n".join(segs)


_SECTIONS = [
    {
        "keys": ("工程概况", "项目概况", "项目背景", "工程背景", "工程概述"),
        "title": "工程概况与监理工作理解",
        "paras": [
            _para(
                "监理单位对工程的基本情况进行梳理，明确本工程的建设规模、主要功能及建设条件，"
                "形成对工程特点、难点及管理重点的总体认识。",
                "针对{term}的具体情况，监理单位将结合勘察设计文件、招标文件及现行建设工程监理规范，"
                "对工程的施工环境、技术特点与管理要求进行逐项分析，为制定监理工作方案奠定基础。",
                "本章节涉及的关键内容与招标评审要点相符，监理单位将在后续章节中逐项落实具体措施。",
            ),
            _para(
                "监理单位建立以总监理工程师为核心、专业监理工程师为骨干的项目监理机构，"
                "按照岗位职责明确分工，确保各项工作责任到人、落实到岗。",
                "项目监理机构将依据监理规划和监理实施细则开展工作，"
                "采用巡视、旁站、平行检验相结合的方式实施过程控制。",
            ),
        ],
        "extend": [
            _para("对工程特点的分析结论，监理单位将组织专题会确认，并形成书面记录留存项目监理机构。"),
            _para("对可能影响工程质量、安全、进度的关键环节，监理单位将提前识别并纳入重点控制清单。"),
        ],
    },
    {
        "keys": ("监理范围", "工作范围", "服务范围", "监理服务范围"),
        "title": "监理工作范围",
        "paras": [
            _para(
                "监理单位承担本工程的施工阶段监理任务，监理工作范围覆盖{term}施工全过程，"
                "包括质量控制、进度控制、造价控制、安全生产管理的监理工作、"
                "合同管理、信息管理以及组织协调等各项监理工作内容。",
                "监理单位将依据建设工程监理合同和招标文件约定，全面履行监理职责，"
                "对施工承包单位的质量、进度、造价行为实施监督与协调。",
            ),
            _para(
                "监理范围的具体界定以招标文件、监理合同及经批准的监理规划为准，"
                "对超出约定范围的委托事项，监理单位将按程序提出处理建议并报建设单位确认。",
            ),
        ],
        "extend": [
            _para("对监理范围边界不清或交叉的事项，监理单位将组织专题分析并向建设单位书面报告。"),
        ],
    },
    {
        "keys": ("监理目标", "工作目标", "监理工作目标"),
        "title": "监理工作目标",
        "paras": [
            _para(
                "监理单位将围绕质量、进度、造价、安全四个方面设置监理工作目标："
                "质量控制目标为实现合同约定的质量标准；进度控制目标为满足合同工期要求；"
                "造价控制目标为将工程投资控制在批准概算及合同价款范围内；"
                "安全目标为落实安全生产管理的监理责任，防止发生生产安全事故。",
                "监理单位将把上述目标分解到各分部分项工程和各个监理岗位，"
                "通过过程控制确保总体目标的实现。",
            ),
        ],
        "extend": [
            _para("目标实现情况将在监理月报中逐项统计，偏离目标时提出纠偏措施并跟踪闭环。"),
        ],
    },
    {
        "keys": ("监理组织机构", "监理机构", "组织机构", "人员配备", "人员配置", "监理组织"),
        "title": "监理组织机构与人员配备",
        "paras": [
            _para(
                "监理单位根据{term}的规模和专业特点组建项目监理机构，"
                "机构设置总监理工程师、专业监理工程师和监理员，"
                "各岗位人员职责明确、持证上岗。",
                "项目监理机构实行总监理工程师负责制，总监理工程师对项目监理工作负总责，"
                "专业监理工程师按专业分工实施日常监理工作。",
            ),
        ],
        "extend": [
            _para("监理机构将根据工程进展动态调整人员配置，关键岗位缺员时及时补充并报建设单位备案。"),
            _para("监理人员将按计划参加业务培训，保持专业能力与工程需要相适应。"),
        ],
    },
    {
        "keys": ("质量控制", "质量保证", "质量管理", "质量体系", "工程质量"),
        "title": "质量控制措施",
        "paras": [
            _para(
                "监理单位建立覆盖事前、事中、事后全过程的质量控制体系："
                "事前审核施工组织设计、技术方案与分包资质；"
                "事中通过巡视、旁站、平行检验实施过程控制；"
                "事后对检验批、分项、分部工程进行验收把关。",
                "监理单位将依据现行建设工程监理规范及验收标准开展工作，"
                "对关键工序、关键部位实行旁站监理，并做好旁站记录。",
                "对发现的质量问题，监理单位将及时签发监理通知单，跟踪整改并复查闭环。",
            ),
            _para(
                "监理单位将组织编制监理实施细则，明确各分部工程的监理要点和控制措施，"
                "作为现场监理人员开展工作的依据。",
            ),
        ],
        "extend": [
            _para("对主要材料、构配件和设备，监理单位将按规定进行进场检验和见证取样，不合格品不得使用。"),
            _para("监理单位将定期组织质量专题会，分析质量趋势并布置预防措施。"),
        ],
    },
    {
        "keys": ("进度控制", "工期控制", "进度管理"),
        "title": "进度控制措施",
        "paras": [
            _para(
                "监理单位对施工进度实施动态控制：审核施工总进度计划和年度、月度进度计划，"
                "跟踪实际进度并与计划对比，分析偏差原因，督促施工承包单位采取纠偏措施。",
                "监理单位将通过进度专题会、监理月报等形式定期向建设单位报告进度情况，"
                "对影响工期的关键线路重点监控。",
            ),
        ],
        "extend": [
            _para("当实际进度滞后于计划时，监理单位将要求施工承包单位提交赶工措施并跟踪落实效果。"),
        ],
    },
    {
        "keys": ("造价控制", "投资控制", "费用控制", "成本控制"),
        "title": "造价控制措施",
        "paras": [
            _para(
                "监理单位依据合同约定实施造价控制：审核工程量清单与计量支付申请，"
                "对工程变更进行技术经济分析，控制索赔与反索赔事项，"
                "确保工程投资控制在批准范围内。",
                "监理单位将建立计量支付台账，对已完工程量和支付金额进行核对，"
                "防止超计量、超支付。",
            ),
        ],
        "extend": [
            _para("对重大变更和签证事项，监理单位将进行专项造价分析并报建设单位决策。"),
        ],
    },
    {
        "keys": ("安全管理", "安全生产", "安全文明", "安全监理", "文明施工"),
        "title": "安全生产管理的监理工作",
        "paras": [
            _para(
                "监理单位将安全生产管理纳入监理工作范围：审查施工组织设计中的安全技术措施"
                "和专项施工方案是否符合工程建设强制性标准，"
                "对危大工程实施专项巡视检查，发现安全事故隐患时及时要求整改。",
                "监理单位按规定对施工安全生产情况进行巡视检查，"
                "发现存在安全事故隐患的，将签发监理通知单要求限期整改；"
                "情况严重时立即报告建设单位并按合同约定处理。",
            ),
        ],
        "extend": [
            _para("监理单位将建立安全监理台账，记录巡视检查、隐患整改及复查闭环情况。"),
        ],
    },
    {
        "keys": ("合同管理", "合同信息", "信息管理"),
        "title": "合同管理与信息管理",
        "paras": [
            _para(
                "监理单位对施工合同实施动态管理：跟踪合同执行情况，"
                "对合同变更、索赔事项进行程序化处理，妥善处理合同争议。",
                "监理单位建立信息管理制度，对工程往来文件、会议纪要、监理日志、"
                "监理月报等资料进行规范收集、整理与归档，保证信息传递及时、准确、可追溯。",
            ),
        ],
        "extend": [
            _para("对重要函件和变更指令，监理单位将按程序签认并存档备查。"),
        ],
    },
    {
        "keys": ("组织协调", "协调", "各方协调"),
        "title": "组织协调",
        "paras": [
            _para(
                "监理单位承担工程建设相关方之间的组织协调工作："
                "定期组织召开工地例会和专题协调会，协调解决施工过程中"
                "影响质量、进度、安全的配合问题。",
                "监理单位将建立协调事项台账，对未决事项跟踪督办，"
                "重大协调事项及时向建设单位报告。",
            ),
        ],
        "extend": [
            _para("对交叉作业和界面衔接事项，监理单位将提前组织各方协商明确责任界面。"),
        ],
    },
    {
        "keys": ("巡视", "旁站", "平行检验", "监理方法", "工作方法"),
        "title": "监理工作方法与程序",
        "paras": [
            _para(
                "监理单位综合运用巡视、旁站、平行检验等监理方法实施过程控制："
                "对施工现场进行定期巡视检查；对关键部位、关键工序实施旁站监理；"
                "对材料、构配件和工程实体按规定进行平行检验。",
                "各项监理工作均按监理规划、监理实施细则规定的程序执行，"
                "发现的问题按发现、报告、处置、复查的程序闭环处理。",
            ),
        ],
        "extend": [
            _para("监理日志将如实记录当日监理工作情况，作为过程控制的原始依据。"),
        ],
    },
    {
        "keys": ("检测试验", "试验", "检测"),
        "title": "检测与试验控制",
        "paras": [
            _para(
                "监理单位对涉及结构安全的试块、试件及材料实行见证取样和送检制度，"
                "见证人员按规定履行见证职责，确保检测数据真实、有效。",
                "监理单位将审核检测机构资质和检测方案，"
                "对检测不合格的项目按程序处理并跟踪处置结果。",
            ),
        ],
        "extend": [
            _para("监理单位将建立见证取样台账，与检测报告对应核验，防止漏检、错检。"),
        ],
    },
    {
        "keys": ("会议制度", "工地例会", "监理会议"),
        "title": "工地会议制度",
        "paras": [
            _para(
                "监理单位建立工地会议制度：定期召开工地例会，"
                "检查上次会议事项落实情况，分析工程质量、进度、安全状况，"
                "明确下一步工作安排并形成会议纪要。",
                "对重要事项组织专题会议研究，会议纪要经与会各方确认后分发执行。",
            ),
        ],
        "extend": [
            _para("会议决定事项将纳入跟踪清单，在下次会议上逐项核对落实情况。"),
        ],
    },
    {
        "keys": ("资料管理", "档案", "资料归档"),
        "title": "监理资料管理",
        "paras": [
            _para(
                "监理单位按现行规范建立监理资料管理制度："
                "对监理规划、监理实施细则、监理日志、监理月报、"
                "会议纪要、通知单、旁站记录等资料及时收集、分类、归档。",
                "资料管理做到真实、完整、及时、可追溯，"
                "工程竣工时按规定向建设单位移交监理档案。",
            ),
        ],
        "extend": [
            _para("监理资料将同步建立电子与纸质台账，便于检索与核验。"),
        ],
    },
    {
        "keys": ("售后服务", "保修", "保修期"),
        "title": "保修期监理服务",
        "paras": [
            _para(
                "在工程保修期内，监理单位将配合建设单位开展保修期管理："
                "对保修范围内的质量缺陷组织核查，督促施工承包单位及时整改，"
                "并对整改结果进行复查确认。",
            ),
        ],
        "extend": [
            _para("保修期结束前，监理单位将协助建设单位组织保修期满验收并办理移交手续。"),
        ],
    },
]

# 通用兜底模板（未命中任何关键词）
_GENERIC_TITLE = "本章监理工作要点"
_GENERIC_PARAS = [
    _para(
        "本章围绕{term}的监理工作要点展开。监理单位将依据招标文件、"
        "现行建设工程监理规范及经批准的监理规划，结合本工程实际情况，"
        "制定针对性措施并落实到项目监理机构各岗位。",
        "对本章涉及的评审要点，监理单位将逐项明确责任岗位、工作频次、"
        "实施工具与验收标准，确保措施可落地、可检查、可考核。",
    ),
    _para(
        "监理单位将把本章工作内容纳入监理月报和检查计划，"
        "对措施执行情况定期核查，并根据工程实际动态调整。",
    ),
]

# 通用扩展句池（字数补足用，每条只追加一次，避免重复）
_GENERIC_EXTS = [
    _para("本节监理措施的落实情况由专业监理工程师在监理日志中记录，并纳入监理月报汇总分析。"),
    _para("对实施过程中出现的偏差，监理单位将组织原因分析并调整控制措施，确保工作目标达成。"),
    _para("监理单位将把本节工作内容纳入人员培训和岗位考核，提升执行质量。"),
    _para("涉及需建设单位决策的事项，监理单位将及时提交书面报告并跟踪决策结果。"),
    _para("对相关分包单位的管理，监理单位将按合同和规范要求实施监督，防止以包代管。"),
    _para("监理单位将定期听取建设单位意见，持续改进监理工作质量。"),
]

# 通用监理措施展开段（无素材注入时优先使用：每段独立成篇、不重复，支撑篇幅下限）
_GENERIC_EXPANDS = [
    _para("质量控制方面，监理单位将以施工承包合同和现行验收规范为依据，建立事前审核、事中控制、"
          "事后验收的全过程控制体系。事前重点审核施工组织设计、专项施工方案及分包单位资质，"
          "从源头控制施工准备质量；事中通过巡视检查、旁站监理和平行检验掌握施工过程质量状态，"
          "对关键工序、关键部位实施重点监控并留存记录；事后组织检验批、分项、分部工程验收，"
          "对发现的质量问题签发监理通知单并跟踪整改复查，实现质量问题的闭环管理。"),
    _para("进度控制方面，监理单位将依据合同约定的工期目标审核承包单位提交的施工总进度计划和"
          "阶段性进度计划，并分解为月、周作业计划进行动态跟踪。监理人员定期对比实际进度与计划进度，"
          "分析偏差原因，督促承包单位采取资源调配、工序调整等措施纠偏；对关键线路上的延误及时预警，"
          "协调各专业施工穿插衔接，定期向建设单位报告进度状况，确保工期目标总体受控。"),
    _para("造价控制方面，监理单位将按照合同约定的计量与支付程序，审核承包单位报送的工程量清单与"
          "支付申请，做到计量准确、支付有据。对工程变更、签证和索赔事项，监理单位将按程序及时审核，"
          "核实工程量与计价依据，防止虚报冒算；同时做好造价控制的资料归集，为竣工结算审核提供依据，"
          "维护建设单位和承包单位的合法权益。"),
    _para("安全生产管理方面，监理单位将依据法律法规和合同约定履行安全监理职责，审查施工组织设计中"
          "的安全技术措施和专项施工方案，监督承包单位落实安全生产责任制。监理人员对危险性较大的分部分项"
          "工程实施专项巡查，检查现场安全防护、临时用电、机械设备使用及特种作业人员持证情况，"
          "发现安全隐患及时签发监理通知单责令整改，并跟踪验证整改结果，实现安全问题的闭环管理。"),
    _para("合同与信息管理方面，监理单位将按合同约定管理工程往来文件，建立文件收发登记和归档制度，"
          "对合同执行中的争议事项及时提出处理建议。监理单位将规范监理日志、监理月报、旁站记录等"
          "过程资料的填写与归档，保证工程档案的完整性、真实性和可追溯性，为工程验收和结算提供依据。"),
    _para("组织协调方面，监理单位将牵头组织工地例会和各专题协调会，协调参建各方在质量、进度、造价、"
          "安全方面的关系，及时化解施工中的界面交叉与责任争议。对需要建设单位决策的事项，监理单位将"
          "及时书面报告并跟踪落实；对设计变更、材料代用等事项，按程序组织审核确认，确保各方工作有序衔接。"),
]

# 措施落实明细行库（字数补足：生成「监理措施落实表」，每行=谁做/怎么做/频次/工具/标准）
_MEASURE_ROWS = [
    ("审查施工组织设计与专项方案", "专业监理工程师", "每标段开工前", "审查记录表", "通过后开工"),
    ("巡视检查施工现场", "监理员", "每日不少于1次", "巡视记录", "问题闭环"),
    ("关键工序旁站监理", "专业监理工程师", "按实施细则", "旁站记录", "记录完整"),
    ("平行检验材料与工程实体", "试验监理人员", "按规定频次", "平行检验记录", "数据合格"),
    ("见证取样与送检", "见证人员", "按检验批", "见证台账", "检测合格"),
    ("审核计量与支付申请", "造价监理工程师", "每月", "计量支付台账", "不超计量"),
    ("跟踪实际进度与计划对比", "进度监理工程师", "每周", "进度对比表", "偏差可控"),
    ("检查安全技术措施落实", "安全监理人员", "每日", "安全检查记录", "隐患整改闭环"),
    ("签发监理通知单", "专业监理工程师", "发现问题时", "监理通知单", "限期整改"),
    ("组织工地例会", "总监理工程师", "每周1次", "会议纪要", "决议落实"),
    ("审核工程变更", "总监理工程师", "收到即审", "变更审核表", "程序合规"),
    ("处理索赔与反索赔事项", "造价监理工程师", "收到即审", "索赔台账", "依据充分"),
    ("管理工程往来文件", "资料员", "即时", "文件收发登记", "归档完整"),
    ("核查分包单位资质", "专业监理工程师", "进场前", "资质核查表", "符合要求"),
    ("检查特种作业人员持证上岗", "安全监理人员", "进场时", "持证台账", "人证相符"),
    ("组织分部工程验收", "总监理工程师", "按验收计划", "验收记录", "复验合格"),
    ("跟踪整改复查闭环", "专业监理工程师", "整改期满", "复查记录", "复查合格"),
    ("编制监理月报", "信息管理员", "每月", "监理月报", "报建设单位"),
    ("检查季节性施工措施", "专业监理工程师", "季节前", "专项检查表", "预案落实"),
    ("开展岗前培训与交底", "总监理工程师", "新工序前", "交底记录", "全员知晓"),
]


def _measures_table(used, table_no):
    """生成一张「监理措施落实表」（6 行，按表号轮转取不同措施行）。"""
    start = (table_no * 5) % len(_MEASURE_ROWS)
    rows = [_MEASURE_ROWS[(start + i) % len(_MEASURE_ROWS)] for i in range(6)]
    lines = ["### 监理措施落实表", "| 序号 | 措施 | 责任岗位 | 频次 | 工具/表单 | 达到标准 |",
             "|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append("| %d | %s | %s | %s | %s | %s |" % (i, r[0], r[1], r[2], r[3], r[4]))
    return "\n".join(lines)


def _clean_kp(kp):
    """要点文本清洗：去掉评分项编号前缀与多余空白。"""
    return re.sub(r"^\s*[（(]?\d+(\.\d+)*[)）]?\s*", "", str(kp or "")).strip()


def match_templates(keypoints):
    """按要点关键词匹配句式模板小节（未命中用通用模板）。"""
    used = []
    remain = []
    for kp in keypoints:
        text = _clean_kp(kp)
        if not text:
            continue
        hit = None
        for sec in _SECTIONS:
            if any(k in text for k in sec["keys"]):
                hit = sec
                break
        if hit:
            used.append((text, hit))
        else:
            remain.append(text)
    if not used and remain:
        used.append((remain[0], {
            "title": _GENERIC_TITLE, "paras": _GENERIC_PARAS, "extend": []}))
    return used, remain


def _fact_lines(materials, bid_mode):
    """素材事实摘要（注入正文）；暗标口径：业绩匿名、不出现企业名/人名。"""
    lines = []
    for m in materials or []:
        cat = m.get("category") or ""
        facts = m.get("facts") or {}
        if cat == "project_overview" and facts:
            joined = "；".join("%s：%s" % (k, v) for k, v in facts.items()
                               if k not in ("项目名称",) and str(v).strip())
            if joined:
                lines.append(joined)
        elif cat == "performance":
            items = facts.get("items") or []
            if items:
                if bid_mode == "暗标":
                    lines.append("本监理单位具有同类工程的监理业绩，具体业绩资料按暗标要求不作署名披露。")
                else:
                    names = "；".join(str(it.get("名称", "")) for it in items if it.get("名称"))
                    if names:
                        lines.append("本监理单位承担过的同类工程业绩包括：【素材:业绩】" + names)
        elif cat == "enterprise_profile":
            if isinstance(facts, dict):
                base = facts.get("企业基础信息") if isinstance(facts.get("企业基础信息"), dict) else facts
                parts = []
                for k in ("注册资金", "资质等级", "主营范围", "成立时间"):
                    v = base.get(k) if isinstance(base, dict) else None
                    if v:
                        parts.append("%s%s" % (k, v))
                if parts:
                    lines.append("；".join(parts))
        elif cat == "regulation":
            lines.append("依据现行建设工程监理规范开展监理工作（知识库未接入，不引用具体条文编号）。")
    return lines


def _personnel_rows(personnel, bid_mode):
    """人员表数据：明标=姓名+岗位；暗标=只岗位（post-only）。"""
    rows = []
    for p in personnel or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        post = str(p.get("post") or p.get("岗位") or "").strip()
        if bid_mode == "暗标":
            rows.append([post or "监理人员", "岗位职责另行明确"])
        else:
            rows.append([name, post or "监理人员"])
    return rows


def _build_md(pack, bid_mode):
    """按上下文包组装章节草稿 markdown（不含一级标题；末尾 M6-COVERAGE 自述块）。"""
    ch = pack.get("chapter") or {}
    no = ch.get("no") or ""
    title = ch.get("title") or ""
    word_cnt = int(ch.get("wordCnt") or 0)
    keypoints = list(ch.get("keyPoints") or [])
    score_items = pack.get("scoreItems") or []
    terminology = dict(pack.get("terminology") or {})
    materials = pack.get("materials") or []
    personnel = list(pack.get("personnel") or [])
    term = terminology.get("项目名称") or terminology.get("工程名称") or terminology.get("招标人") or "本工程"

    used, remain = match_templates(keypoints)
    facts = _fact_lines(materials, bid_mode)

    head = []
    if no:
        head.append("<!-- %s %s · %s %s 章节草稿：规则拼装生成，未经人工精修 -->"
                    % (DRAFT_MARK, DRAFT_SCHEMA, no, title))
    if facts:
        head.append("**本章依据的工程事实：**")
        for f in facts:
            head.append("- %s" % f)
        head.append("")

    out = list(head)
    covered = []
    missing = []
    for text, sec in used:
        out.append("### %s" % sec["title"])
        for para in sec["paras"]:
            out.append(para.replace("{term}", term))
        covered.append({"point": text, "covered": True, "where": sec["title"]})
    for text in remain:
        out.append("### %s" % text)
        out.append(_GENERIC_PARAS[0].replace("{term}", term))
        covered.append({"point": text, "covered": True, "where": "本章要点"})

    # 人员配置表（personnel 依赖注入时）
    if personnel:
        rows = _personnel_rows(personnel, bid_mode)
        if rows:
            out.append("### 项目监理机构人员配置表")
            if bid_mode == "暗标":
                out.append("| 岗位 | 职责 |")
                out.append("|---|---|")
                for r in rows:
                    out.append("| %s | %s |" % (r[0], r[1]))
            else:
                out.append("| 姓名 | 岗位 |")
                out.append("|---|---|")
                for r in rows:
                    out.append("| %s | %s |" % (r[0], r[1]))
            covered.append({"point": "人员配置", "covered": True, "where": "人员配置表"})

    # 缺料披露：要点无法从素材支撑的项（评分项 evidence 空且无事实）→ {{待填:}}
    if not facts:
        missing.append("工程事实素材（项目概况/企业信息）未注入，涉及具体数据处待人工补齐")
    for si in score_items:
        if not (si.get("evidence") or "").strip() and not facts:
            missing.append("评分项「%s」未取得原文证据，正文仅作通用展开" % (si.get("item") or ""))

    # 字数补足：正文未达 0.9×wordCnt 时，先追加 节扩展句 + 通用扩展池（每条一次），
    # 仍不足则追加「监理措施落实表」（每表 6 行，按表号轮转取行，至多 4 表）
    # 统计口径与 tech-parse 一致：body_chars + table_chars
    def _total(s):
        c = rules.count_chars(s)
        return c["body_chars"] + c["table_chars"]

    body = "\n\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    total = _total(body)
    target = int(word_cnt * TARGET_RATIO)
    ext_pool = []
    for _t, sec in used:
        ext_pool.extend(sec["extend"])
    ext_pool.extend(_GENERIC_EXPANDS)      # 完整展开段优先（内容充实、独立成篇）
    ext_pool.extend(_GENERIC_EXTS)         # 短句池兜底
    used_i = 0
    table_no = 0
    while total < target and (used_i < len(ext_pool) or table_no < 6):
        if used_i < len(ext_pool):
            body += "\n\n" + ext_pool[used_i].replace("{term}", term)
            used_i += 1
        else:
            body += "\n\n" + _measures_table(used, table_no)
            table_no += 1
        total = _total(body)

    # 自述覆盖块
    cov = {"keyPoints": covered,
           "missingMaterials": missing,
           "notes": "机器草稿：由 tech-draft 规则拼装生成（%s），须经人工审阅或 agent 平台 LLM 精修后落盘"
                    % DRAFT_SCHEMA}
    md = body + "\n\n<!-- M6-COVERAGE\n%s\n-->\n" % json.dumps(cov, ensure_ascii=False)
    return md, total


def _validate_draft(md, ch, vocab, bid_mode):
    """自检同 tech-parse 硬校验；返回 (problems, warnings)。不通过则调用方不落盘。"""
    info, self_err = rules.parse_selfcheck_block(md)
    body = rules.strip_selfcheck_block(md)
    problems, warnings = [], []
    if self_err:
        problems.append(("SELFCHECK", self_err))
    if not body.strip():
        problems.append(("EMPTY", "正文为空（剥离自述块后无内容）"))
    counts = rules.count_chars(body)
    total = counts["body_chars"] + counts["table_chars"]
    need = int((ch.get("wordCnt") or 0) * FLOOR_RATIO)
    if total < need:
        problems.append(("WORDCNT", "正文 %d 字 < 预算 %d×0.7=%d 字（篇幅不足）"
                         % (total, ch.get("wordCnt") or 0, need)))
    hard_ph = [h for h in rules.scan_placeholders(body)
               if h.get("type") in writer.HARD_PLACEHOLDER_TYPES]
    if hard_ph:
        problems.append(("PLACEHOLDER", "存在未替换模板占位：%s"
                         % "；".join("%s@L%s" % (h.get("text", ""), h.get("line"))
                                     for h in hard_ph)))
    soft_ph = [h for h in rules.scan_placeholders(body) if h.get("type") == "待填"]
    if soft_ph:
        warnings.append("缺料披露 {{待填}} %d 处（允许，须在 tech-check 裁决）" % len(soft_ph))
    sens = rules.scan_sensitive(body, vocab, bid_mode)
    if sens:
        problems.append(("SENSITIVE", "暗标敏感词命中 %d 处：%s"
                         % (len(sens), "；".join("%s@L%s" % (h["text"], h["line"])
                                                 for h in sens[:5]))))
    return problems, warnings


def cmd_tech_draft(args):
    """生成机器草稿：章节/ch-xx.draft.md（自检通过才落盘，fail fast）。"""
    ent = sources.get_ent(args)
    proj = sources.proj_dir(ent, args.project)
    tech = sources.tech_dir(ent, args.project)
    tree = store.read_tree(tech)
    if not store.outline_confirmed(tree):
        raise core.LibraryError("闸门①未确认：章节树需先 tech-outline --confirm，禁止 tech-draft")
    if getattr(args, "all", False):
        chapters = store.list_chapters(tree)
    elif args.chapter:
        chapters = [store.find_chapter(tree, args.chapter)]
    else:
        raise core.LibraryError("请指定 --chapter ch-01 或 --all")

    tdir = sources.tdir(args, proj)
    points = sources.load_points(tdir, args.project)
    raw_items = sources.scoring_items(points)
    material = sources.load_material(tdir, args.project) or {}
    vocab = writer._vocab(ent, tree)
    bid_mode = tree.get("bidMode") or "明标"

    rows, skipped = [], []
    for ch in chapters:
        cid = ch.get("id")
        cur = ch.get("status") or "PENDING"
        if cur in ("WRITTEN", "CONFIRMED"):
            skipped.append({"id": cid, "reason": "已有正文（%s），请走 tech-rewrite 精修" % cur})
            continue
        pack = store.read_context_pack(tech, cid)      # 缺 .meta 直接报错（须先 tech-ctx）
        from .ctxpack import fill_score_items
        pack = fill_score_items(pack, raw_items)
        md, total = _build_md(pack, bid_mode)
        problems, warnings = _validate_draft(md, ch, vocab, bid_mode)
        if problems:
            detail = "\n".join("[%s] %s" % p for p in problems)
            raise core.LibraryError("章节 %s 草稿自检失败，未落盘：\n%s" % (cid, detail))
        dst = tech / "章节" / ("%s.draft.md" % cid)
        if dst.is_file():
            store.backup_rewrite(tech, dst)
        store.write_text_inside(tech, "章节/%s.draft.md" % cid, md)
        back = store._read_text(tech / "章节" / ("%s.draft.md" % cid))
        if back != md:
            raise core.LibraryError("章节 %s 草稿回读不一致，未落盘" % cid)
        rows.append({"id": cid, "status": cur, "chars": total,
                     "wordCnt": ch.get("wordCnt"),
                     "draft": "章节/%s.draft.md" % cid,
                     "missing": len([w for w in warnings if "{{待填}}" in w or "未注入" in w or "未取得" in w])})
        if getattr(args, "json", False):
            if warnings:
                rows[-1]["warnings"] = warnings
        else:
            for w in warnings:
                print("  ⚠ %s：%s" % (cid, w))

    if getattr(args, "json", False):
        import sys as _sys
        json.dump({"project": args.project, "chapters": rows, "skipped": skipped},
                  _sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        for r in rows:
            print("%s 机器草稿已生成（%d 字 / 预算 %s 字）→ 章节/%s.draft.md"
                  % (r["id"], r["chars"], r["wordCnt"], r["id"]))
        for s in skipped:
            print("  ⚠ %s 跳过：%s" % (s["id"], s["reason"]))
        print("下一步：人工直改草稿或 agent 平台 LLM 精修 → tech-parse --file 章节/ch-xx.draft.md 落盘"
              " → tech-rewrite 精修 → tech-check/tech-report → tech-export")
    return 0


def add_sub(sub):
    sp = sub.add_parser("tech-draft", help="M6·T14 自动撰写引擎：规则拼装骨架草稿（句式模板+评分点覆盖+素材注入+暗标口径+字数预算，自检通过才落盘）；LLM 填充由 agent 平台在精修链提供")
    sp.add_argument("--project", required=True, help="项目名（项目级/<项目>）")
    sp.add_argument("--tdir", default="", help="招标解析目录（默认 项目级/<项目>/招标解析）")
    sp.add_argument("--chapter", default="", help="单章 id（如 ch-01）")
    sp.add_argument("--all", action="store_true", help="全部章节（跳过已有正文 WRITTEN/CONFIRMED 章）")
    sp.set_defaults(func=cmd_tech_draft)
    return sp
