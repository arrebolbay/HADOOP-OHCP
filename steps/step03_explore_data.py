#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step03_explore_data.py —— 第 3 步：数据质量探查 + 清洗
================================================================================
做什么：
    1) 统计分片规模、城市/省份覆盖、时间范围；
    2) 统计各污染物缺失率、物理越界值、重复记录；
    3) 抽样看数据分布（AQI 等级占比、PM2.5 最高的城市）；
    4) 调用 core.cleaning 执行清洗，输出清洗报告；
    5) 生成 output/01_数据质量探查报告.txt。

【答辩要点】
    这一份报告就是"数据清洗真实做了"的证据：清洗前后行数、异常值、填充量都有据可查。
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, print_table
from core.data_store import DataStore
from core.cleaning import clean_all


def main():
    banner("第 3 步：数据质量探查 + 清洗")
    store = DataStore(chunk_dir=config.RAW_CHUNK_DIR)
    if not store.available():
        print("没有原始分片，请先运行 step02_prepare_data.py")
        return 1

    stats = store.stats(refresh=True)
    info(f"分片 {stats['chunks']} 个，{stats['rows']:,} 行，"
         f"{stats['cities']} 城市 / {stats['provinces']} 省份，"
         f"{stats['date_min']} ~ {stats['date_max']}")

    rows = [(m, config.POLLUTANTS[m]["cn"], f"{stats['missing_ratio'][m]:.3%}")
            for m in config.POLLUTANTS]
    print_table(rows, headers=["字段", "指标", "缺失率"], title="缺失率")

    # 抽样统计 AQI 等级与高浓度城市（只读一个月，演示分片读取）
    first = store.chunk_files()[0]
    df = pd.read_csv(first, usecols=["city", "province", "pm25", "aqi", "quality"])
    quality_counts = df["quality"].value_counts().to_dict()
    top_cities = (df.groupby("city")["pm25"].mean().sort_values(ascending=False)
                  .head(8).round(1).to_dict())
    print_table([(k, v) for k, v in quality_counts.items()],
                headers=["质量等级", "记录数"], title=f"{first.name} 质量等级分布")
    print_table([(k, v) for k, v in top_cities.items()],
                headers=["城市", "PM2.5均值(μg/m³)"], title=f"{first.name} PM2.5 均值 TOP8")

    info("开始清洗（物理范围 + 3×IQR 截断 + 同城市中位数填充 + 去重）...")
    report = clean_all()
    ok(f"清洗完成：{report['rows_in']:,} → {report['rows_out']:,} 行")

    lines = [
        "空气质量数据质量探查报告",
        "=" * 60,
        f"数据源：{config.DATASET_SOURCE}",
        f"时间范围：{stats['date_min']} ~ {stats['date_max']}",
        f"规模：{stats['rows']:,} 行 / {stats['chunks']} 个分片 / {stats['size_mb']} MB",
        f"覆盖：{stats['cities']} 城市 / {stats['provinces']} 省级行政区",
        "",
        "一、缺失率",
        *[f"  {config.POLLUTANTS[m]['cn']}: {stats['missing_ratio'][m]:.3%}"
          for m in config.POLLUTANTS],
        "",
        "二、清洗统计（core/cleaning.py）",
        f"  物理越界值：{report['out_of_range']:,}",
        f"  3×IQR 截断：{report['iqr_clipped']:,}",
        f"  中位数填充：{report['filled']:,}",
        f"  重复记录：{report['duplicates']:,}",
        f"  全空行剔除：{report['dropped_all_missing']:,}",
        f"  清洗后行数：{report['rows_out']:,}",
        "",
        "三、抽样分布",
        *[f"  {k}: {v}" for k, v in quality_counts.items()],
        "",
        "四、PM2.5 均值 TOP8（首个分片）",
        *[f"  {k}: {v}" for k, v in top_cities.items()],
        "",
        "结论：真实监测数据存在缺失与异常，清洗后进入 DWD 层；",
        "      清洗方法、数量、前后行数均可复核。",
    ]
    out = config.OUTPUT_DIR / "01_数据质量探查报告.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    ok(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
