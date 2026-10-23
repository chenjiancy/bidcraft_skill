# UI 真实流程对齐分析：项目功能实现原理 → 软件 UI 映射

> 原则（用户 2026-10-23 确立）：UI 不是自造逻辑，而是本项目功能实现原理与流程在界面上的体现。做任何 UI 功能前，先读项目实现，再画界面。
> 依据：scripts/ 模块源码（m0_env ~ m10_remedy + m_feedback + _shared）、references/ 契约与需求对齐、共享资源/技术标风格。

## 1. 模块化管道（bidcraft 总纲）

```
M0 环境 → M1 素材库 → M2 模板库 → M4 招标解析 → M5 项目模板 → M6 技术标
        → M7 标书检查 → M8 模拟评标 → M9/M10 补救 → m_feedback 产物反馈
（_shared/core：ledger 台账 / batch 批量 / trash 回收站 / inbox 收件箱 / propose-apply 保护 / readback 回读）
```

## 2. 各模块真实流程（UI 必须体现的）

### M4 招标解析（双通道 + 闸门①）
- 通道A：`文档解析.json`（确定性解析，pdf_extract）
- 通道B：`投标要点.json`（agent 语义，rule_extract）
- `双通道差异.json` → 人工裁决（以招标原文为准）
- 闸门①：`投标要点_<项目>.html` 人工核对后，才进入下游

### M6 技术标（状态机 + 双闸门）
- 命令：tech-init（建骨架+校验 M4 产物+抽取页数/暗标）→ tech-outline（章节树草案校验→回填系统字段→覆盖矩阵→落盘，闸门① 未覆盖/页数超限拒绝）→ tech-ctx（逐章上下文包 m6.ctx/v1）→ tech-parse（正文校验：非空/字数/占位/敏感词→WRITTEN）→ tech-check（通道A 六项：覆盖/结构/篇幅/敏感词/一致性/占位）→ tech-report（闸门② HTML 报告；--confirm 记 confirmLog）→ tech-status（状态表）→ tech-layout（排版预设；--preview 依赖 T10 导出引擎）
- 状态机 STATUSES：PENDING → CONTEXT_READY → WRITING → WRITTEN → CHECKED → CONFIRMED / FAILED（迁移表 + 重来路径）
- 暗标判定：tech-init 按「投标要点文本含『暗标』」自动判定；--bid-mode 手动覆盖
- 章节 id：ch-01 … ch-10；状态文件 m6.state/v1 与章节树 status 同步

### M7 标书检查（双通道）
- 通道A：机器检查（确定性规则 check-rule）
- 通道B：agent 语义审查（check-parse，按提示词 schema）
- check-diff 双通道差异比对 → 人工裁决；check-report HTML
- 产物落位：项目级/<项目>/标书检查/（机器检查_<项目>.json/.md、检查要点_<项目>、双通道检查差异_<项目>、标书检查报告_<项目>.html）

### M8 模拟评标 / M9·M10 补救
- evaluator → eval_report（评分标准 eval_std、rules）
- remedy：M8 产物 → 「失分补救任务单」（能力问题：素材补齐 业绩/职称/荣誉/体系 vs 响应问题）→ 逐项补救再投标

### M1 素材库（命令即流程）
- init-enterprise（企业初始化）→ open-inbox / upload / sync-inbox / close-inbox（收件箱流程）
- build-name（按关键字命名，多页加页码）/ classify（分类）→ 归档入库
- propose（变更提议）/ apply（应用变更）/ validate / inspect / ownership-check（归档即受保护，变更走标准流程）
- trash（回收站）/ cleanup-trash（默认保留 30 天）/ rm-project / reconcile

## 3. 当前 UI 自造项 vs 真实项（修订清单）

| UI 位置 | 自造（错） | 真实（对） | 状态 |
|---|---|---|---|
| 向导步骤 1 | 导入招标文件（OCR） | M4 双通道：文档解析 + 投标要点 + 双通道差异 + 投标要点 html 闸门① | 待改 |
| 向导步骤 2 | 表单+手动判定 | tech-init：按投标要点文本含「暗标」判定 + --bid-mode 覆盖 + 页数抽取 | 待改 |
| 向导步骤 3 | 目录勾选 | tech-outline：章节树草案校验 → 覆盖矩阵（评分点覆盖）→ 落盘 | 待改 |
| 向导步骤 4 | 生成策略+预设 | tech-ctx（上下文包）→ 正文编写 → tech-parse（非空/字数/占位/敏感词→WRITTEN） | 待改 |
| 向导步骤 5 | 导出选项+自造检查清单 | tech-check 通道A六项（覆盖/结构/篇幅/敏感词/一致性/占位）+ tech-report 闸门② + T10 导出 | 待改 |
| 编辑器章节树 | 无状态 | 每章真实状态 PENDING/CONTEXT_READY/WRITING/WRITTEN/CHECKED/CONFIRMED/FAILED | 待改 |
| 编辑器工具栏 | AI 生成/插入图表 | tech-ctx / tech-parse / tech-check / tech-report | 待改 |
| 编辑器状态栏 | 自造页数估算 | 章节状态 + 字数 + 页数预算（来自招标抽取）+ 预设 | 待改 |
| 素材库快捷操作 | 上传/归档/回收站 | open-inbox/upload/sync-inbox/close-inbox + build-name/classify + propose/apply + trash/cleanup-trash | 待改 |
| 项目屏流程组 | 检查/导出/资料 | 招标解析 / 技术标 / 标书检查 / 补救任务单（项目级/<项目>/ 产物目录） | 待改 |
| 风格配置 / 工作台系统状态 / 暗标合规校验 | — | 已对齐真实（15 组×10 套、layout.* 校验、审计 C1–C9、回归计数） | 已正确 |

## 4. 结论
UI 骨架（混合导航）与风格配置已对齐真实数据；向导、编辑器、素材库、项目屏存在自造逻辑，按下表逐项修订为真实命令/产物/状态机。
