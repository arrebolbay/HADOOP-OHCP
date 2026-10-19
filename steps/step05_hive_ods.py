#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step05_hive_ods.py —— 第 5 步：Hive ODS 贴源层外部表
================================================================================
执行 sql/hive/01_create_ods.sql：
    * 建库 air_quality
    * 建外部表 ods_air_quality（指向 HDFS 上的分片 CSV）
    * 查询行数与样例，确认 Hive 真的读到了数据
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, error, print_table, hive_file, hive_rows


def main():
    banner("第 5 步：Hive ODS 贴源层")
    sql_file = config.HIVE_SQL_DIR / "01_create_ods.sql"
    if not sql_file.exists():
        error(f"缺少 SQL 文件：{sql_file}")
        return 1

    info(f"执行 {sql_file.name}（Hive 首次启动需要 20~60 秒）")
    code, _ = hive_file(sql_file, log_name="05_hive_ods.log", timeout=1800)
    if code != 0:
        error("Hive 建表失败，请查看 logs/05_hive_ods.log")
        return 1

    code, rows = hive_rows(f"SELECT COUNT(*) FROM {config.HIVE_DB}.ods_air_quality",
                           timeout=900)
    if code != 0 or not rows:
        error("ODS 行数查询失败")
        return 1
    ods_rows = int(rows[0][0])

    local_rows = 0
    for path in sorted(config.RAW_CHUNK_DIR.glob(f"air_quality_{config.DATASET_YEAR}-*.csv")):
        with open(path, encoding="utf-8") as f:
            local_rows += max(sum(1 for _ in f) - 1, 0)
    diff = abs(ods_rows - local_rows)
    ok(f"ODS 行数 = {ods_rows:,}，本地分片行数 = {local_rows:,}，差 {diff}")
    if diff > 0:
        info("差异通常来自空行或 Hive 对非法行的过滤，属正常现象")

    code, sample = hive_rows(
        f"SELECT city, province, dt, hour, pm25, aqi, quality "
        f"FROM {config.HIVE_DB}.ods_air_quality LIMIT 5", timeout=900)
    print_table(sample, headers=["城市", "省份", "日期", "时", "PM2.5", "AQI", "等级"],
                title="ODS 样例")
    info("下一步：step06 执行 DWD → DWS → ADS 三层建模")
    return 0


if __name__ == "__main__":
    sys.exit(main())
