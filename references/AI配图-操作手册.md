# AI 配图 · 操作手册（m_img，v1.0）

> 定位：跨 M4/M5 的**素材生产管道**——从投标要点（M4 产物）确定配图需求，双通道生图，
> 图片**必须落盘**到项目级 `配图/` 目录并回填清单，供 fill-tpl（M5）按清单位置嵌入 docx。
> 一句话：**谁要图、要什么图、图在项目哪个文件里，全部有清单可查、有文件可验。**

---

## 一、为什么要配图清单（而不是让 agent 随便插）

标书里的图不能是"AI 随手画的装饰"，必须是**按投标文件格式、评分点、废标红线**安排的
可验证资产。配图清单是**唯一事实源**：

- **脚本**（`img-plan`）从投标要点**确定性生成**骨架：哪些章节按规则需要图（人员配置框图/
  项目概况示意图/资质框架图/评分对照图），每张图的用途、建议比例、风格模板。
- **agent**（豆包/CodeBuddy）可以**改写/增删**清单项（语义判断哪里配图更合理）。
- **落盘回填**（`img-save`）把图片收进项目目录、状态从 `pending → saved`——**没落盘的图
  等于不存在**，嵌入引擎只认 `saved` 项。

状态机：`pending`（待生成）→ `saved`（已落盘，可嵌入）／`skipped`（明确跳过，如素材库已有）。

---

## 二、流程总览（5 步）

```
① 定图   img-plan         投标要点 → 配图清单骨架（脚本确定性；agent 可改写）
② 要图   清单即需求       {哪一章、多大、什么内容、什么风格}
③ 生图   双通道          豆包 agent 原生生图 / CodeBuddy ImageGen / 即梦 API（备选）
④ 交图   img-save        图片 → <项目>/配图/<id>.<png|jpg>，清单回填 saved（交接协议核心）
⑤ 嵌图   fill-tpl(M5)    模板「【图片占位：AI配图-<section>】」按清单 saved 项嵌入 docx（v1.1 已实现）
```

**嵌图通道（v1.1 新增）**：fill-tpl 识别 `【图片占位：AI配图-<section>】` 类别（section =
配图清单项的章节名，如「项目概况与监理工作内容」），从 `配图/配图清单_<项目>.json` 取
**status=saved** 且 section 匹配的项嵌入（宽 16cm 全宽、高按原图等比）；pending/未匹配
→ 删框并在缺图清单披露。与证书/执照素材通道（aggregate_category）完全并列，互不影响。

**交接协议（硬规则）**：任何通道生出的图，**必须**经 `img-save` 落盘并回填 `saved`，
才算"配图完成"；只把图发给用户看、未落盘的，视为未完成（agent 不得声称完成）。
**img-save 是"校验 + 清洗 + 归档"三合一收口（v1.2 实测强化）**：
- 平台产物（豆包/即梦/CodeBuddy ImageGen 等）常内嵌 **AIGC 元数据段**（JPEG APP11
  `AIGC{...}`，python-docx 直接嵌入会报 `UnrecognizedImageError`）→ img-save 用 PIL
  **重编码清洗**后落盘，产出 Word/python-docx 可直接识别的标准文件；
- 归档**扩展名按真实格式**判定（扩展名 `.png` 实为 JPEG → 落 `img_005.jpg`，不落错配
  `.png`）——**平台产物必须先经 img-save 清洗才能进正式文档**，这是交接协议的底线。

---

## 三、产物与落位

```
<软件根>/<企业>/项目级/<项目名>/配图/
  配图清单_<项目>.json        # 机读清单（唯一事实源）
  img_001.png / img_002.jpg   # 图片本体（id 与清单一一对应）
```

配图清单 JSON 结构：

```json
{
  "project": "项目名",
  "generated_at": "2026-10-24 17:40:00",
  "items": [
    {
      "id": "img_001",
      "section": "资格条件",            // 嵌入章节（投标要点模块标题）
      "kind": "框图",                   // 框图/示意图/对照图
      "ratio": "16:9",                  // 建议画幅
      "subject": "企业组织机构与资质框架图",
      "style": "商务正式、扁平化、蓝色系",
      "status": "saved",                // pending/saved/skipped
      "source": "CodeBuddy",            // CodeBuddy/豆包/即梦API/用户提供
      "file": "配图/img_001.png",       // saved 后回填
      "created_at": "...",
      "saved_at": "..."
    }
  ]
}
```

---

## 四、命令速查

| 命令 | 作用 | 写操作？ |
| --- | --- | --- |
| `img-plan --project <名>` | 从投标要点生成/合并配图清单（幂等：已有项不重复） | 否（生成清单产物） |
| `img-save --project <名> --id <img_00x> --file <图片路径> [--source <来源>]` | 图片收口落盘：校验（png/jpg/jpeg、≤10MB）→ **PIL 清洗重编码（剥离 AIGC 元数据段，v1.2）** → 按真实格式归档 `配图/<id>.<png|jpg>` → 回填 `saved` | **是**（执行桥须 `confirm:true`） |
| `img-status --project <名> [--json]` | 查看清单状态（待生成/已落盘 计数 + 明细） | 否 |
| `fill-tpl --project <名> [--agent <代理>]` | M5 嵌图：模板含 `【图片占位：AI配图-<section>】` 时按清单 saved 项嵌入商务标 | **是**（CLI 人工确认闸门） |

