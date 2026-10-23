# -*- coding: utf-8 -*-
"""T10 tech-export 样张生成器（一次性）：明标 + 暗标两份 docx → dev/reports/t10-sample/。"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

REPO = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO / "dev" / "reports" / "t10-sample"

from m6_tech import export  # noqa: E402


class _A:
    def __init__(self, root, enterprise, project, override="", bid_mode="", out=""):
        self.root = str(root)
        self.enterprise = enterprise
        self.project = project
        self.override = override
        self.bid_mode = bid_mode
        self.out = out


def make_fixture(root, dark):
    shared = root / "共享资源" / "技术标风格"
    shared.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(str(REPO / "共享资源" / "技术标风格" / "layout-presets.json"),
                    str(shared / "layout-presets.json"))
    ent = root / "安徽安硕工程咨询有限公司"
    tech = ent / "项目级" / "市政务服务中心项目" / "技术标"
    for d in ("章节", "章节/.meta", "检查", "产出", "源文件"):
        (tech / d).mkdir(parents=True, exist_ok=True)
    for cid in ("ch-01", "ch-02", "ch-03"):
        (tech / "章节" / cid).mkdir(parents=True, exist_ok=True)
    chs = []
    titles = {
        "ch-01": "第一章 工程概况与监理工作范围",
        "ch-02": "第二章 监理工作依据、目标与内容",
        "ch-03": "第三章 项目监理机构及人员配备",
    }
    layout = {
        "preset": "single-column", "palette": "deep-indigo", "cover": "full-block",
        "decoration": "standard", "font": "gov-gongwen", "imageRatio": "mid",
        "imageRule": "hybrid", "imageLayout": "split-h", "pageSetup": "p1-standard-a4",
        "headingSystem": "h1-gbt-arabic", "tocStyle": "t1-jianyu-auto",
        "tableStyle": "tb1-three-line", "captionSystem": "c2-cy-chapter",
        "paragraphStyle": "pa7-jianyu-15", "headerFooter": "hf1-classic-enterprise",
    }
    if dark:
        layout.update({"font": "dark-safe", "cover": "none", "decoration": "none",
                       "imageRatio": "none", "pageSetup": "p7-hb-25-20",
                       "headingSystem": "h2-tender-arabic", "tocStyle": "t3-qinghai-nopage",
                       "tableStyle": "tb7-dark-0.5", "captionSystem": "c9-dark-appendix",
                       "paragraphStyle": "pa3-hebei-30", "headerFooter": "hf9-dark-none"})
    for i, cid in enumerate(("ch-01", "ch-02", "ch-03")):
        chs.append({"id": cid, "title": titles[cid], "status": "WRITTEN",
                    "files": {"body": "章节/%s/正文.md" % cid}})
    tree = {"schema": "m6.tree/v1", "project": "市政务服务中心项目", "layout": layout,
            "confirmed": True, "chapters": chs}
    (tech / "章节树.json").write_text(json.dumps(tree, ensure_ascii=False), encoding="utf-8")

    bodies = {
        "ch-01": (
            "# 一、工程概况\n"
            "市政务服务中心项目位于主城区政务新区，总建筑面积约 8.6 万平方米，其中地上 6.2 万平方米，"
            "地下 2.4 万平方米，框架剪力墙结构，地上十层、地下两层，建筑高度 45.6 米。\n"
            "## （一）项目理解\n"
            "本项目为市级重点民生工程，建成后承担政务服务集中办理职能，对工程质量、进度、投资控制"
            "及安全文明施工要求高，监理工作覆盖质量、进度、投资、安全环保与合同信息管理五大目标。\n"
            "- 质量控制：材料进场验收、旁站监理、见证取样\n"
            "- 进度控制：总控计划动态纠偏、周报制度\n"
            "- 投资控制：工程量复核与变更签证管理\n"
            "- 安全环保：危大工程专项巡视与扬尘管控\n"
            "| 序号 | 控制目标 | 主要措施 |\n"
            "| --- | --- | --- |\n"
            "| 1 | 质量目标 | 三检制、样板引路 |\n"
            "| 2 | 进度目标 | 关键线路周报纠偏 |\n"
            "| 3 | 投资目标 | 动态成本台账 |\n"
            "| 4 | 安全目标 | 危大工程旁站巡视 |\n"
            "### 1. 监理工作范围\n"
            "施工阶段监理，含土建、安装、装饰、智能化、室外工程等全部专业，以及保修阶段的监理服务。\n"
        ),
        "ch-02": (
            "# 一、监理工作依据\n"
            "1. 国家和地方有关工程建设的法律、法规与规章；\n"
            "2. 《建设工程监理规范》GB/T 50319-2013；\n"
            "3. 本项目招标文件、监理合同及施工合同；\n"
            "4. 施工图设计文件与现行工程建设标准、规范。\n"
            "## （一）监理工作目标\n"
            "确保工程质量达到一次性验收合格标准，争创省级优质工程；进度满足合同节点要求；"
            "投资控制在批准概算内；杜绝重大安全事故。\n"
            "| 目标项 | 目标要求 |\n"
            "| --- | --- |\n"
            "| 质量 | 一次验收合格率 100%，争创省级优质工程 |\n"
            "| 进度 | 满足合同工期及各里程碑节点 |\n"
            "| 投资 | 控制在批准概算范围内 |\n"
            "| 安全 | 无重大安全责任事故 |\n"
            "### 1. 监理工作制度\n"
            "建立监理例会制度、旁站监理制度、见证取样制度、巡视检查制度、资料管理制度。\n"
            "#### （1）例会制度\n"
            "每周召开监理例会，形成会议纪要并闭环跟踪落实。\n"
        ),
        "ch-03": (
            "# 一、项目监理机构\n"
            "本工程实行总监理工程师负责制，设立项目监理部，配备总监理工程师 1 名、"
            "专业监理工程师 5 名（土建、安装、市政、安全、造价各 1 名）、监理员 4 名。\n"
            "## （一）人员配备\n"
            "总监理工程师：高级工程师，注册监理工程师，从事监理工作 15 年以上，类似业绩 3 项；\n"
            "专业监理工程师：中级及以上职称，持证上岗，具备同类工程经验。\n"
            "| 岗位 | 人数 | 资格要求 |\n"
            "| --- | --- | --- |\n"
            "| 总监理工程师 | 1 | 注册监理工程师、高级职称 |\n"
            "| 土建专业监理工程师 | 1 | 中级及以上职称 |\n"
            "| 安装专业监理工程师 | 1 | 中级及以上职称 |\n"
            "| 安全专业监理工程师 | 1 | 注册安全工程师优先 |\n"
            "| 造价专业监理工程师 | 1 | 注册造价工程师 |\n"
            "| 监理员 | 4 | 持监理员培训证 |\n"
            "### 1. 仪器设备配置\n"
            "配备全站仪、水准仪、回弹仪、钢筋保护层测定仪、坍落度筒、卷尺等常规检测仪器，"
            "以及监理信息化管理平台。\n"
        ),
    }
    for cid, body in bodies.items():
        (tech / "章节" / cid / "正文.md").write_text(body, encoding="utf-8")
        ctx = {"schema": "m6.ctx/v1", "chapter": cid, "project": "市政务服务中心项目",
               "context": {"tender_points": ["暗标" if dark else "明标"], "pageBudget": 900}}
        (tech / "章节" / ".meta" / (cid + ".json")).write_text(
            json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    return root


def main():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else (SAMPLE_DIR / "fixture")
    if base.exists():
        shutil.rmtree(str(base))
    # 明标
    root_m = make_fixture(base / "mingbiao", dark=False)
    export.cmd_tech_export(_A(root_m, "安徽安硕工程咨询有限公司", "市政务服务中心项目"))
    # 暗标
    root_d = make_fixture(base / "anbiao", dark=True)
    export.cmd_tech_export(_A(root_d, "安徽安硕工程咨询有限公司", "市政务服务中心项目"))
    print("样张目录: %s" % SAMPLE_DIR)


if __name__ == "__main__":
    main()
