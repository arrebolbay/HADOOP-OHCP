#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step01_check_env.py —— 第 1 步：环境自检
================================================================================
检查项：
    1) Hadoop / Hive / Sqoop / MySQL 命令行是否可用；
    2) HDFS 与 YARN 守护进程是否在运行；
    3) MySQL 能否连接（能否建库）；
    4) Python 依赖（pandas / matplotlib / pymysql / requests）；
    5) 本地数据分片、城市→省份映射、中文字体是否就绪；
    6) 大模型 API Key 是否配置（没有也能跑，自动用规则规划器）。

【为什么第一步做这个？】
    比赛现场最怕"演示到一半发现 HDFS 没启动"。先把环境一次看清，
    失败项会明确告诉你该修什么，避免 40 分钟编码时间被环境问题吞掉。
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, warn, error, print_table, mysql_scalar, hadoop_env


def check_command(name):
    """按项目环境变量里的 PATH 检查命令（hive/sqoop 不在系统默认 PATH 中）。"""
    return shutil.which(name, path=hadoop_env()["PATH"]) is not None


def check_daemons():
    """用 jps 看 NameNode / DataNode / ResourceManager 是否存在。"""
    try:
        out = subprocess.run(["jps"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    wanted = ["NameNode", "DataNode", "ResourceManager", "NodeManager"]
    return [w for w in wanted if w in out]


def main():
    banner("第 1 步：环境自检")
    rows, failures = [], 0

    def add(item, passed, detail):
        nonlocal failures
        rows.append((item, "通过" if passed else "失败", detail))
        failures += 0 if passed else 1

    for tool in ("hadoop", "hive", "sqoop", "mysql"):
        path = shutil.which(tool, path=hadoop_env()["PATH"])
        add(f"命令 {tool}", path is not None, path or "未找到（检查 /opt 与 PATH）")

    daemons = check_daemons()
    add("HDFS/YARN 守护进程", len(daemons) >= 3, "运行中：" + (", ".join(daemons) or "无"))

    try:
        value = mysql_scalar("SELECT 1")
        add("MySQL 连接", value == 1,
            f"{config.MYSQL_USER}@{config.MYSQL_HOST}:{config.MYSQL_PORT}")
    except Exception as exc:  # noqa: BLE001
        add("MySQL 连接", False, f"{type(exc).__name__}: {exc}")

    libs = {"pandas": "pandas", "matplotlib": "matplotlib",
            "pymysql": "pymysql", "requests": "requests"}
    for label, module in libs.items():
        add(f"Python 库 {label}", importlib.util.find_spec(module) is not None,
            "已安装" if importlib.util.find_spec(module) else "未安装")

    chunks = sorted(config.RAW_CHUNK_DIR.glob(f"air_quality_{config.DATASET_YEAR}-*.csv"))
    add("原始数据分片", bool(chunks), f"{len(chunks)} 个文件：{config.RAW_CHUNK_DIR}")
    cleaned = sorted(config.CLEAN_CHUNK_DIR.glob(f"air_quality_{config.DATASET_YEAR}-*.csv"))
    add("清洗后分片", bool(cleaned), f"{len(cleaned)} 个文件（第 3 步会生成）")
    add("城市→省份映射", config.PROVINCE_MAP_CSV.exists(),
        str(config.PROVINCE_MAP_CSV))
    add("中文字体", config.font_path() is not None, str(config.font_path()))
    add("大模型 API Key", bool(config.LLM_API_KEY),
        "已配置（LLM 规划可用）" if config.LLM_API_KEY
        else "未配置（自动使用规则规划器，不影响演示）")

    print_table(rows, headers=["检查项", "结果", "说明"], max_rows=30)

    if failures:
        warn(f"有 {failures} 项未通过：Hadoop/Hive 相关项可先跳过，"
             f"Agent + 本地分片计算链路不依赖它们；MySQL 项影响结果库演示。")
    else:
        ok("环境全部就绪，可以开始全链路演示。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
