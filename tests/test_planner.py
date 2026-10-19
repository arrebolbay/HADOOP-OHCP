# -*- coding: utf-8 -*-
"""tests/test_planner.py —— 规则规划器的意图解析与多轮记忆。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.memory import Memory
from agent.planner import RulePlanner


class PlannerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.planner = RulePlanner()

    def test_example1_top5_with_monthly_line(self):
        plan = self.planner.plan("找出2024年PM2.5年均浓度最高的5个城市，画出月度变化曲线")
        self.assertEqual(plan["slots"]["metric"], "pm25")
        self.assertEqual(plan["slots"]["top_n"], 5)
        self.assertEqual(plan["slots"]["year"], 2024)
        tools = [s["tool"] for s in plan["steps"]]
        self.assertEqual(tools[0], "dataset_read")
        self.assertEqual(tools[1], "clean_data")
        self.assertIn("gb3095_judge", tools)
        self.assertIn("validate_result", tools)
        self.assertEqual(tools[-1], "build_report")
        charts = [s for s in plan["steps"] if s["tool"] == "draw_chart"]
        self.assertEqual(charts[0]["args"]["chart_type"], "line")

    def test_example2_province_share_pie(self):
        plan = self.planner.plan("筛选PM2.5超标记录，统计各省份超标天数占比")
        self.assertEqual(plan["slots"]["analysis"], "province_exceed")
        charts = [s for s in plan["steps"] if s["tool"] == "draw_chart"]
        self.assertEqual(charts[0]["args"]["chart_type"], "pie")

    def test_example3_beijing_summer_o3(self):
        plan = self.planner.plan("统计北京市夏季臭氧O₃超标总天数")
        self.assertEqual(plan["slots"]["metric"], "o3")
        self.assertEqual(plan["slots"]["season"], "夏季")
        self.assertEqual(plan["slots"]["cities"], ["北京"])
        self.assertEqual(plan["slots"]["analysis"], "city_season_exceed")
        aggregate = [s for s in plan["steps"] if s["tool"] == "aggregate"][0]
        self.assertEqual(aggregate["args"]["city"], "北京")

    def test_memory_follow_up(self):
        memory = Memory()
        memory.add("找出2024年PM2.5年均浓度最高的5个城市", {
            "slots": {"metric": "pm25", "year": 2024,
                      "cities": ["商丘", "菏泽", "聊城", "济宁", "保定"]}})
        plan = self.planner.plan("再看这几个城市的PM10超标情况", memory)
        self.assertEqual(plan["slots"]["metric"], "pm10")
        self.assertEqual(plan["slots"]["cities"],
                         ["商丘", "菏泽", "聊城", "济宁", "保定"])

    def test_alert_intent(self):
        plan = self.planner.plan("检测北京市PM2.5异常突变，标记污染突发时段")
        self.assertIn("detect_alert", [s["tool"] for s in plan["steps"]])

    def test_pro_template(self):
        plan = self.planner.plan("统计北京市冬季PM2.5超标天数（专业版）")
        report = [s for s in plan["steps"] if s["tool"] == "build_report"][0]
        self.assertEqual(report["args"]["template"], "pro")


if __name__ == "__main__":
    unittest.main()
