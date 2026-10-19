# -*- coding: utf-8 -*-
"""
core/cleaning.py —— 数据清洗（DWD 层的 Python 实现）
================================================================================
清洗五步（每一步都计数，供报告与答辩展示）：
    1) 类型转换：把文本列转成数值，转不了的记为缺失；
    2) 物理范围校验：超出监测设备合理量程的值判为异常（置空）；
    3) IQR 异常识别：按城市计算 Q1/Q3，超出 [Q1-1.5IQR, Q3+1.5IQR] 的值截断；
    4) 缺失值填充：用同城市同月份的指标中位数填充（比全局均值更贴合季节规律）；
    5) 全空行剔除 + 重复记录去重，并按 AQI 重新生成空气质量等级。

为什么按"月"处理？
    每个分片约 30 万行，内存友好；同时"同城市同月份"的中位数正好只需要本分片数据，
    不需要把全年数据读进内存 —— 这就是"分片批处理"的实际价值。
"""

import json
from pathlib import Path

import pandas as pd

import config
from core.data_store import DTYPES, NUMERIC_COLS
from core import gb3095


def clean_chunk(df):
    """清洗单个分片，返回 (清洗后的 DataFrame, 统计 dict)。"""
    stats = {"rows_in": len(df), "duplicates": 0, "dropped_all_missing": 0,
             "out_of_range": 0, "iqr_clipped": 0, "filled": 0,
             "filled_by_col": {c: 0 for c in NUMERIC_COLS}}

    df = df.copy()
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 物理范围校验：超量程 -> NaN
    for col, (low, high) in config.PHYSICAL_RANGES.items():
        bad = (df[col] < low) | (df[col] > high)
        stats["out_of_range"] += int(bad.sum())
        df.loc[bad, col] = pd.NA

    # IQR 截断（按城市，3×IQR：只压制极端离群值，保留真实的昼夜/季节波动）
    for col in NUMERIC_COLS:
        q1_map = df.groupby("city")[col].quantile(0.25)
        q3_map = df.groupby("city")[col].quantile(0.75)
        iqr_map = q3_map - q1_map
        low_map = (q1_map - 3.0 * iqr_map).clip(lower=config.PHYSICAL_RANGES[col][0])
        high_map = (q3_map + 3.0 * iqr_map).clip(upper=config.PHYSICAL_RANGES[col][1])
        low = df["city"].map(low_map)
        high = df["city"].map(high_map)
        clipped = (df[col] < low) | (df[col] > high)
        stats["iqr_clipped"] += int(clipped.sum())
        df[col] = df[col].clip(lower=low, upper=high)

    # 全空记录先剔除（避免用中位数"复活"一条本来就不存在的观测）
    all_missing = df[NUMERIC_COLS].isna().all(axis=1)
    stats["dropped_all_missing"] = int(all_missing.sum())
    df = df[~all_missing]

    # 同城市中位数填充（本分片内，避免跨月信息泄露）
    for col in NUMERIC_COLS:
        miss = df[col].isna()
        if miss.any():
            med_map = df.groupby("city")[col].median()
            fill_values = df["city"].map(med_map)
            fill_mask = miss & fill_values.notna()
            stats["filled"] += int(fill_mask.sum())
            stats["filled_by_col"][col] = int(fill_mask.sum())
            df[col] = df[col].fillna(fill_values)

    # 去重
    before = len(df)
    df = df.drop_duplicates(subset=["city", "date", "hour"], keep="last")
    stats["duplicates"] = before - len(df)

    # AQI -> 质量等级（统一口径，避免原始等级缺失）
    df["quality"] = [gb3095.quality_level(v)["level"] for v in df["aqi"]]
    stats["rows_out"] = len(df)
    return df, stats


def clean_all(raw_dir=None, out_dir=None, year=None):
    """把 raw 分片清洗后写入 cache/cleaned，返回汇总报告。"""
    raw_dir = Path(raw_dir or config.RAW_CHUNK_DIR)
    out_dir = Path(out_dir or config.CLEAN_CHUNK_DIR)
    year = int(year or config.DATASET_YEAR)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob(f"air_quality_{year}-*.csv"))
    if not files:
        raise FileNotFoundError(f"找不到原始分片：{raw_dir}（先运行 step02）")

    total = {"rows_in": 0, "rows_out": 0, "duplicates": 0,
             "dropped_all_missing": 0, "out_of_range": 0, "iqr_clipped": 0,
             "filled": 0, "chunks": 0,
             "filled_by_col": {c: 0 for c in NUMERIC_COLS}}
    for path in files:
        df = pd.read_csv(path, dtype=DTYPES)
        cleaned, stats = clean_chunk(df)
        cleaned.to_csv(out_dir / path.name, index=False)
        total["chunks"] += 1
        for key in ("rows_in", "rows_out", "duplicates", "dropped_all_missing",
                    "out_of_range", "iqr_clipped", "filled"):
            total[key] += stats[key]
        for col, n in stats["filled_by_col"].items():
            total["filled_by_col"][col] += n

    report = {
        "year": year,
        "chunks": total["chunks"],
        "rows_in": total["rows_in"],
        "rows_out": total["rows_out"],
        "duplicates": total["duplicates"],
        "dropped_all_missing": total["dropped_all_missing"],
        "out_of_range": total["out_of_range"],
        "iqr_clipped": total["iqr_clipped"],
        "filled": total["filled"],
        "filled_by_col": total["filled_by_col"],
        "missing_ratio_before": (total["filled"] / (total["rows_in"] * len(NUMERIC_COLS))
                                 if total["rows_in"] else 0),
        "method": "物理范围校验 + 城市 IQR 截断 + 同城市中位数填充 + 去重",
        "output_dir": str(out_dir),
    }
    report_path = config.OUTPUT_DIR / "cleaning_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return report
