#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step10_agent_demo.py —— 第 10 步：Agent 现场演示（官方示例 + 多轮追问 + 异常告警）
================================================================================
依次运行：
    1) 题面示例 1：TOP5 城市年均 PM2.5 + 月度曲线
    2) 题面示例 2：各省份 PM2.5 超标天数占比
    3) 题面示例 3：北京市夏季 O₃ 超标总天数
    4) 多轮追问：再看这几个城市的 PM10 超标情况（验证记忆能力）
    5) 异常突变：检测北京市 PM2.5 月度突变（验证告警创新点）

所有回答同时写入 output/04_Agent演示记录.md，图表写入 output/charts/。
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from common import banner, info, ok, warn, print_table
from agent import AirQualityAgent

QUESTIONS = [
    "找出2024年PM2.5年均浓度最高的5个城市，画出月度变化曲线",
    "筛选PM2.5超标记录，统计各省份超标天数占比",
    "统计北京市夏季臭氧O3超标总天数",
    "再看这几个城市的PM10超标情况（专业版）",
    "检测北京市PM2.5异常突变，标记污染突发时段",
]


def main():
    banner("第 10 步：Agent 全链路演示")
    if not config.LLM_API_KEY:
        warn("未配置 AQ_LLM_API_KEY：本次演示使用规则规划器（双模兜底，链路完全一致）")

    agent = AirQualityAgent()
    results = []
    for i, question in enumerate(QUESTIONS, 1):
        banner(f"演示 {i}/{len(QUESTIONS)}：{question}")
        res = agent.ask(question)
        results.append(res)
        charts = [c["path"] for c in res["charts"]]
        info(f"规划器：{res['plan']['planner']}｜工具步数：{len(res['trace'])}｜"
             f"图表：{len(charts)} 个")
        if res["validation"]:
            info(f"结果校验：{res['validation']['passed']}/{res['validation']['total']} 通过")
        ok(f"演示 {i} 完成")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# 空气质量时序分析 Agent 演示记录", "",
             f"- 生成时间：{stamp}",
             f"- 规划器模式：{config.PLANNER_MODE}（无 Key 时自动规则兜底）",
             f"- 数据源：{config.DATASET_NAME}（{config.DATASET_SOURCE}）", ""]
    for i, (question, res) in enumerate(zip(QUESTIONS, results), 1):
        lines += [f"## {i}. {question}", "", res["answer"], "",
                  "**工具调用轨迹**", ""]
        for item in res["trace"]:
            mark = "✓" if item["ok"] else "✗"
            lines.append(f"- {mark} `{item['action']}`：{item['observation']}")
        lines.append("")
    out = config.OUTPUT_DIR / "04_Agent演示记录.md"
    out.write_text("\n".join(lines), encoding="utf-8")

    summary = [(i, q, r["plan"]["planner"], len(r["trace"]),
                len(r["charts"]),
                f"{r['validation']['passed']}/{r['validation']['total']}"
                if r["validation"] else "-")
               for i, (q, r) in enumerate(zip(QUESTIONS, results), 1)]
    print_table(summary, headers=["#", "问题", "规划器", "工具步数", "图表", "校验"],
                max_rows=10, title="演示汇总")
    ok(f"演示记录已保存：{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
