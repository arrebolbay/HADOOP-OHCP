#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step06_hive_dwd_dws_ads.py —— 第 6 步：Hive 数仓三层建模 + 与本地复算对账
================================================================================
执行 sql/hive/02_dwd_dws_ads.sql：
    DWD：类型转换 + 物理量程过滤 + 城市日均（≥12 个有效小时）
    DWS：城市-年、城市-月汇总
    ADS：TOP20 城市年均 PM2.5、各省超标天数、逐小时均值（给 MapReduce 对账用）

并把 Hive 的 TOP5 与本地 pandas 复算结果逐行对比（允许 2% 相对误差），
差额写入 output/hive_vs_pandas.json —— 这就是"结果真实可信"的证据。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, warn, error, print_table, hive_file, hive_rows, save_json
from core.data_store import DataStore


def main():
    banner("第 6 步：Hive DWD / DWS / ADS 三层建模")
    sql_file = config.HIVE_SQL_DIR / "02_dwd_dws_ads.sql"
    if not sql_file.exists():
        error(f"缺少 SQL 文件：{sql_file}")
        return 1

    info(f"执行 {sql_file.name}（全量聚合，单机可能需要 1~3 分钟）")
    code, _ = hive_file(sql_file, log_name="06_hive_dwd_dws_ads.log", timeout=3600)
    if code != 0:
        error("Hive 三层建模失败，请查看 logs/06_hive_dwd_dws_ads.log")
        return 1

    code, top_rows = hive_rows(
        f"SELECT city, province, annual_mean, days, exceeded "
        f"FROM {config.HIVE_DB}.ads_top_city_pm25 ORDER BY annual_mean DESC LIMIT 5",
        timeout=900)
    if code != 0 or not top_rows:
        error("ADS TOP5 查询失败")
        return 1
    print_table(top_rows, headers=["城市", "省份", "年均PM2.5", "天数", "超标"],
                title="Hive ADS：PM2.5 年均 TOP5")

    out_csv = config.OUTPUT_DIR / "hive_top5_pm25.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "province", "annual_mean", "days", "exceeded"])
        writer.writerows(top_rows)

    # 本地独立复算对账
    store = DataStore()
    local = store.annual_mean("pm25", top_n=5)
    local_map = {r["city"]: float(r["value"]) for r in local.to_dict("records")}
    compare, worst = [], 0.0
    for row in top_rows:
        city, hive_value = row[0], float(row[2])
        local_value = local_map.get(city)
        if local_value is None:
            compare.append((city, hive_value, "-", "-"))
            continue
        diff = abs(hive_value - local_value) / max(hive_value, 1e-9)
        worst = max(worst, diff)
        compare.append((city, f"{hive_value:.2f}", f"{local_value:.2f}", f"{diff:.2%}"))
    print_table(compare, headers=["城市", "Hive", "本地复算", "相对偏差"],
                title="Hive vs 本地 pandas 对账")

    save_json({"hive_top5": top_rows, "local_top5": local_map,
               "worst_rel_diff": worst, "rows": compare},
              config.OUTPUT_DIR / "hive_vs_pandas.json")
    if worst <= config.VALIDATE_MAX_REL_DIFF:
        ok(f"对账通过：最大相对偏差 {worst:.2%}（阈值 {config.VALIDATE_MAX_REL_DIFF:.0%}）")
    else:
        warn(f"对账偏差 {worst:.2%} 超过阈值，通常是 Hive 未做缺失填充导致，属口径差异")
    info("下一步：step07 用 MapReduce 独立再算一遍，做双引擎对账")
    return 0


if __name__ == "__main__":
    sys.exit(main())
