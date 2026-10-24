# -*- coding: utf-8 -*-
"""unit：M5 mat-status —— 素材清单状态（配图通道视角，只读）：
fill 结构素材清单 → 图片类类别聚合（aggregate_category 真实消费逻辑）
→ has（已列且文件存在）/ broken（已列但路径断）/ empty（未列，红线不生成）。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from _shared import core          # noqa: E402
import m5_project as m5           # noqa: E402（包 __init__ 暴露 cmd_mat_status / MAT_IMG_CATS）


class MatStatusTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        core.Library(self.root).init_enterprise("素材企业")
        self.ent = self.root / "素材企业"
        self.project = "素材状态项目"
        proj = self.ent / "项目级" / self.project
        (proj / "招标解析").mkdir(parents=True, exist_ok=True)
        self.proj = proj

    def tearDown(self):
        self._tmp.cleanup()

    def _mk_args(self):
        class A:
            root = str(self.root)
            enterprise = None
            project = self.project
            json = True
        return A()

    def _write_material(self, material):
        (self.proj / "招标解析" / "素材清单.json").write_text(
            json.dumps(material, ensure_ascii=False), encoding="utf-8")

    def test_empty_all_categories(self):
        # 空素材清单 → 全部 empty（商务标红线：素材清单未列不生成）
        self._write_material({"project": self.project, "企业基础信息": {}})
        r = m5.cmd_mat_status.__wrapped__ if hasattr(m5.cmd_mat_status, "__wrapped__") else None
        # 直接调用函数（--json 分支打印，用对象断言）
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            m5.cmd_mat_status(self._mk_args())
        out = json.loads(buf.getvalue())
        self.assertTrue(out["ok"])
        self.assertEqual(out["summary"]["empty"], len(m5.MAT_IMG_CATS))
        self.assertEqual(out["image_total"], 0)

    def test_has_and_broken(self):
        # qualification_required 带真实文件 → has；带不存在路径 → broken
        (self.proj / "招标解析").mkdir(parents=True, exist_ok=True)
        real = self.proj / "项目资料" / "营业执照.png"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_bytes(b"x" * 8)
        material = {
            "project": self.project,
            "企业基础信息": {},
            "qualification_required": [
                {"name": "企业法人营业执照", "path": str(real)},
                {"name": "开户许可证", "path": str(self.proj / "项目资料" / "不存在.png")},
            ],
        }
        self._write_material(material)
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            m5.cmd_mat_status(self._mk_args())
        out = json.loads(buf.getvalue())
        self.assertEqual(out["image_total"], 2)
        self.assertEqual(out["image_exist"], 1)
        self.assertEqual(out["image_broken"], 1)
        self.assertEqual(out["categories"]["企业法人营业执照"]["status"], "has")
        self.assertEqual(out["categories"]["开户许可证"]["status"], "broken")
        self.assertEqual(out["summary"]["has"], 1)
        self.assertEqual(out["summary"]["broken"], 1)
        miss = {m["category"]: m["status"] for m in out["missing"]}
        self.assertEqual(miss["开户许可证"], "broken")

    def test_missing_material_raises(self):
        from _shared import core as _core
        with self.assertRaises(_core.LibraryError):
            m5.cmd_mat_status(self._mk_args())


if __name__ == "__main__":
    unittest.main()
