#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mapreduce/pm25_reducer.py —— Hadoop Streaming Reducer
输入：城市 \t PM2.5小时值（已按城市分组）
输出：城市 \t 小时均值 \t 有效样本数
用途：与 Hive 的 ads_city_pm25_hourly 做双引擎对账。
"""
import sys


def main():
    current, total, count = None, 0.0, 0

    def emit(city, total, count):
        if city is not None and count:
            print(f"{city}\t{total / count:.2f}\t{count}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            city, raw = line.split("\t")
            value = float(raw)
        except ValueError:
            continue
        if city != current:
            emit(current, total, count)
            current, total, count = city, 0.0, 0
        total += value
        count += 1
    emit(current, total, count)


if __name__ == "__main__":
    main()
