# -*- coding: utf-8 -*-
"""生产环境清理方案 Word 生成脚本（无模板新建）"""
import docx
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

TARGET = r"E:\bidcraft_skill\dev\plans\生产环境清理方案-2026-10-23.docx"

doc = Document()

# ---------- 页面设置：A4，2.5cm 边距 ----------
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.top_margin = sec.bottom_margin = sec.left_margin = sec.right_margin = Cm(2.5)

# ---------- 页脚居中页码（阿拉伯数字） ----------
footer = sec.footer
fp = footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run()
f1 = OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'), 'begin')
it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve'); it.text = 'PAGE'
f2 = OxmlElement('w:fldChar'); f2.set(qn('w:fldCharType'), 'end')
r._r.append(f1); r._r.append(it); r._r.append(f2)
r.font.size = Pt(10.5)

# ---------- 样式 ----------
def set_fonts(style, east, west, size, bold, color=(0, 0, 0)):
    style.font.name = west
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor(*color)
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn('w:rFonts'))
    if rf is None:
        rf = OxmlElement('w:rFonts'); rpr.append(rf)
    rf.set(qn('w:eastAsia'), east)
    rf.set(qn('w:ascii'), west)
    rf.set(qn('w:hAnsi'), west)
    # 移除主题字体选择器，避免显式字体被主题解析值遮蔽
    for attr in ('w:asciiTheme', 'w:eastAsiaTheme', 'w:hAnsiTheme', 'w:cstheme'):
        if rf.get(qn(attr)) is not None:
            del rf.attrib[qn(attr)]

set_fonts(doc.styles['Normal'], '宋体', 'Times New Roman', 12, False)
doc.styles['Normal'].paragraph_format.line_spacing = 1.5
doc.styles['Normal'].paragraph_format.space_before = Pt(0)
doc.styles['Normal'].paragraph_format.space_after = Pt(0)
doc.styles['Normal'].paragraph_format.first_line_indent = Pt(24)  # 2 字符

for name, size in [('Title', 18), ('Heading 1', 16), ('Heading 2', 14), ('Heading 3', 12)]:
    set_fonts(doc.styles[name], '黑体', 'Times New Roman', size, True)
    doc.styles[name].paragraph_format.first_line_indent = Pt(0)
    if name == 'Title':
        doc.styles[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.styles[name].paragraph_format.space_after = Pt(18)
    elif name == 'Heading 1':
        doc.styles[name].paragraph_format.space_before = Pt(14)
        doc.styles[name].paragraph_format.space_after = Pt(6)
    elif name == 'Heading 2':
        doc.styles[name].paragraph_format.space_before = Pt(11)
        doc.styles[name].paragraph_format.space_after = Pt(5)
    else:
        doc.styles[name].paragraph_format.space_before = Pt(9)
        doc.styles[name].paragraph_format.space_after = Pt(4)

# ---------- 工具函数 ----------
def add_para(text, bold=False, style=None, indent=True):
    p = doc.add_paragraph(style=style)
    run = p.add_run(text)
    run.bold = bold
    if not indent:
        p.paragraph_format.first_line_indent = Pt(0)
    return p

def add_bullet(text, bold_prefix=None):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.left_indent = Cm(0.74)
    if bold_prefix:
        r1 = p.add_run(bold_prefix)
        r1.bold = True
    p.add_run(text)
    return p

def add_code(text):
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(6)
    ppr = p._p.get_or_add_pPr()
    shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), 'F2F2F2')
    ppr.append(shd)
    run = p.add_run(text)
    run.font.name = 'Consolas'
    rpr = run._element.get_or_add_rPr()
    rf = OxmlElement('w:rFonts'); rf.set(qn('w:eastAsia'), '宋体')
    rpr.append(rf)
    run.font.size = Pt(10)
    return p

def shade_cell(cell, color):
    tcpr = cell._tc.get_or_add_tcPr()
    old = tcpr.find(qn('w:shd'))
    if old is not None:
        tcpr.remove(old)
    shd = OxmlElement('w:shd'); shd.set(qn('w:val'), 'clear'); shd.set(qn('w:fill'), color)
    # 按 OOXML schema 顺序插入：shd 位于 vAlign 之前
    anchor = tcpr.find(qn('w:vAlign'))
    if anchor is not None:
        anchor.addprevious(shd)
    else:
        tcpr.append(shd)

