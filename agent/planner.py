# -*- coding: utf-8 -*-
"""
agent/planner.py —— 任务规划器（双模：LLM 优先 + 规则兜底）
================================================================================
RulePlanner：确定性的中文意图解析，不依赖网络，现场演示的"保底方案"。
LLMPlanner ：调用 OpenAI 兼容接口，让大模型输出同样结构的计划（只做规划，不做计算）。
DualPlanner：auto 模式下先试大模型，超时/报错/JSON 不合法就自动降级到规则规划器。

两条路径输出完全相同的 plan 结构：
    {"planner": "rule|llm", "intent": "...", "slots": {...}, "steps": [...]}
"""

import json
import re

import pandas as pd

import config
from agent.prompts import build_messages
from agent.tools import tool_descriptions
from agent.tools.aggregate_tool import normalize_metric
from common import warn

METRIC_PATTERNS = [
    ("pm25", r"pm\s*2\.5|pm25|细颗粒物"),
    ("pm10", r"pm\s*10|pm10|可吸入颗粒物"),
    ("o3", r"臭氧|o\s*3|o₃|o3"),
    ("so2", r"二氧化硫|so\s*2|so₂|so2"),
    ("no2", r"二氧化氮|no\s*2|no₂|no2"),
    ("co", r"一氧化碳|(?<![a-z])co(?![a-z])"),
    ("aqi", r"aqi|空气质量指数"),
]


def _normalize(question):
    text = str(question).replace("　", " ")
    text = text.replace("（", "(").replace("）", ")").replace("，", ",")
    return re.sub(r"\s+", " ", text)


_CITY_CACHE = None


def known_cities():
    """从真实行政区划映射表读取城市名单（按长度降序，避免短名先匹配）。"""
    global _CITY_CACHE
    if _CITY_CACHE is not None:
        return _CITY_CACHE
    cities = set()
    if config.PROVINCE_MAP_CSV.exists():
        df = pd.read_csv(config.PROVINCE_MAP_CSV)
        cities.update(str(c) for c in df["city"].dropna().unique())
    cities.update({"北京", "上海", "广州", "深圳", "天津", "重庆", "成都", "杭州",
                   "武汉", "西安", "南京", "郑州", "济南", "青岛", "长沙"})
    _CITY_CACHE = sorted(cities, key=len, reverse=True)
    return _CITY_CACHE


def detect_metric(text):
    lowered = text.lower()
    for metric, pattern in METRIC_PATTERNS:
        if re.search(pattern, lowered):
            return normalize_metric(metric)
    return "pm25"


def detect_cities(text):
    if any(p in text for p in ("各省", "省份", "全省", "各省份")):
        return []
    found = []
    for city in known_cities():
        if city and city in text:
            found.append(city)
    result = []
    for city in sorted(set(found), key=len, reverse=True):
        if not any(city != other and city in other for other in result):
            result.append(city)
    return result


class RulePlanner:
    """基于关键词/正则的确定性规划器（零网络依赖）。"""

    name = "rule"

    def plan(self, question, memory=None):
        text = _normalize(question)
        lowered = text.lower()
        metric = detect_metric(text)
        year_match = re.search(r"(20\d{2})\s*年?", text)
        year = int(year_match.group(1)) if year_match else (
            (memory.last_year if memory and memory.last_year else config.DATASET_YEAR))

        cities = detect_cities(text)
        if memory:
            cities = memory.resolve_cities(text, cities)

        season = next((s for s in config.SEASONS if s in text), None)
        if "夏" in text and not season:
            season = "夏季"
        if "冬" in text and not season:
            season = "冬季"

        top_match = re.search(r"(?:前|top|最高的?|排名前)\s*(\d+)", lowered)
        top_n = int(top_match.group(1)) if top_match else 5

        wants_province = any(k in text for k in ("各省", "省份", "全省", "占比"))
        wants_monthly = any(k in text for k in ("月度", "逐月", "曲线", "折线", "趋势"))
        wants_top = any(k in text for k in ("最高", "top", "排名", "年均", "前"))
        wants_alert = any(k in text for k in ("异常", "突变", "告警", "突发", "跳变"))
        wants_pro = any(k in text for k in ("专业", "统计版", "从业者"))

        steps = [
            {"tool": "dataset_read", "args": {},
             "thought": "先确认本地分片数据规模与时间范围"},
            {"tool": "clean_data", "args": {},
             "thought": "执行缺失值/异常值清洗（DWD 层）"},
        ]
        slots = {"metric": metric, "year": year, "cities": cities,
                 "season": season, "top_n": top_n, "analysis": None}

        if wants_province:
            slots["analysis"] = "province_exceed"
            steps += [
                {"tool": "aggregate", "args": {"analysis": "province_exceed",
                                               "metric": metric, "year": year},
                 "thought": "按省份聚合超标城市-天数并计算占比"},
                {"tool": "gb3095_judge", "args": {},
                 "thought": "依据 GB 3095-2012 判定限值并生成研判说明"},
                {"tool": "draw_chart", "args": {"chart_type": "pie"},
                 "thought": "生成各省超标天数占比饼图"},
            ]
        elif season and cities:
            slots["analysis"] = "city_season_exceed"
            steps += [
                {"tool": "aggregate", "args": {"analysis": "city_season_exceed",
                                               "metric": metric, "year": year,
                                               "city": cities[0], "season": season},
                 "thought": f"统计{cities[0]}{season}超标天数"},
                {"tool": "gb3095_judge", "args": {},
                 "thought": "按对应统计口径的国标限值判定"},
                {"tool": "draw_chart", "args": {"chart_type": "bar"},
                 "thought": "生成逐月超标天数柱状图"},
            ]
        elif wants_top:
            slots["analysis"] = "top_n_annual"
            steps += [
                {"tool": "aggregate", "args": {"analysis": "top_n_annual",
                                               "metric": metric, "year": year,
                                               "top_n": top_n},
                 "thought": f"计算城市年均浓度并取 TOP{top_n}"},
                {"tool": "gb3095_judge", "args": {},
                 "thought": "对 TOP 城市做年均国标判定"},
            ]
            if wants_monthly:
                steps += [
                    {"tool": "aggregate", "args": {"analysis": "monthly_series",
                                                   "metric": metric, "year": year},
                     "thought": "复用上一轮 TOP 城市，计算逐月序列"},
                    {"tool": "draw_chart", "args": {"chart_type": "line"},
                     "thought": "绘制 TOP 城市月度变化折线图"},
                ]
            else:
                steps.append({"tool": "draw_chart", "args": {"chart_type": "bar"},
                              "thought": "绘制 TOP 城市柱状图"})
        else:
            slots["analysis"] = "monthly_series"
            steps += [
                {"tool": "aggregate", "args": {"analysis": "monthly_series",
                                               "metric": metric, "year": year,
                                               "cities": cities},
                 "thought": "计算指定/默认城市的逐月浓度序列"},
                {"tool": "draw_chart", "args": {"chart_type": "line"},
                 "thought": "绘制月度变化折线图"},
            ]

        if wants_alert:
            steps.append({"tool": "detect_alert",
                          "args": {"metric": metric, "cities": cities},
                          "thought": "检测月度突变，标记污染突发时段"})
        steps += [
            {"tool": "validate_result", "args": {}, "thought": "对结果做独立校验"},
            {"tool": "build_report",
             "args": {"template": "pro" if wants_pro else "simple"},
             "thought": "输出结构化结论（含思政自然融入）"},
        ]
        intent = "省份超标占比分析" if wants_province else (
            "城市季节超标统计" if season and cities else (
                "TOP 城市年均+月度曲线" if wants_top else "城市月度趋势分析"))
        return {"planner": self.name, "intent": intent, "slots": slots, "steps": steps}