前置：项目已完成 M4 双通道解析（`招标解析/投标要点_<项目>.json` 存在）。

---

## 五、双通道执行说明

### 通道 A · 豆包对话框（平台 agent 原生）
1. 用户/豆包 agent 先跑 `img-plan` 生成清单（或 agent 直接改清单）。
2. **豆包 agent 调用平台生图能力**逐项出图（原生生图，无额外依赖）。
3. **交接**：agent 把图保存到本地——通过本地 CLI `img-save --id <img_00x> --file <图>`，
   或用户在会话中确认后由 agent 落盘。**必须回填 `saved`**。
4. 全部 `saved` 且用户确认后，进入 fill-tpl 嵌入（M5）。

### 通道 B · UI / CodeBuddy（执行桥）
1. UI 执行桥调 `img-plan`（read）→ 清单展示。
2. `tender-agent-parse` 式 agent 桥调 CodeBuddy，prompt 含 ImageGen 工具要求（**授权结论见文末实测**）。
3. CodeBuddy 生成的图片文件 → `img-save --id … --file <CodeBuddy 产物路径> --source CodeBuddy`（write，须用户确认）。
4. 落盘回填后嵌入。

### 备选 · 即梦开放平台 API（火山引擎）
若平台工具不可用/需授权，可挂即梦 API（`visual.volcengineapi.com` 图片生成 4.6）：
脚本侧新增生图执行器（API key 环境变量 `JIMENG_API_KEY`），产物落盘后同样走 `img-save`。

---

## 六、生图提示词模板（agent 用）

```
生成一张标书配图：
- 主题：{item.subject}
- 类型：{item.kind}（{item.ratio}）
- 风格：{item.style}，画面内禁止出现真实单位名称/LOGO/人名（暗标要求）
- 附加：画面不得包含任何水印、AI 生成标识、平台标识、角标
- 用途：嵌入 {item.section} 章节
- 输出：保存为图片文件后，用 img-save --id {item.id} --file <文件路径> --source <通道> 落盘
```

暗标红线：**图中不得出现公司名、LOGO、可识别标识**（与投标要点「废标红线·暗标」一致）。
水印红线：实测发现 CodeBuddy ImageGen 产物右下角默认带「AI 生成」角标——提示词必须显式
要求无水印；若产物仍有角标，`img-save` 前先裁掉该区域（或用 `mediakit-cli image`
crop 处理），否则不得进入正式文档。

---

## 七、边界与失败处理

- 投标要点缺失 → `img-plan` 明确报错并引导先完成 M4，不生成空清单。
- 图片校验失败（格式/大小）→ `img-save` 拒绝，不落盘。
- 重复落盘（同 id 已有文件）→ 拒绝，提示先清理。
- 平台生图失败/需授权 → 如实报错，可切另一通道（CodeBuddy ↔ 豆包 ↔ 即梦 API）。
- **人工确认闸门**：`img-save` 为写操作，执行桥侧必须 `confirm:true`；批量落盘前
  先 `img-status` 核对清单。

---

## 八、CodeBuddy ImageGen 授权实测结论（2026-10-24 实测）

**结论：headless 默认拒绝，加 `-y` 即通，生成/落盘全成功。**

| 项 | 实测结果 |
| --- | --- |
| 默认 headless 调用 | ❌ 拒绝：`DeferExecuteTool permission denied`，非交互无法弹确认，图片未生成 |
| 加 `-y`（bypassPermissions） | ✅ `permission_denials` 为空，34s 生成 1536×1024 图，1.77MB 真实落盘 |
| 产物真实性 | ✅ 实测 `IMAGE_DONE_<路径>` 返回与实际文件一致（监理组织机构框图，三层结构正确） |
| 消耗 | 约 5-10 credits/张（官方说明） |
| 水印 | ⚠️ 产物右下角默认带「AI 生成」角标 → 提示词要求无水印 + 落盘前检查/裁剪 |

**CodeBuddy 通道调用姿势（bridge 侧，写死入白名单）：**
```
codebuddy -p -y "<生图提示词（含保存路径）>" --output-format json
```
- `-y` 只影响 CodeBuddy 侧自身工具权限，**不绕过** bidcraft 的落盘校验与执行桥
  `img-save confirm:true` 闸门（图片仍须经校验后才进正式 `配图/` 目录）。
- 图片先由 CodeBuddy 写到**临时/指定目录**（如 `<项目>/配图/临时/`），确认后再 img-save 归档。
- 安全边界：`-y` 授予了 CodeBuddy 自由写文件能力 → prompt 必须把输出路径限定在
  项目级 `配图/` 临时区，禁止写入其他目录。

**双通道结论汇总：**
- 通道 A（豆包）：平台原生生图，无授权问题（用户判断成立）；交接靠 `img-save` 落盘。
- 通道 B（CodeBuddy）：**需 `-y` 授权模式**，已实测打通；备用即梦 API。
- 因此**无需自研 agent+LLM**：生图作为平台工具子能力，图片交接协议（img-save）是唯一新增点。
