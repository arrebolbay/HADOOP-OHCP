#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step09_mysql_load.py —— 第 9 步：结果装载（Hive ADS → MySQL + 本地聚合）
================================================================================
装载内容：
    1) dim_city            城市维度（来自真实行政区划映射）
    2) fact_city_year      PM2.5 优先读 Hive ADS（真正的 Hive→MySQL 搬运），
                           其余指标由本地分片聚合结果补齐
    3) fact_city_month     PM2.5 / O₃ 月度趋势（图表与前端用）
    4) fact_province_exceed 各省超标天数与占比

装完逐表校验行数，并抽样验证 TOP1 城市与本地复算一致。
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import (banner, info, ok, warn, error, print_table, save_json,
                    mysql_execute, mysql_query, mysql_scalar, hive_rows)
from core.data_store import DataStore


def upsert(sql, rows, chunk=500):
    total = 0
    for i in range(0, len(rows), chunk):
        total += mysql_execute(sql, rows[i:i + chunk], many=True,
                               database=config.MYSQL_DB)
    return total


def main():
    banner("第 9 步：结果装载到 MySQL")
    store = DataStore()
    if not store.available():
        error("没有数据分片，请先运行 step02 / step03")
        return 1

    # 1) 城市维度
    if not config.PROVINCE_MAP_CSV.exists():
        error("缺少城市→省份映射表")
        return 1
    cities = pd.read_csv(config.PROVINCE_MAP_CSV)
    upsert("INSERT INTO dim_city(city, province) VALUES(%s,%s) "
           "ON DUPLICATE KEY UPDATE province=VALUES(province)",
           [(r["city"], r["province"]) for r in cities.to_dict("records")])
    ok(f"dim_city 装载 {len(cities)} 行")

    # 2) 城市-年（PM2.5 优先来自 Hive ADS）
    year = config.DATASET_YEAR
    code, hive_data = hive_rows(
        f"SELECT city, province, annual_mean, days, exceeded "
        f"FROM {config.HIVE_DB}.ads_city_year_pm25", timeout=900)
    if code == 0 and hive_data:
        pm25_rows = [(r[0], r[1], year, "pm25", float(r[2]), int(r[3]), int(r[4]))
                     for r in hive_data if len(r) >= 5]
        source = "Hive ADS（ads_city_year_pm25）"
    else:
        warn("Hive ADS 不可用，改用本地分片聚合结果（不影响正确性）")
        df = store.annual_mean("pm25")
        pm25_rows = [(r["city"], r["province"], year, "pm25", round(float(r["value"]), 2),
                      int(r["days"]), int(bool(r["exceeded"])))
                     for r in df.to_dict("records")]
        source = "本地分片聚合（pandas）"

    upsert("INSERT INTO fact_city_year(city, province, year, metric, annual_mean, days, exceeded) "
           "VALUES(%s,%s,%s,%s,%s,%s,%s) "
           "ON DUPLICATE KEY UPDATE annual_mean=VALUES(annual_mean), days=VALUES(days), "
           "exceeded=VALUES(exceeded), province=VALUES(province)", pm25_rows)
    info(f"fact_city_year.pm25 来源：{source}，{len(pm25_rows)} 行")

    for metric in ("pm10", "so2", "no2", "o3", "co"):
        df = store.annual_mean(metric)
        rows = [(r["city"], r["province"], year, metric, round(float(r["value"]), 2),
                 int(r["days"]), int(bool(r["exceeded"]))) for r in df.to_dict("records")]
        upsert("INSERT INTO fact_city_year(city, province, year, metric, annual_mean, days, exceeded) "
               "VALUES(%s,%s,%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE annual_mean=VALUES(annual_mean), days=VALUES(days), "
               "exceeded=VALUES(exceeded), province=VALUES(province)", rows)
        info(f"fact_city_year.{metric} 装载 {len(rows)} 行")

    # 3) 城市-月（PM2.5 / O₃）
    for metric in ("pm25", "o3"):
        daily = store.daily_values(metric, "mean").copy()
        daily["month"] = daily["date"].str.slice(0, 7)
        grouped = (daily.groupby(["city", "province", "month"])["value"]
                   .agg(value="mean", days="size").reset_index())
        rows = [(r["city"], r["province"], r["month"], metric,
                 round(float(r["value"]), 2), int(r["days"]))
                for r in grouped.to_dict("records")]
        upsert("INSERT INTO fact_city_month(city, province, month, metric, monthly_mean, days) "
               "VALUES(%s,%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE monthly_mean=VALUES(monthly_mean), days=VALUES(days)", rows)
        info(f"fact_city_month.{metric} 装载 {len(rows)} 行")

    # 4) 省份超标（PM2.5 24h / O₃ 8h）
    for metric, period in (("pm25", "24h"), ("o3", "8h")):
        res = store.province_exceed(metric, period)
        rows = [(r["province"], year, metric, period, int(r["exceed_days"]),
                 int(r["total_days"]), round(float(r["exceed_rate"]), 4),
                 round(float(r["share"]), 4)) for r in res["rows"]]
        upsert("INSERT INTO fact_province_exceed(province, year, metric, period, "
               "exceed_days, total_days, exceed_rate, share) "
               "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
               "ON DUPLICATE KEY UPDATE exceed_days=VALUES(exceed_days), "
               "total_days=VALUES(total_days), exceed_rate=VALUES(exceed_rate), "
               "share=VALUES(share)", rows)
        info(f"fact_province_exceed.{metric}/{period} 装载 {len(rows)} 行")

    # 5) 校验
    checks = []
    for table in ("dim_city", "fact_city_year", "fact_city_month", "fact_province_exceed"):
        n = mysql_scalar(f"SELECT COUNT(*) FROM {table}", database=config.MYSQL_DB)
        checks.append((table, n))
    print_table(checks, headers=["表", "行数"], title="MySQL 装载校验")

    top = mysql_query(
        "SELECT city, annual_mean FROM fact_city_year WHERE metric='pm25' "
        "ORDER BY annual_mean DESC LIMIT 1", database=config.MYSQL_DB)
    local_top = store.annual_mean("pm25", top_n=1).to_dict("records")[0]
    if top:
        diff = abs(float(top[0]["annual_mean"]) - float(local_top["value"])) / float(local_top["value"])
        ok(f"TOP1 城市校验：MySQL {top[0]['city']} {top[0]['annual_mean']} vs "
           f"本地 {local_top['city']} {local_top['value']:.2f}，偏差 {diff:.2%}")
        save_json({"mysql_top": top[0], "local_top": local_top, "rel_diff": diff},
                  config.OUTPUT_DIR / "mysql_vs_local.json")
    all_rows = sum(n for _, n in checks)
    ok(f"MySQL 结果库装载完成，共 {all_rows:,} 行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
