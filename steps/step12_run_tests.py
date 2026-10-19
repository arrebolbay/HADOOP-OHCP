#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step12_run_tests.py —— 第 12 步：运行自动化测试并生成测试报告
================================================================================
测试框架：Python 标准库 unittest（零额外依赖，pytest 也能直接跑）。
覆盖：
    * 国标限值与边界（GB 3095-2012）
    * 清洗规则（缺失/越界/重复/全空）
    * 分片聚合口径（年均/月度/省份占比/O₃ 8h）
    * 规划器意图解析与多轮记忆
    * Agent 工具链端到端（真实数据子集 fixture）
    * MySQL 跨引擎对账（就绪时）

输出：output/test_report.txt（答辩时直接展示测试通过率）
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, ok, warn, info


def main():
    banner("第 12 步：自动化测试")
    cmd = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    proc = subprocess.run(cmd, cwd=str(config.PROJECT_DIR),
                          capture_output=True, text=True, timeout=1800)
    output = proc.stdout + "\n" + proc.stderr
    print(output[-8000:])

    report = [f"自动化测试报告  {datetime.now():%Y-%m-%d %H:%M:%S}",
              "=" * 70,
              "测试框架：unittest（pytest 可直接运行同一套用例）",
              "覆盖范围：国标判定 / 数据清洗 / 分片聚合 / 规划器 / E2E / 跨引擎对账",
              "", output]
    path = config.OUTPUT_DIR / "test_report.txt"
    path.write_text("\n".join(report), encoding="utf-8")

    if proc.returncode == 0:
        ok(f"测试全部通过，报告：{path}")
    else:
        warn(f"存在失败用例，请查看 {path}")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