def set_row_header(row):
    trpr = row._tr.get_or_add_trPr()
    trpr.append(OxmlElement('w:tblHeader'))

def set_row_cantsplit(row):
    trpr = row._tr.get_or_add_trPr()
    trpr.append(OxmlElement('w:cantSplit'))

def make_table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = 'Table Grid'
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    # 固定布局：显式列宽生效，避免空列被自动压缩导致表头竖排
    # 按 OOXML 顺序：tblLayout 应位于 tblLook 之前
    tblpr = t._tbl.tblPr
    layout = OxmlElement('w:tblLayout')
    layout.set(qn('w:type'), 'fixed')
    look = tblpr.find(qn('w:tblLook'))
    if look is not None:
        look.addprevious(layout)
    else:
        tblpr.append(layout)
    hdr = t.rows[0]
    set_row_header(hdr); set_row_cantsplit(hdr)
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(c, 'D9D9D9')
        p = c.paragraphs[0]
        p.paragraph_format.first_line_indent = Pt(0)
        p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(h); r.bold = True
        r.font.size = Pt(10.5)
        r.font.name = 'Times New Roman'
        r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    for row in rows:
        tr = t.add_row()
        set_row_cantsplit(tr)
        for i, v in enumerate(row):
            c = tr.cells[i]
            c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            p = c.paragraphs[0]
            p.paragraph_format.first_line_indent = Pt(0)
            if i == 0:
                p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(v); r.font.size = Pt(10.5)
            r.font.name = 'Times New Roman'
            r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t

def add_caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.first_line_indent = Pt(0)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    r.font.size = Pt(10.5)
    r.font.name = 'Times New Roman'
    r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    return p

def add_toc():
    p = doc.add_paragraph()
    p.paragraph_format.first_line_indent = Pt(0)
    run = p.add_run()
    f1 = OxmlElement('w:fldChar'); f1.set(qn('w:fldCharType'), 'begin')
    it = OxmlElement('w:instrText'); it.set(qn('xml:space'), 'preserve')
    it.text = 'TOC \\o "1-2" \\h \\z \\u'
    f2 = OxmlElement('w:fldChar'); f2.set(qn('w:fldCharType'), 'separate')
    t = OxmlElement('w:t'); t.text = '（目录域：打开文档后按 Ctrl+A 再按 F9 更新）'
    f3 = OxmlElement('w:fldChar'); f3.set(qn('w:fldCharType'), 'end')
    for el in (f1, it, f2, t, f3):
        run._r.append(el)
    return p

# ================= 文档内容 =================

# 封面区：标题 + 文档信息
doc.add_paragraph('bidcraft_skill 生产环境清理方案', style='Title')
p = doc.add_paragraph()
p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.first_line_indent = Pt(0)
r = p.add_run('标书匠 · E:\\标书匠生产 环境净化与升级脚本修复')
r.font.size = Pt(12); r.font.name = 'Times New Roman'
r._element.rPr.rFonts.set(qn('w:eastAsia'), '楷体')
p = doc.add_paragraph()
p.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.first_line_indent = Pt(0)
r = p.add_run('版本基准：GitHub main（当前 prod-sync e959a3a） ｜ 日期：2026-10-23 ｜ 状态：待审阅')
r.font.size = Pt(10.5); r.font.name = 'Times New Roman'
r._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

# 目录（独立起页）
doc.add_paragraph()
h = doc.add_paragraph('目录', style='Heading 1')
h.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
add_toc()
doc.add_page_break()

# ---------- 一、问题诊断摘要 ----------
doc.add_heading('一、问题诊断摘要', level=1)

doc.add_heading('1.1 生产目录设计意图', level=2)
add_para('生产环境说明（E:\\标书匠生产\\生产环境说明.txt）明确：本目录为生产环境，代码 100% 来自 GitHub main 分支，本地不做任何开发/测试；工作区不含任何开发/测试文件。')
add_bullet('原方案为 sparse-checkout 只检出发布文件：scripts/、references/、SKILL.md、README.md、.gitignore、requirements.txt、VERSION。', bold_prefix='设计：')
add_bullet('业务数据在 E:\\监理标书制作（--root 指向），生产目录本身不含企业数据。', bold_prefix='数据：')
add_bullet('升级只走 GitHub main，本地永不手动改代码。', bold_prefix='升级：')

