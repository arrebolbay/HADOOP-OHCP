# -*- coding: utf-8 -*-
"""tests/test_web.py —— Web 前端接口集成测试（fixture 数据 + 本地回环端口）。"""

import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from core.data_store import DataStore
from web.server import create_server


class MiniPlanner:
    """固定计划：验证 HTTP → Agent → 工具 → JSON 的整条链路。"""

    def plan(self, question, memory=None):
        return {
            "planner": "test", "intent": "web-e2e",
            "slots": {"metric": "pm25", "year": 2024,
                      "cities": [], "top_n": 2},
            "steps": [
                {"tool": "dataset_read", "args": {}, "thought": "读取数据"},
                {"tool": "aggregate", "args": {"analysis": "top_n_annual",
                                               "metric": "pm25", "top_n": 2},
                 "thought": "TOP2 年均"},
                {"tool": "gb3095_judge", "args": {}, "thought": "国标判定"},
                {"tool": "aggregate", "args": {"analysis": "monthly_series",
                                               "metric": "pm25"}, "thought": "月度序列"},
                {"tool": "draw_chart", "args": {"chart_type": "line"}, "thought": "折线图"},
                {"tool": "validate_result", "args": {}, "thought": "结果校验"},
                {"tool": "build_report", "args": {"template": "simple"}, "thought": "报告"},
            ],
        }


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DataStore(chunk_dir=config.FIXTURE_DIR)
        cls.server = create_server(port=0, store=cls.store,
                                   planner=MiniPlanner(), verbose=False)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path):
        with urllib.request.urlopen(self._url(path), timeout=30) as resp:
            return resp.status, resp.read(), dict(resp.headers)

    def _post(self, path, payload):
        req = urllib.request.Request(
            self._url(path), data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_index_and_static(self):
        status, body, headers = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("空气质量时序分析 Agent", body.decode("utf-8"))
        status, body, _ = self._get("/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"function ask", body)

    def test_health(self):
        status, body, _ = self._get("/api/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["ok"])
        self.assertTrue(data["data"]["available"])

    def test_overview(self):
        status, body, _ = self._get("/api/overview")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertTrue(data["available"])
        self.assertGreater(data["stats"]["rows"], 0)
        self.assertTrue(data["top_cities"])

    def test_ask_and_chart(self):
        with mock.patch("agent.tools.validate_tool.mysql_scalar", return_value=None):
            status, data = self._post("/api/ask", {"question": "测试网页分析"})
        self.assertEqual(status, 200)
        self.assertIn("【统计结果】", data["answer"])
        self.assertEqual(len(data["trace"]), 7)
        self.assertEqual(data["validation"]["passed"],
                         data["validation"]["total"])
        self.assertTrue(data["charts"])
        chart_url = data["charts"][0]["url"]
        self.assertTrue(chart_url.startswith("/charts/"))
        status, body, headers = self._get(chart_url)
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_empty_question_rejected(self):
        req = urllib.request.Request(
            self._url("/api/ask"), data=b'{"question": ""}',
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(ctx.exception.code, 400)

    def test_reset(self):
        status, data = self._post("/api/reset", {})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])


if __name__ == "__main__":
    unittest.main()
