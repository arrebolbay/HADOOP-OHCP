#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/build_province_map.py —— 生成"城市 -> 省份"参考映射表
================================================================================
数据来源：民政部行政区划（GitHub modood/Administrative-divisions-of-China 镜像）
输出：data/reference/city_province.csv（city,province）

【为什么需要？】
    监测数据只给城市名，题目要求"统计各省份超标天数占比"，
    所以需要一张真实的行政区划参考表（这是参考数据，不是模拟监测数据）。

【用法】
    python3 scripts/build_province_map.py
    （赛前运行一次即可，结果随项目提交；现场无需联网）
"""

import csv
import json
import re
import sys
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_CSV = PROJECT_DIR / "data" / "reference" / "city_province.csv"
CACHE_JSON = PROJECT_DIR / "data" / "reference" / "pcas-code.json"

MIRRORS = [
    "https://unpkg.com/china-division@2.7.0/dist/pcas-code.json",
    "https://ghproxy.net/https://raw.githubusercontent.com/modood/"
    "Administrative-divisions-of-China/master/dist/pcas-code.json",
]

# 直辖市：数据里直接用简称
MUNICIPALITIES = {"北京", "天津", "上海", "重庆"}

# 省级名称规范化：去掉"省/市/自治区/壮族自治区..."后缀
PROVINCE_ALIAS = {
    "内蒙古自治区": "内蒙古",
    "广西壮族自治区": "广西",
    "西藏自治区": "西藏",
    "宁夏回族自治区": "宁夏",
    "新疆维吾尔自治区": "新疆",
    "香港特别行政区": "香港",
    "澳门特别行政区": "澳门",
}

# 城市名后缀，按长度从长到短剥离
CITY_SUFFIXES = [
    "哈萨克自治州", "蒙古族藏族自治州", "藏族自治州", "彝族自治州", "苗族自治州",
    "土家族苗族自治州", "布依族苗族自治州", "傣族景颇族自治州", "白族自治州",
    "哈尼族彝族自治州", "壮族苗族自治州", "傈僳族自治州", "回族自治州",
    "柯尔克孜自治州", "蒙古自治州", "自治州", "地区", "林区", "盟", "市",
]


def normalize_province(name: str) -> str:
    if name in PROVINCE_ALIAS:
        return PROVINCE_ALIAS[name]
    return re.sub(r"(省|市|自治区|特别行政区)$", "", name)


def normalize_city(name: str) -> str:
    """把"石家庄市"变成"石家庄"；"北京市"保留"北京"；不改变专名本身。"""
    for suffix in CITY_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def load_source() -> list:
    if CACHE_JSON.exists():
        return json.loads(CACHE_JSON.read_text(encoding="utf-8"))
    last_exc = None
    for url in MIRRORS:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
            CACHE_JSON.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data
        except Exception as exc:  # noqa: BLE001 - 镜像依次尝试
            last_exc = exc
    raise RuntimeError(f"行政区划数据下载失败：{last_exc}")


def build_rows(data: list) -> list:
    rows = {}
    for province in data:
        p_name = normalize_province(province.get("name", ""))
        for city in province.get("children", []) or []:
            c_raw = city.get("name", "")
            if not c_raw or c_raw in {"市辖区", "县", "省直辖县级行政区划", "自治区直辖县级行政区划"}:
                continue
            c_name = normalize_city(c_raw)
            if not c_name:
                continue
            rows.setdefault(c_name, p_name)
    # 直辖市补全（数据里可能只有"市辖区"，没有"北京"这一层）
    for name in MUNICIPALITIES:
        rows.setdefault(name, name)
    return sorted(rows.items())


def main() -> int:
    data = load_source()
    rows = build_rows(data)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["city", "province"])
        writer.writerows(rows)
    print(f"已生成 {OUT_CSV}，共 {len(rows)} 个城市")
    return 0


if __name__ == "__main__":
    sys.exit(main())