doc.add_heading('1.2 实际污染现状（2026-10-23 核查）', level=2)
add_para('经生产仓库 git ls-files 与磁盘核查，生产目录混入了开发、测试及运维文件，且大部分已被 git 跟踪：')
add_caption('表 1 生产目录污染现状')
make_table(
    ['污染类别', '具体内容', '规模', '被 git 跟踪'],
    [
        ['开发目录 dev/', '开发日志、原型、设计报告、脚本', '179 个文件', '是'],
        ['测试目录 tests/', '单元/集成/e2e 测试与夹具', '53 个文件', '是'],
        ['CI 配置 .github/', 'GitHub Actions 工作流', '—', '是'],
        ['根目录垃圾文件', 'gen2.txt、gen_final.txt、out.txt、out_e2e.txt、push.txt、sme_prod_check.txt、verify_patch.txt、secedit.jfm、secedit.sdb', '9 个文件', '是'],
        ['部署私钥 .deploy/', 'bidcraft_deploy（SSH 私钥）、.pub、known_hosts', '3 个文件', '是'],
        ['运维文件', '升级日志.txt、定时升级.cmd、使用bidcraft_skill.bat、生产环境说明.txt', '4 个文件', '是'],
    ],
    widths=[3.2, 7.2, 2.2, 2.4],
)
add_para('合计：git 跟踪的 dev/tests/.github 相关文件达 192 个；本地 main 分支领先 origin/main 共 7 个 prod-sync 提交（未推送）。', indent=True)

doc.add_heading('1.3 根因分析', level=2)

doc.add_heading('1.3.1 根因一（主因）：升级脚本同步机制绕过隔离设计', level=3)
add_bullet('升级生产.ps1 因网络原因（GitHub SSH/HTTPS 传输受限）改用 api.github.com 下载整仓 zipball 全量快照，快照内含 dev/、tests/、.github/ 全部内容。', bold_prefix='快照全量：')
add_bullet('robocopy /E 全量同步工作区，仅排除 .git、.deploy、scripts/tools/tmp_out 与少数文件，dev/tests/.github 由此进入生产磁盘。', bold_prefix='同步全量：')
add_bullet('同步后执行 git sparse-checkout disable（放弃隔离），再 git add -A 全量入库并提交 prod-sync，开发/测试文件被固化进生产仓库历史。', bold_prefix='入库全量：')

doc.add_heading('1.3.2 根因二（历史遗留）：根目录垃圾文件被收编', level=3)
add_para('gen2.txt、secedit.sdb 等 9 个根目录文件在开发仓库 E:\\bidcraft_skill 中不存在（git ls-files 与磁盘均确认），属生产目录建立初期（2026-10-19 之前）的本地开发产物，在 2026-10-19 19:15 提交 1827390（prod-sync 30bf72cf）时被 git add -A 一并入库。')

doc.add_heading('1.3.3 根因三（安全疏漏）：部署私钥入库', level=3)
add_para('.deploy/bidcraft_deploy（SSH 部署私钥）在 2026-10-19 19:19 提交 dcd741d（全量收敛）时被 git add -A 跟踪。当前生产仓库只拉不推（ahead 7 未推送），私钥未外泄，但入库本身构成泄露风险。')

doc.add_heading('1.4 污染引入提交定位', level=2)
add_caption('表 2 污染文件引入提交')
make_table(
    ['提交', '时间', '引入内容'],
    [
        ['1827390', '10-19 19:15', 'gen2.txt、gen_final.txt、out.txt、out_e2e.txt、push.txt 等根目录垃圾文件'],
        ['80864d1', '10-19 19:18', '补充收敛（prod-sync 30bf72cf）'],
        ['dcd741d', '10-19 19:19', '.deploy/ 私钥、tests/ 等（全量收敛）'],
        ['1019863', '10-19 21:47', '最近一次 prod-sync，dev/ 等随全量同步入库'],
    ],
    widths=[2.4, 2.4, 10.2],
)
add_para('注：dev/ 目录早于生产环境即存在于 GitHub main（上游提交 3ba3e7a 等），因开发仓库本就跟踪并推送该目录；生产侧通过全量同步将其带入。', indent=True)

# ---------- 二、清理目标与边界 ----------
doc.add_heading('二、清理目标与边界', level=1)

