"""Run focused mathematical, capture and evaluator checks without GPU workloads."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))


def main():
    suite=unittest.TestSuite()
    for pattern in ('test_continuous*.py','test_offline_reconciliation.py','test_pose_repair_memory.py',
                    'test_effective_execution_budget.py','test_marker_localization.py'):
        suite.addTests(unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern=pattern))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)


if __name__=='__main__':main()
