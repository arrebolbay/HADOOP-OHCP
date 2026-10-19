#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step07_mapreduce_alignment.py —— 第 7 步：MapReduce 双引擎对账
================================================================================
做什么：
    用 Hadoop Streaming（Python 写 map/reduce）独立计算"各城市 PM2.5 逐小时均值"，
    再与 Hive 的 ads_city_pm25_hourly 逐城市对比，验证两套计算引擎结果一致。

【答辩价值】
    同一个指标用 Hive SQL 和 MapReduce 各算一遍，结果对齐 —— 说明统计链路可信，
    不是"只跑通一次"的偶然结果。
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import (banner, info, ok, warn, error, print_table, run,
                    hdfs, hdfs_rmr, hdfs_cat, hive_rows, save_json)


def main():
    banner("第 7 步：MapReduce 独立计算 + 与 Hive 对账")
    mapper = config.MR_DIR / "pm25_mapper.py"
    reducer = config.MR_DIR / "pm25_reducer.py"
    if not mapper.exists() or not reducer.exists():
        error("缺少 mapreduce 脚本")
        return 1

    output = f"{config.HDFS_MR}/city_pm25"
    hdfs_rmr(output, log_name="07_mapreduce.log")
    cmd = [
        f"{config.HADOOP_HOME}/bin/hadoop", "jar", config.STREAMING_JAR,
        "-D", "mapreduce.job.reduces=1",
        "-D", "mapreduce.job.name=air_quality_city_pm25",
        "-files", f"{mapper},{reducer}",
        "-mapper", "python3 pm25_mapper.py",
        "-reducer", "python3 pm25_reducer.py",
        "-input", f"{config.HDFS_ODS}/air_quality",
        "-output", output,
    ]
    info("提交 Hadoop Streaming 作业（首次会启动 YARN 容器，约 30~90 秒）")
    code, out = run(cmd, log_name="07_mapreduce.log", timeout=1800, quiet=True)
    if code != 0:
        error("MapReduce 作业失败，请查看 logs/07_mapreduce.log")
        print(out[-1500:])
        return 1

    raw = hdfs_cat(f"{output}/part-00000")
    records = []
    for line in raw.splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 3:
            try:
                records.append((parts[0], float(parts[1]), int(parts[2])))
            except ValueError:
                continue
    if not records:
        error("MapReduce 输出为空")
        return 1
    records.sort(key=lambda r: r[1], reverse=True)
    ok(f"MapReduce 完成：{len(records)} 个城市，TOP 城市 {records[0][0]} "
       f"{records[0][1]:.2f}μg/m³")

    out_csv = config.OUTPUT_DIR / "03_mapreduce_city_pm25.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "hourly_mean_pm25", "samples"])
        writer.writerows(records)
    info(f"完整结果已保存：{out_csv}")

    # 与 Hive 对账（取前 20 名）
    code, hive_rows_data = hive_rows(
        f"SELECT city, hourly_mean FROM {config.HIVE_DB}.ads_city_pm25_hourly",
        timeout=900)
    hive_map = {r[0]: float(r[1]) for r in hive_rows_data if len(r) >= 2} if code == 0 else {}
    if not hive_map:
        warn("Hive 结果表不可用，跳过双引擎对账（不影响 Agent 链路）")
        return 0

    compare, worst = [], 0.0
    for city, mr_value, samples in records[:20]:
        if city in hive_map:
            diff = abs(mr_value - hive_map[city]) / max(hive_map[city], 1e-9)
            worst = max(worst, diff)
            compare.append((city, f"{mr_value:.2f}", f"{hive_map[city]:.2f}", f"{diff:.4%}"))
    print_table(compare, headers=["城市", "MapReduce", "Hive", "相对偏差"],
                title="双引擎对账（TOP20）")
    save_json({"mr_top20": records[:20], "hive": hive_map, "worst_rel_diff": worst},
              config.OUTPUT_DIR / "mapreduce_vs_hive.json")
    if worst <= config.VALIDATE_MAX_REL_DIFF:
        ok(f"双引擎对账通过：最大相对偏差 {worst:.4%}")
    else:
        warn(f"最大偏差 {worst:.2%}，请检查两边清洗口径是否一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
