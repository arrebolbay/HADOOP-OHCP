#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all.py —— 一键跑完全链路（项目总入口）
================================================================================
12 个步骤：
     1 环境自检        2 数据接入分片     3 数据探查 + 清洗
     4 上传 HDFS       5 Hive ODS       6 Hive DWD/DWS/ADS
     7 MapReduce 对账  8 MySQL 建表      9 MySQL 装载
    10 Agent 演示     11 分析看板       12 自动化测试

运行方式（在项目根目录）：
    python3 run_all.py                  # 从第 1 步跑到第 12 步
    python3 run_all.py 2               # 从第 2 步开始（环境已确认过）
    python3 run_all.py 7 12            # 只跑第 7~12 步
    python3 run_all.py --list           # 只看步骤清单
    python3 run_all.py --keep-going     # 某步失败也继续（调试用）
    AQ_PLANNER=rule python3 run_all.py  # 强制规则规划器（无网络演示）
    python3 web/server.py               # 启动网页前端（http://127.0.0.1:8000）

【赛前准备】
    python3 scripts/download_real_data.py --start 2024-01-01 --end 2024-12-31
    python3 scripts/build_province_map.py
    启动 Hadoop：/opt/hadoop/sbin/start-dfs.sh && /opt/hadoop/sbin/start-yarn.sh
"""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import STEPS_DIR, LOG_DIR, ensure_dirs
from common import banner, info, ok, warn, error, print_table, hr

STEPS = [
    (1, "step01_check_env.py", "环境自检：命令 / 守护进程 / MySQL / 依赖 / 数据 / 字体"),
    (2, "step02_prepare_data.py", "真实数据接入：宽表转长表、补省份、按月分片"),
    (3, "step03_explore_data.py", "数据质量探查 + 清洗（缺失/越界/IQR/填充/去重）"),
    (4, "step04_hdfs_upload.py", "分片上传 HDFS（ODS 原始层）"),
    (5, "step05_hive_ods.py", "Hive 建库 + ODS 外部表"),
    (6, "step06_hive_dwd_dws_ads.py", "Hive DWD→DWS→ADS 三层建模 + pandas 对账"),
    (7, "step07_mapreduce_alignment.py", "MapReduce 独立计算 + 双引擎对账"),
    (8, "step08_mysql_schema.py", "MySQL 建库建表（视图/存储过程/事件）"),
    (9, "step09_mysql_load.py", "装载结果：Hive ADS → MySQL + 本地聚合"),
    (10, "step10_agent_demo.py", "Agent 演示：官方示例 + 多轮追问 + 异常告警"),
    (11, "step11_dashboard.py", "综合分析看板（4 图合一）"),
    (12, "step12_run_tests.py", "自动化测试 + 测试报告"),
]


def print_steps():
    banner("项目步骤清单")
    print_table([(n, f, d) for n, f, d in STEPS],
                headers=["步骤", "脚本", "作用"], max_rows=20)


def run_step(n, script, title, log_file):
    path = STEPS_DIR / script
    if not path.exists():
        error(f"找不到脚本：{path}")
        return False, 0.0

    print()
    hr("=")
    print(f"  ▶ 第 {n} 步：{title}")
    print(f"    脚本：steps/{script}")
    hr("=")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    t0 = time.time()
    with open(log_file, "a", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            [sys.executable, str(path)], stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
            env=env, cwd=str(path.parent.parent))
        try:
            for line in proc.stdout:
                print(line, end="")
                logf.write(line)
            proc.wait()
        except KeyboardInterrupt:
            proc.kill()
            proc.wait()
            raise
    elapsed = time.time() - t0
    with open(log_file, "a", encoding="utf-8") as logf:
        logf.write(f"\n[返回码] {proc.returncode}  [耗时] {elapsed:.1f}s\n")
    return proc.returncode == 0, elapsed


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("-")]
    if "--list" in argv[1:]:
        print_steps()
        return 0

    start, end = 1, 12
    if len(args) == 1 and args[0].isdigit():
        start = int(args[0])
    elif len(args) == 2 and all(a.isdigit() for a in args):
        start, end = int(args[0]), int(args[1])
    if not (1 <= start <= 12 and 1 <= end <= 12 and start <= end):
        error("用法：python3 run_all.py [起始步骤 [结束步骤]]（1~12）")
        return 2

    keep_going = "--keep-going" in argv[1:]
    ensure_dirs()
    banner("空气质量时序分析 Agent —— 一键全链路")
    log_file = LOG_DIR / f"run_all_{datetime.now():%Y%m%d_%H%M%S}.log"
    info(f"计划：第 {start} → {end} 步｜日志：{log_file.name}")
    info(f"规划器模式：{os.environ.get('AQ_PLANNER', 'auto')}"
         f"｜大模型 Key：{'已配置' if os.environ.get('AQ_LLM_API_KEY') else '未配置（规则兜底）'}")

    results, failed = [], None
    total_t0 = time.time()
    for n, script, title in STEPS:
        if not (start <= n <= end):
            continue
        try:
            success, elapsed = run_step(n, script, title, log_file)
        except KeyboardInterrupt:
            results.append((n, "已中止", "-", title))
            failed = n
            break
        results.append((n, "成功" if success else "失败", f"{elapsed:.1f}s", title))
        if success:
            ok(f"第 {n} 步完成（{elapsed:.1f}s）")
        else:
            error(f"第 {n} 步失败，详见日志 {log_file}")
            failed = n
            if not keep_going:
                break

    total = time.time() - total_t0
    banner("运行汇总")
    print_table(results, headers=["步骤", "结果", "耗时", "说明"], max_rows=20)
    info(f"总耗时 {total:.1f} 秒（约 {total / 60:.1f} 分钟）")
    if failed:
        error(f"第 {failed} 步未通过。修复后可从该步续跑：python3 run_all.py {failed}")
        return 1
    ok("★ 全链路执行成功：数据 → Hive → MapReduce → MySQL → Agent → 图表 → 测试")
    info("产出物：output/（演示记录、看板、对账报告、测试报告、图表）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
