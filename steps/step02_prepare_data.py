#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step02_prepare_data.py —— 第 2 步：真实数据接入 + 按月分片
================================================================================
【输入】
    data/raw/daily/china_cities_YYYYMMDD.csv   （quotsoft 全国城市空气质量日文件，
                                                 原始来源：国家城市空气质量实时发布平台）
    或 data/raw/tianchi/*.csv                  （天池数据集，长表 CSV，见 README）

【处理】
    1) 宽表 -> 长表：一行 = 一个城市一个小时的各项污染物浓度；
    2) 补省份：读取 data/reference/city_province.csv（真实行政区划参考表）；
    3) 生成质量等级：AQI -> 优/良/轻度污染/中度污染/重度污染/严重污染（HJ 633-2012）；
    4) 按月写分片：data/raw/chunks/air_quality_2024-01.csv ...（每月一个文件）。

【为什么要分片？】
    全年 300 多万行，一次性读进内存既慢又浪费；按月分片后，每一步只处理 30 万行左右，
    后续清洗、聚合、MapReduce 都按分片批处理，这就是题目要求的大数据工程体现。

【运行】
    python3 steps/step02_prepare_data.py
    python3 steps/step02_prepare_data.py --limit 31     # 只处理前 31 天（调试用）
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, warn, error, print_table

COLUMN_MAP = {
    "PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "SO₂": "so2",
    "NO2": "no2", "NO₂": "no2", "CO": "co", "O3": "o3", "O₃": "o3", "AQI": "aqi",
}
AQI_BINS = [-1, 50, 100, 150, 200, 300, 500]
AQI_LABELS = ["优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"]

# 数据里少量特殊/兵团城市，行政区划表里没有对应地级市，手工归属（真实行政区划）
CITY_ALIAS = {
    "五家渠": "新疆", "石河子": "新疆", "阿拉尔": "新疆", "图木舒克": "新疆",
    "铁门关": "新疆", "双河": "新疆", "可克达拉": "新疆", "昆玉": "新疆",
    "胡杨河": "新疆", "新星": "新疆", "兰州新区": "甘肃", "雄安新区": "河北",
    "儋州": "海南", "三沙": "海南", "伊犁哈萨克州": "新疆",
    "克孜勒苏柯尔克孜自治州": "新疆", "文山州": "云南", "湘西州": "湖南",
    "红河州": "云南", "西双版纳州": "云南", "西咸新区": "陕西", "赣江新区": "江西",
}
CITY_SUFFIXES = ["哈萨克自治州", "蒙古族藏族自治州", "藏族自治州", "彝族自治州",
                 "苗族自治州", "土家族苗族自治州", "布依族苗族自治州",
                 "傣族景颇族自治州", "白族自治州", "哈尼族彝族自治州",
                 "壮族苗族自治州", "傈僳族自治州", "回族自治州", "蒙古自治州",
                 "自治州", "地区", "林区", "盟", "市", "州"]


def normalize_city(name):
    for suffix in CITY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    return name


def load_province_map():
    """城市 -> 省份；同时建立"去后缀"别名索引，提升匹配率。"""
    if not config.PROVINCE_MAP_CSV.exists():
        warn("没有城市→省份映射表，请先运行 scripts/build_province_map.py")
        return {}
    df = pd.read_csv(config.PROVINCE_MAP_CSV)
    mapping = dict(zip(df["city"], df["province"]))
    for city, province in list(mapping.items()):
        mapping.setdefault(normalize_city(city), province)
    mapping.update(CITY_ALIAS)
    return mapping


def add_quality(df):
    """AQI -> 质量等级（向量化，比逐行调用快几十倍）。"""
    aqi = pd.to_numeric(df["aqi"], errors="coerce")
    df["quality"] = pd.cut(aqi, bins=AQI_BINS, labels=AQI_LABELS).astype("string")
    df.loc[aqi > 500, "quality"] = "严重污染"
    return df


def wide_day_to_long(path, province_map):
    """把一个日文件（date,hour,type,城市A,城市B...）转成长表。"""
    raw = pd.read_csv(path, dtype=str)
    raw = raw[raw["type"].isin(config.RAW_TYPES)].copy()
    if raw.empty:
        return None, []
    long = raw.melt(id_vars=["date", "hour", "type"], var_name="city", value_name="value")
    wide = long.pivot_table(index=["date", "hour", "city"], columns="type",
                            values="value", aggfunc="first").reset_index()
    wide = wide.rename(columns=COLUMN_MAP)

    for col in config.POLLUTANTS:
        wide[col] = pd.to_numeric(wide.get(col), errors="coerce")
    wide["date"] = pd.to_datetime(wide["date"].astype(str), format="%Y%m%d",
                                  errors="coerce").dt.strftime("%Y-%m-%d")
    wide = wide.dropna(subset=["date"])
    wide["hour"] = pd.to_numeric(wide["hour"], errors="coerce").fillna(0).astype("int16")

    matched = wide["city"].map(province_map)
    if matched.isna().any():
        fallback = wide.loc[matched.isna(), "city"].map(
            lambda c: province_map.get(normalize_city(c)))
        matched = matched.fillna(fallback)
    wide["province"] = matched.fillna("其他")
    unmatched = sorted(wide.loc[matched.isna(), "city"].unique().tolist())
    wide = add_quality(wide)
    cols = ["city", "province", "date", "hour"] + list(config.POLLUTANTS) + ["quality"]
    return wide[cols], unmatched


def load_tianchi_long(tianchi_dir, province_map):
    """天池数据集适配：长表 CSV（支持中英文列名）规范化为标准长表。"""
    frames = []
    for path in sorted(Path(tianchi_dir).glob("*.csv")):
        df = pd.read_csv(path, dtype=str)
        df = df.rename(columns={"城市": "city", "省份": "province", "日期": "date",
                                "时间": "hour", "质量等级": "quality", **COLUMN_MAP})
        if not {"city", "date"} <= set(df.columns):
            warn(f"跳过热池文件（缺少城市/日期列）：{path.name}")
            continue
        if "hour" not in df.columns:
            df["hour"] = 0
        df["province"] = df["province"].fillna(df["city"].map(province_map)).fillna("其他")
        for col in config.POLLUTANTS:
            df[col] = pd.to_numeric(df.get(col), errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = add_quality(df)
        frames.append(df[["city", "province", "date", "hour"] +
                         list(config.POLLUTANTS) + ["quality"]])
    return pd.concat(frames, ignore_index=True) if frames else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 天（调试用）")
    args = parser.parse_args()

    banner("第 2 步：真实数据接入 + 按月分片")
    province_map = load_province_map()
    info(f"城市→省份映射：{len(province_map)} 个城市")

    daily_files = sorted(config.RAW_DAILY_DIR.glob("china_cities_*.csv"))
    tianchi_dir = config.DATA_DIR / "raw" / "tianchi"
    if not daily_files and tianchi_dir.exists():
        info("未发现日文件，改用天池数据集适配模式")
        df = load_tianchi_long(tianchi_dir, province_map)
        if df is None or df.empty:
            error("天池目录里没有可用 CSV")
            return 1
        df["month"] = df["date"].str.slice(0, 7)
        for month, part in df.groupby("month"):
            out = config.RAW_CHUNK_DIR / f"air_quality_{month}.csv"
            part.to_csv(out, index=False)
            info(f"写出 {out.name}：{len(part)} 行")
        ok("天池数据接入完成")
        return 0

    if not daily_files:
        error("没有原始数据。请先运行 scripts/download_real_data.py，"
              "或把天池 CSV 放到 data/raw/tianchi/")
        return 1
    if args.limit:
        daily_files = daily_files[: args.limit]
        warn(f"调试模式：只处理前 {len(daily_files)} 天")

    config.RAW_CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    unmatched_all, total_rows = set(), 0
    written = []
    current_month, buffer = None, []

    def flush(month, parts):
        """按月落盘，避免把全年 300 万行同时留在内存。"""
        if not parts:
            return
        out = config.RAW_CHUNK_DIR / f"air_quality_{month}.csv"
        part = pd.concat(parts, ignore_index=True)
        part.to_csv(out, index=False)
        written.append((out.name, len(part), round(out.stat().st_size / 1024 / 1024, 1)))
        buffer.clear()

    for i, path in enumerate(daily_files, 1):
        long, unmatched = wide_day_to_long(path, province_map)
        unmatched_all.update(unmatched)
        if long is None or long.empty:
            continue
        month = long["date"].iloc[0][:7]
        if current_month is not None and month != current_month:
            flush(current_month, buffer)
        current_month = month
        buffer.append(long)
        total_rows += len(long)
        if i % 20 == 0 or i == len(daily_files):
            info(f"已处理 {i}/{len(daily_files)} 天，累计 {total_rows} 行")
    flush(current_month, buffer)

    ok(f"写出 {len(written)} 个月分片，共 {total_rows} 行")

    print_table(written, headers=["分片", "行数", "大小(MB)"], max_rows=15, title="分片清单")
    if unmatched_all:
        warn(f"有 {len(unmatched_all)} 个城市未匹配到省份（计入'其他'）："
             f"{', '.join(sorted(unmatched_all)[:10])}{' ...' if len(unmatched_all) > 10 else ''}")

    report = {
        "source": config.DATASET_SOURCE,
        "days": len(daily_files),
        "rows": total_rows,
        "chunks": len(written),
        "unmatched_cities": sorted(unmatched_all),
    }
    (config.OUTPUT_DIR / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    info("数据概况：" + json.dumps(report, ensure_ascii=False)[:200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
