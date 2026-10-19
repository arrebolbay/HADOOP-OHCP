# -*- coding: utf-8 -*-
"""tests/test_gb3095.py —— 国标判定边界与空气质量分级。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import gb3095


class GB3095Test(unittest.TestCase):
    def test_pm25_annual_boundary(self):
        # "超过"限值才算超标：等于 35 达标，35.01 超标
        self.assertFalse(gb3095.judge(35.0, "pm25", "annual")["exceeded"])
        self.assertTrue(gb3095.judge(35.01, "pm25", "annual")["exceeded"])

    def test_pm25_daily_boundary(self):
        self.assertFalse(gb3095.judge(75.0, "pm25", "24h")["exceeded"])
        self.assertTrue(gb3095.judge(75.1, "pm25", "24h")["exceeded"])

    def test_limits_of_all_pollutants(self):
        expected = {
            ("pm25", "annual"): 35, ("pm10", "annual"): 70,
            ("so2", "annual"): 60, ("no2", "annual"): 40,
            ("co", "24h"): 4, ("o3", "8h"): 160,
        }
        for (metric, period), value in expected.items():
            self.assertEqual(gb3095.limit_of(metric, period), value)

    def test_o3_daily_max_8h(self):
        self.assertIsNone(gb3095.limit_of("o3", "24h"))
        self.assertEqual(gb3095.choose_period("o3"), "8h")
        self.assertTrue(gb3095.judge(160.5, "o3", "8h")["exceeded"])

    def test_quality_levels(self):
        self.assertEqual(gb3095.quality_level(50)["level"], "优")
        self.assertEqual(gb3095.quality_level(51)["level"], "良")
        self.assertEqual(gb3095.quality_level(201)["level"], "重度污染")
        self.assertEqual(gb3095.quality_level(500)["level"], "严重污染")

    def test_standard_brief_mentions_gb(self):
        text = gb3095.standard_brief("pm25", "annual")
        self.assertIn("GB 3095", text)
        self.assertIn("35", text)

    def test_eco_tip_is_short(self):
        self.assertLessEqual(len(gb3095.eco_tip(True)), 120)
        self.assertIn("绿水青山", gb3095.eco_tip(True))


if __name__ == "__main__":
    unittest.main()
