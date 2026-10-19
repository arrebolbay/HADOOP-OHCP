# -*- coding: utf-8 -*-
"""tests/test_data_store.py —— 分片聚合 / 日均口径 / 省份占比 / 突变检测。"""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from core.data_store import DataStore

FIXTURE = config.FIXTURE_DIR


class DataStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DataStore(chunk_dir=FIXTURE)
        cls.raw = pd.read_csv(FIXTURE / "air_quality_2024-01.csv")

    def test_stats(self):
        stats = self.store.stats(refresh=True)
        self.assertTrue(stats["available"])
        self.assertEqual(stats["rows"], len(self.raw))
        self.assertEqual(stats["cities"], 4)

    def test_annual_mean_matches_independent_calc(self):
        result = self.store.annual_mean("pm25")
        daily = (self.raw.groupby(["city", "date"])["pm25"].mean()
                 .groupby("city").mean())
        top = result.iloc[0]
        self.assertEqual(top["city"], daily.idxmax())
        self.assertAlmostEqual(top["value"], daily.max(), places=3)

    def test_monthly_series(self):
        wide = self.store.monthly_series(["北京", "上海"], "pm25")
        self.assertEqual(list(wide.index), ["2024-01"])
        self.assertEqual(set(wide.columns), {"北京", "上海"})

    def test_province_exceed_counts(self):
        res = self.store.province_exceed("pm25", "24h")
        self.assertEqual(res["total_city_days"], len(self.raw) // 24)
        daily = self.raw.groupby(["province", "city", "date"])["pm25"].mean().reset_index()
        expected = int((daily["pm25"] > 75).sum())
        self.assertEqual(res["total_exceed_days"], expected)

    def test_city_season_exceed(self):
        res = self.store.city_season_exceed("北京", "pm25", "冬季")
        self.assertEqual(res["city"], "北京")
        self.assertEqual(res["period"], "24h")
        self.assertEqual(res["total_days"], 3)
        self.assertGreaterEqual(res["exceed_days"], 0)

    def test_o3_max8h_uses_8h_period(self):
        res = self.store.city_season_exceed("北京", "o3", None)
        self.assertEqual(res["period"], "8h")
        self.assertEqual(res["limit"], 160.0)

    def test_detect_jumps_returns_monthly(self):
        res = self.store.detect_jumps("北京", "pm25")
        self.assertIn("2024-01", res["monthly"])
        self.assertIsInstance(res["jumps"], list)


if __name__ == "__main__":
    unittest.main()
