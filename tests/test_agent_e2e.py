# -*- coding: utf-8 -*-
"""tests/test_agent_e2e.py —— 工具链端到端集成测试（fixture 真实数据子集）。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from agent import AirQualityAgent
from core.data_store import DataStore


class FixturePlanner:
    """固定计划：不依赖大模型，专测工具链串联。"""

    def plan(self, question, memory=None):
        return {
            "planner": "test", "intent": "e2e", "slots": {
                "metric": "pm25", "year": 2024, "cities": [], "top_n": 3},
            "steps": [
                {"tool": "dataset_read", "args": {}, "thought": "读取数据"},
                {"tool": "aggregate", "args": {"analysis": "top_n_annual",
                                               "metric": "pm25", "top_n": 3},
                 "thought": "年均 TOP3"},
                {"tool": "gb3095_judge", "args": {}, "thought": "国标判定"},
                {"tool": "aggregate", "args": {"analysis": "monthly_series",
                                               "metric": "pm25"}, "thought": "月度序列"},
                {"tool": "draw_chart", "args": {"chart_type": "line"}, "thought": "折线图"},
                {"tool": "validate_result", "args": {}, "thought": "结果校验"},
                {"tool": "build_report", "args": {"template": "pro"}, "thought": "输出报告"},
            ],
        }


class AgentE2ETest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DataStore(chunk_dir=config.FIXTURE_DIR)
        cls.agent = AirQualityAgent(store=cls.store, planner=FixturePlanner(),
                                    verbose=False)

    def test_full_chain(self):
        with mock.patch("agent.tools.validate_tool.mysql_scalar", return_value=None):
            result = self.agent.ask("测试：TOP3 城市 PM2.5 年均与月度曲线")
        answer = result["answer"]
        for section in ("【分析任务】", "【统计结果】", "【超标研判说明】",
                        "【图表输出】", "【数据来源】", "【环境小感悟】", "【结果校验】"):
            self.assertIn(section, answer)
        self.assertTrue(result["charts"])
        chart_path = Path(result["charts"][0]["path"])
        self.assertTrue(chart_path.exists())
        self.assertGreater(chart_path.stat().st_size, 1000)
        self.assertEqual(result["validation"]["passed"],
                         result["validation"]["total"])
        self.assertTrue(all(item["ok"] for item in result["trace"]))
        self.assertEqual(len(result["trace"]), 7)

    def test_trace_is_persisted(self):
        with mock.patch("agent.tools.validate_tool.mysql_scalar", return_value=None):
            result = self.agent.ask("测试：轨迹落盘")
        trace_path = Path(result["trace_path"])
        self.assertTrue(trace_path.exists())


if __name__ == "__main__":
    unittest.main()
