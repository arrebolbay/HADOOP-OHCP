# -*- coding: utf-8 -*-
"""tests/test_cleaning.py —— 缺失值 / 异常值清洗单元测试。"""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cleaning import clean_chunk


def make_df():
    rows = []
    for hour in range(3):
        rows.append({"city": "北京", "province": "北京", "date": "2024-01-01",
                     "hour": hour, "pm25": 40.0, "pm10": 80.0, "so2": 10.0,
                     "no2": 30.0, "co": 0.8, "o3": 50.0, "aqi": 60, "quality": "良"})
    # 缺失值
    rows.append({"city": "北京", "province": "北京", "date": "2024-01-01",
                 "hour": 3, "pm25": None, "pm10": 85.0, "so2": 11.0,
                 "no2": 31.0, "co": 0.9, "o3": 52.0, "aqi": 62, "quality": "良"})
    # 物理越界
    rows.append({"city": "北京", "province": "北京", "date": "2024-01-01",
                 "hour": 4, "pm25": 9999, "pm10": 90.0, "so2": 12.0,
                 "no2": 32.0, "co": 1.0, "o3": 55.0, "aqi": 65, "quality": "良"})
    # 重复记录
    rows.append({"city": "北京", "province": "北京", "date": "2024-01-01",
                 "hour": 0, "pm25": 41.0, "pm10": 81.0, "so2": 10.0,
                 "no2": 30.0, "co": 0.8, "o3": 50.0, "aqi": 61, "quality": "良"})
    # 全空行
    rows.append({"city": "北京", "province": "北京", "date": "2024-01-01",
                 "hour": 5, "pm25": None, "pm10": None, "so2": None,
                 "no2": None, "co": None, "o3": None, "aqi": None, "quality": None})
    return pd.DataFrame(rows)


class CleaningTest(unittest.TestCase):
    def test_clean_removes_duplicates_and_empty_rows(self):
        cleaned, stats = clean_chunk(make_df())
        self.assertEqual(stats["duplicates"], 1)
        self.assertEqual(stats["dropped_all_missing"], 1)
        self.assertLess(len(cleaned), len(make_df()))

    def test_out_of_range_and_fill(self):
        _, stats = clean_chunk(make_df())
        self.assertGreaterEqual(stats["out_of_range"], 1)
        self.assertGreaterEqual(stats["filled"], 1)

    def test_no_negative_or_huge_values(self):
        cleaned, _ = clean_chunk(make_df())
        self.assertTrue((cleaned["pm25"].dropna() >= 0).all())
        self.assertTrue((cleaned["pm25"].dropna() <= 1000).all())

    def test_quality_generated(self):
        cleaned, _ = clean_chunk(make_df())
        self.assertTrue(cleaned["quality"].notna().all())
        self.assertTrue(set(cleaned["quality"]).issubset(
            {"优", "良", "轻度污染", "中度污染", "重度污染", "严重污染"}))


if __name__ == "__main__":
    unittest.main()