class LLMPlanner:
    """OpenAI 兼容接口规划器：只负责拆解任务，不参与任何数值计算。"""

    name = "llm"

    def __init__(self, base_url=None, model=None, api_key=None, timeout=None):
        self.base_url = (base_url or config.LLM_BASE_URL).rstrip("/")
        self.model = model or config.LLM_MODEL
        self.api_key = api_key if api_key is not None else config.LLM_API_KEY
        self.timeout = timeout or config.LLM_TIMEOUT

    @property
    def enabled(self):
        return bool(self.api_key)

    def plan(self, question, memory=None):
        if not self.enabled:
            raise RuntimeError("未配置 AQ_LLM_API_KEY，无法使用大模型规划")
        import requests

        payload = {
            "model": self.model,
            "messages": build_messages(question, tool_descriptions(),
                                       memory.context() if memory else {}),
            "temperature": 0,
        }
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload, timeout=self.timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        plan = self._parse_json(content)
        self._validate(plan)
        plan["planner"] = self.name
        return plan

    @staticmethod
    def _parse_json(content):
        text = content.strip()
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            raise ValueError("大模型没有返回 JSON")
        return json.loads(text[start:end + 1])

    @staticmethod
    def _validate(plan):
        from agent.tools import TOOLS
        steps = plan.get("steps") or []
        if not steps:
            raise ValueError("计划为空")
        for step in steps:
            if step.get("tool") not in TOOLS:
                raise ValueError(f"未知工具：{step.get('tool')}")
        names = [s["tool"] for s in steps]
        if "dataset_read" not in names:
            steps.insert(0, {"tool": "dataset_read", "args": {},
                             "thought": "补齐：先读取本地分片数据"})
            names.insert(0, "dataset_read")
        if "clean_data" not in names:
            steps.insert(1, {"tool": "clean_data", "args": {},
                             "thought": "补齐：执行数据清洗"})
        if "build_report" not in names:
            steps.append({"tool": "build_report", "args": {"template": "simple"},
                          "thought": "补齐：输出报告"})
        plan["steps"] = steps


class DualPlanner:
    """auto 模式：先试 LLM，失败自动降级规则规划器（演示可靠性保障）。"""

    name = "auto"

    def __init__(self, llm=None, rule=None):
        self.llm = llm or LLMPlanner()
        self.rule = rule or RulePlanner()

    def plan(self, question, memory=None):
        if self.llm.enabled:
            try:
                return self.llm.plan(question, memory)
            except Exception as exc:  # noqa: BLE001 - 任何异常都降级
                warn(f"大模型规划不可用（{type(exc).__name__}: {exc}），已自动切换到规则规划器")
        plan = self.rule.plan(question, memory)
        plan["planner"] = "rule(fallback)"
        return plan


def get_planner():
    mode = config.PLANNER_MODE.lower()
    if mode == "rule":
        return RulePlanner()
    if mode == "llm":
        return LLMPlanner()
    return DualPlanner()
