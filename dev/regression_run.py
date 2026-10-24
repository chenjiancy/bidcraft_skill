# -*- coding: utf-8 -*-
"""全量回归：unit / integration / e2e 三层汇总（执行桥交付用）。"""
import glob
import io
import os
import sys
import unittest

ROOTS = ("tests.unit", "tests.integration", "tests.e2e")
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


def collect():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for root in ROOTS:
        for f in sorted(glob.glob(os.path.join("tests", root.split(".")[1], "test_*.py"))):
            n = os.path.basename(f)[:-3]
            if n.startswith("_"):
                continue
            mod = __import__(root + "." + n, fromlist=["*"])
            suite.addTests(loader.loadTestsFromModule(mod))
    return suite


def main():
    buf = io.StringIO()
    runner = unittest.TextTestRunner(stream=buf, verbosity=1)
    result = runner.run(collect())
    print(buf.getvalue())
    print("FULL SUMMARY: run=%d fails=%d errors=%d skipped=%d" % (
        result.testsRun, len(result.failures), len(result.errors), len(result.skipped)))
    return 1 if (result.failures or result.errors) else 0


if __name__ == "__main__":
    sys.exit(main())
