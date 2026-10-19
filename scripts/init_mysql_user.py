#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/init_mysql_user.py —— 初始化 MySQL 账号与结果库（一次性）
================================================================================
用途：很多 MySQL 8 安装里 root 使用 auth_socket，pymysql 无法用密码登录。
     本脚本用系统 root 权限创建项目专用账号（最小权限原则）：
        用户：aq_user / aq_pass_2026
        库  ：air_quality（utf8mb4）

用法（需要操作系统 root 或能免密登录 mysql 的账号）：
    python3 scripts/init_mysql_user.py
    MYSQL_USER=xxx MYSQL_PASSWORD=yyy python3 scripts/init_mysql_user.py   # 自定义
"""

import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import config
from common import info, ok, error


def main():
    user = os.environ.get("AQ_NEW_MYSQL_USER", config.MYSQL_USER)
    password = os.environ.get("AQ_NEW_MYSQL_PASSWORD", config.MYSQL_PASSWORD)
    db = config.MYSQL_DB
    sql = (f"CREATE DATABASE IF NOT EXISTS {db} DEFAULT CHARACTER SET utf8mb4; "
           f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY '{password}'; "
           f"GRANT ALL PRIVILEGES ON {db}.* TO '{user}'@'localhost'; "
           f"GRANT CREATE ON *.* TO '{user}'@'localhost'; "
           f"FLUSH PRIVILEGES;")
    info(f"创建账号 {user}@localhost 并授权 {db}.*")
    proc = subprocess.run(["mysql", "-uroot", "-e", sql],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        error(proc.stderr[-800:])
        info("可尝试手动执行：mysql -uroot -e \"...\"；或在 config.py 中改成本机可用的账号")
        return 1
    ok("MySQL 账号与结果库初始化完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