doc.add_heading('2.1 目标状态', level=2)
add_caption('表 3 现状与目标对照')
make_table(
    ['项目', '现状', '目标'],
    [
        ['git 跟踪树', '含 dev/tests/.github/垃圾/私钥', '仅含发布文件（scripts、references、SKILL.md、README.md、.gitignore、requirements.txt、VERSION）'],
        ['工作区', '含 dev/tests/.github 及 9 个垃圾文件', '无任何开发/测试文件'],
        ['.deploy 私钥', '被 git 跟踪', '仅存在于磁盘，不跟踪'],
        ['运维文件', '被 git 跟踪', '不跟踪（本地保留）'],
        ['本地分支', '领先 origin 7 个提交', '维持只拉不推，干净可回滚'],
    ],
    widths=[3.0, 5.2, 6.8],
)

doc.add_heading('2.2 清理边界（明确不做）', level=2)
add_bullet('不修改 GitHub main 历史：开发仓库仍保留 dev/tests，属开发侧正常内容，本次只治理生产侧。', bold_prefix='① ')
add_bullet('不清除生产业务数据：E:\\监理标书制作 及企业/项目数据一律不动。', bold_prefix='② ')
add_bullet('不删除 .deploy 私钥：升级通道仍需使用，只移出 git 跟踪、保留磁盘文件。', bold_prefix='③ ')
add_bullet('本次只输出方案，经用户确认后按阶段执行。', bold_prefix='④ ')

# ---------- 三、分阶段清理方案 ----------
doc.add_heading('三、分阶段清理方案', level=1)
add_para('共四个阶段：前置检查与备份 → 修复升级脚本（根治）→ 清理 git 跟踪与磁盘 → 验证回归。每阶段含操作、命令与验收。')

doc.add_heading('3.1 阶段 0：前置检查与备份', level=2)
add_bullet('记录当前 HEAD、确认 git 状态、确认定时任务「Bidcraft生产定时升级」状态。', bold_prefix='动作：')
add_bullet('全量备份生产目录（含 .git）至备份区，确保任何一步可回滚。', bold_prefix='备份：')
add_code('cd /d E:\\标书匠生产\nrem 记录当前版本\ngit rev-parse HEAD\ngit status --porcelain\nrem 全量备份（到备份盘）\nrobocopy E:\\标书匠生产 D:\\backup\\标书匠生产_20261023 /E /COPYALL /DCOPY:T')

doc.add_heading('3.2 阶段 1：修复升级脚本（根治，关键）', level=2)
add_para('修改 E:\\标书匠生产\\升级生产.ps1，将“zipball 全量同步 + git add -A”改为“发布子集白名单同步 + 白名单暂存”，从源头杜绝开发/测试文件进入生产：', indent=True)
add_bullet('zipball 解压后，robocopy 只同步白名单目录/文件：scripts/、references/、SKILL.md、README.md、.gitignore、requirements.txt、VERSION。', bold_prefix='同步白名单：')
add_bullet('删除 git sparse-checkout disable 之后的全量 git add -A，改为按白名单 git add（scripts references SKILL.md README.md .gitignore requirements.txt VERSION）。', bold_prefix='暂存白名单：')
add_bullet('保留原有防污染检查、冒烟（--help + list-enterprises）、版本记录逻辑。', bold_prefix='保留逻辑：')
add_para('同时更新两份 .gitignore（职责分离）：', indent=True)
add_bullet('生产 .gitignore 增加忽略：.deploy/、dev/、tests/、.github/、9 个根目录垃圾文件、升级日志.txt、定时升级.cmd、使用bidcraft_skill.bat、生产环境说明.txt。', bold_prefix='生产侧：')
add_bullet('开发仓库 .gitignore 仅补充根目录垃圾文件与 .deploy/ 忽略；不得忽略 dev/tests（开发侧仍需跟踪）。', bold_prefix='开发侧：')

doc.add_heading('3.3 阶段 2：清理生产 git 跟踪', level=2)
add_para('将污染文件移出版本跟踪（--cached 保留磁盘文件），随后提交 cleanup 提交（本地，不推送）：', indent=True)
add_code('cd /d E:\\标书匠生产\ngit rm -r --cached dev tests .github\ngit rm --cached gen2.txt gen_final.txt out.txt out_e2e.txt push.txt ^\n    sme_prod_check.txt verify_patch.txt secedit.jfm secedit.sdb\ngit rm -r --cached .deploy\ngit rm --cached 升级日志.txt 定时升级.cmd 使用bidcraft_skill.bat 生产环境说明.txt\ngit commit -m "prod-cleanup: 移除开发/测试/私钥/运维文件跟踪（保留磁盘文件）"')

