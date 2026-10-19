# -*- coding: utf-8 -*-
"""agent/memory.py —— 多轮对话记忆（创新点：支持"再看这几个城市"式追问）。"""


class Memory:
    """保存最近几轮的提问、指标、年份与城市集合。"""

    def __init__(self, max_turns=10):
        self.max_turns = max_turns
        self.turns = []
        self.last_cities = []
        self.last_metric = None
        self.last_year = None
        self.last_analysis = None

    def add(self, question, plan, report=None):
        slots = (plan or {}).get("slots", {})
        self.last_cities = slots.get("cities") or self.last_cities
        self.last_metric = slots.get("metric") or self.last_metric
        self.last_year = slots.get("year") or self.last_year
        self.last_analysis = slots.get("analysis") or self.last_analysis
        self.turns.append({
            "question": question,
            "slots": slots,
            "answer_head": (report or {}).get("text", "")[:120],
        })
        self.turns = self.turns[-self.max_turns:]

    def context(self):
        return {"last_cities": list(self.last_cities),
                "last_metric": self.last_metric,
                "last_year": self.last_year,
                "last_analysis": self.last_analysis,
                "turn": len(self.turns)}

    def resolve_cities(self, question, detected):
        """"这几个城市 / 上述城市"等指代词 -> 上一轮结果中的城市。"""
        if detected:
            return detected
        pronouns = ("这几个城市", "这些城市", "上述城市", "前面几个城市", "它们")
        if any(p in question for p in pronouns):
            return list(self.last_cities)
        return []
