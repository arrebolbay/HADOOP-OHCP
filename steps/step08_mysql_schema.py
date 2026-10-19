#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step08_mysql_schema.py —— 第 8 步：MySQL 结果库建表
================================================================================
执行 sql/mysql/01_schema.sql（通过 mysql 客户端整文件执行，天然支持
DELIMITER 分隔的存储过程），然后校验表/视图/存储过程/事件是否创建成功。

【为什么结果库要单独设计？】
    Hive 适合"算"，不适合"秒级查"。把 ADS 结果同步到 MySQL 后，
    Agent 与前端查询可以毫秒级响应；维表/事实表结构也让口径更清晰。
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import (banner, info, ok, warn, error, print_table,
                    mysql_query, mysql_execute, hadoop_env)


def run_sql_file(path):
    cmd = ["mysql", "-h", config.MYSQL_HOST, "-P", str(config.MYSQL_PORT),
           f"-u{config.MYSQL_USER}", f"-p{config.MYSQL_PASSWORD}",
           "--default-character-set=utf8mb4"]
    with open(path, encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdin=f, capture_output=True, text=True,
                              env=hadoop_env(), timeout=300)
    if proc.returncode != 0:
        error(proc.stderr[-1500:])
    return proc.returncode


def main():
    banner("第 8 步：MySQL 结果库建表")
    sql_file = config.MYSQL_SQL_DIR / "01_schema.sql"
    if not sql_file.exists():
        error(f"缺少 SQL 文件：{sql_file}")
        return 1

    info(f"执行 {sql_file.name}（建库 + 3 张事实表 + 维表 + 2 个视图 + 存储过程 + 事件）")
    if run_sql_file(sql_file) != 0:
        error("建表脚本执行失败")
        return 1
    ok("建表脚本执行完成")

    try:
        mysql_execute("SET GLOBAL event_scheduler = ON")
        info("已开启 MySQL 事件调度器（ev_refresh_exceed 每日刷新超标标记）")
    except Exception as exc:  # noqa: BLE001
        warn(f"事件调度器开启失败（不影响主链路）：{exc}")

    tables = mysql_query(
        "SELECT table_name, table_type FROM information_schema.tables "
        "WHERE table_schema=%s ORDER BY table_name", (config.MYSQL_DB,))
    rows = [(t["TABLE_NAME"] if "TABLE_NAME" in t else t.get("table_name"),
             t["TABLE_TYPE"] if "TABLE_TYPE" in t else t.get("table_type")) for t in tables]
    print_table(rows, headers=["对象", "类型"], max_rows=20, title="MySQL 对象清单")
    procs = mysql_query(
        "SELECT routine_name FROM information_schema.routines WHERE routine_schema=%s",
        (config.MYSQL_DB,))
    ok(f"表/视图 {len(rows)} 个，存储过程 {len(procs)} 个，库名 {config.MYSQL_DB}")
    info("下一步：step09 把 Hive ADS 结果与本地聚合结果装入 MySQL")
    return 0


if __name__ == "__main__":
    sys.exit(main())