doc.add_heading('3.4 阶段 3：清理工作区磁盘文件', level=2)
add_para('删除工作区中的开发/测试目录与垃圾文件，移入系统回收站（按用户偏好保留 30 天后清理）；.deploy/ 保留：', indent=True)
add_code('rem 逐个移入回收站（以 dev 为例；tests/.github 及 9 个垃圾文件同样处理）\n$dir = "E:\\标书匠生产\\dev"\n$shell = New-Object -ComObject Shell.Application\n$recycle = $shell.Namespace(10)\n$recycle.MoveHere($dir)\nrem 确认 .deploy 私钥仍在\ndir E:\\标书匠生产\\.deploy')

doc.add_heading('3.5 阶段 4：验证与回归', level=2)
add_bullet('git ls-files 顶层仅含发布文件；git status 无已跟踪改动（可容忍 untracked 运维文件）。', bold_prefix='跟踪树：')
add_bullet('python scripts\\bidcraft.py --help 与 --root <临时目录> list-enterprises 均退出码 0。', bold_prefix='冒烟：')
add_bullet('手动运行一次升级生产.ps1，确认新脚本不再引入 dev/tests/.github 且业务文档同步正常。', bold_prefix='升级回归：')
add_bullet('确认定时任务「Bidcraft生产定时升级」可正常触发（下次运行时间与输出）。', bold_prefix='定时任务：')

# ---------- 四、风险与回滚预案 ----------
doc.add_heading('四、风险与回滚预案', level=1)
add_caption('表 4 风险与回滚预案')
make_table(
    ['风险', '说明', '应对措施'],
    [
        ['清理中断', '断电/脚本失败导致半清理状态', '阶段 0 全量备份先行；git reset --hard <cleanup 前 commit> 恢复'],
        ['定时任务冲突', '清理过程中自动升级触发覆盖', '阶段 0 先禁用/错峰；清理完成后恢复计划任务'],
        ['私钥误删', '.deploy 被当作垃圾清理', 'git rm --cached 只移出跟踪；磁盘 .deploy/ 明确保留'],
        ['开发仓库 .gitignore 误改', '忽略 dev/tests 破坏开发侧', '两份 .gitignore 职责分离；开发侧只加垃圾文件忽略'],
        ['升级脚本改坏', '新同步逻辑冒烟失败', '保留旧版 升级生产.ps1 备份；失败即 git reset --hard 回滚'],
    ],
    widths=[3.2, 5.0, 6.8],
)

# ---------- 五、验收清单 ----------
doc.add_heading('五、验收清单', level=1)
add_caption('表 5 验收清单')
make_table(
    ['序号', '检查项', '预期结果', '执行后填写'],
    [
        ['1', 'git ls-files 顶层', '仅 scripts/references/SKILL.md/README.md/.gitignore/requirements.txt/VERSION', ''],
        ['2', 'git status', '无已跟踪改动（可容忍 untracked 运维文件）', ''],
        ['3', '冒烟 --help', '退出码 0', ''],
        ['4', '冒烟 list-enterprises', '退出码 0', ''],
        ['5', '手动升级一次', '工作区仍干净，无 dev/tests/.github 复现', ''],
        ['6', '.deploy 私钥', '仍在磁盘、未被 git 跟踪', ''],
        ['7', '定时任务', '正常运行且日志无异常', ''],
    ],
    widths=[1.2, 4.6, 6.6, 2.6],
)

# ---------- 六、待确认事项 ----------
doc.add_heading('六、待用户确认事项', level=1)
add_caption('表 6 待确认事项')
make_table(
    ['序号', '待确认项', '候选方案'],
    [
        ['1', '是否按本方案执行清理', '执行 / 修改后执行'],
        ['2', '根目录 9 个垃圾文件处理方式', '移入回收站（30 天后清）/ 移入备份目录'],
        ['3', '升级脚本改造方式', '方案 A：白名单同步；方案 B：robocopy 排除法（/XD dev tests .github）'],
        ['4', '执行时间窗口', '避开定时任务（每 6 小时）触发时段'],
        ['5', '执行主体', '本 Agent 执行 / 提供脚本由用户手动执行'],
    ],
    widths=[1.2, 6.4, 7.4],
)

doc.save(TARGET)
print('SAVED:', TARGET)
