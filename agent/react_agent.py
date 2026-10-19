# -*- coding: utf-8 -*-
"""
agent/react_agent.py —— ReAct Agent 主循环
================================================================================
流程：用户问题 -> Planner 产出计划 -> 依次执行工具（Thought / Action / Observation）
      -> 汇总报告 -> 更新多轮记忆 -> 落盘决策轨迹（答辩可视化证据）。

为什么叫 ReAct？
    Reason + Act：每一步先说明"为什么做"（Thought），再执行工具（Action），
    再用工具返回的结果（Observation）驱动下一步。大模型只参与规划，
    统计与判定全部由本地真实数据上的工具完成，符合题目"禁止编造结果"的要求。
"""

import json
import time
from datetime import datetime

import config
from agent.memory import Memory
from agent.planner import get_planner
from agent.tools import get_tool
from common import banner, info, ok, warn, error, save_json
from core.data_store import DataStore


class AirQualityAgent:
    def __init__(self, store=None, planner=None, template=None, verbose=True):
        self.store = store or DataStore()
        self.memory = Memory()
        self.planner = planner or get_planner()
        self.template = template
        self.verbose = verbose

    # ------------------------------------------------------------------
    def ask(self, question, max_steps=14):
        t_start = time.time()
        plan = self.planner.plan(question, self.memory)
        ctx = {"store": self.store, "question": question,
               "plan": plan, "template": self.template}
        trace = []

        if self.verbose:
            banner(f"问题：{question}")
            info(f"规划器：{plan.get('planner')}｜意图：{plan.get('intent')}")
            info(f"工具链：{' → '.join(s['tool'] for s in plan['steps'])}")

        for idx, step in enumerate(plan["steps"][:max_steps], 1):
            name = step["tool"]
            args = dict(step.get("args") or {})
            if self.template and name == "build_report":
                args["template"] = self.template
            thought = step.get("thought", "")
            if self.verbose:
                print(f"\n  Step {idx}｜Thought: {thought}")
                print(f"          Action : {name}({json.dumps(args, ensure_ascii=False)})")

            t0 = time.time()
            try:
                result = get_tool(name).run(ctx, **args)
                summary, ok_flag = result.summary, True
            except Exception as exc:  # noqa: BLE001 - 单步失败不终止全链路
                summary, ok_flag = f"工具执行失败：{exc}", False
            elapsed = round(time.time() - t0, 2)

            if self.verbose:
                print(f"          Observation（{elapsed}s）: {summary}")
            trace.append({"step": idx, "thought": thought, "action": name,
                          "args": args, "ok": ok_flag, "observation": summary,
                          "elapsed_s": elapsed})

        report = ctx.get("report") or {}
        if not report:
            try:
                fallback = get_tool("build_report").run(
                    ctx, template=self.template or config.REPORT_TEMPLATE)
                report = fallback.data
            except Exception as exc:  # noqa: BLE001
                error(f"报告生成失败：{exc}")
                report = {"text": "报告生成失败，请查看上方工具执行记录。", "path": None}

        # 把本轮实际得到的城市集合写入记忆，支持下一轮"这几个城市"的追问
        if ctx.get("top_cities") and not plan.get("slots", {}).get("cities"):
            plan.setdefault("slots", {})["cities"] = list(ctx["top_cities"])
        self.memory.add(question, plan, report)
        trace_doc = {
            "question": question,
            "planner": plan.get("planner"),
            "intent": plan.get("intent"),
            "slots": plan.get("slots"),
            "steps": trace,
            "answer": report.get("text", ""),
            "charts": ctx.get("charts", []),
            "validation": ctx.get("validation"),
            "elapsed_s": round(time.time() - t_start, 2),
        }
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        trace_path = config.OUTPUT_DIR / f"agent_trace_{stamp}.json"
        save_json(trace_doc, trace_path)
        with open(config.OUTPUT_DIR / "agent_trace.log", "a", encoding="utf-8") as f:
            f.write(f"\n[{stamp}] {question}\n")
            for item in trace:
                f.write(f"  {item['step']}. {item['action']} -> {item['observation']}\n")

        if self.verbose:
            banner("最终结论")
            print(report.get("text", ""))

        return {"question": question, "answer": report.get("text", ""),
                "plan": plan, "trace": trace, "charts": ctx.get("charts", []),
                "validation": ctx.get("validation"),
                "aggregate": ctx.get("aggregate"),
                "trace_path": str(trace_path)}
