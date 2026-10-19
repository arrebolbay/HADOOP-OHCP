#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mapreduce/pm25_mapper.py —— Hadoop Streaming Mapper
输入：ODS 分片 CSV（city,province,date,hour,pm25,...）
输出：城市 \t PM2.5小时值
说明：跳过表头与非法值，物理量程 0~1000 之外直接丢弃。
"""
import sys


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("city,"):
            continue
        parts = line.split(",")
        if len(parts) < 5:
            continue
        city, pm25 = parts[0], parts[4]
        if not city:
            continue
        try:
            value = float(pm25)
        except ValueError:
            continue
        if 0 <= value <= 1000:
            print(f"{city}\t{value}")


if __name__ == "__main__":
    main()
