# -*- coding: utf-8 -*-
"""agent/tools/alert_tool.py —— 时序突变告警工具（创新点）。"""

from agent.tools.base import BaseTool, ToolResult
from agent.tools.aggregate_tool import normalize_metric
import config


class AlertTool(BaseTool):
    name = "detect_alert"
    description = ("对城市月度序列做突变检测：相邻月份变化率与绝对变化同时超过阈值时告警，"
                   "用于标记污染突发时段。")
    args_hint = '{"cities": [], "metric": "pm25"}'

    def run(self, ctx, cities=None, metric=None, **kwargs):
        store = ctx["store"]
        agg = ctx.get("aggregate") or {}
        metric = normalize_metric(metric or agg.get("metric") or "pm25")
        targets = cities or ([agg["city"]] if agg.get("city") else None) \
            or agg.get("cities") or ctx.get("top_cities") or []
        if not targets:
            targets = store.annual_mean(metric, top_n=3)["city"].tolist()

        items = []
        for city in list(targets)[:3]:
            res = store.detect_jumps(city, metric)
            items.append(res)
        ctx["alerts"] = {"metric": metric, "items": items,
                         "threshold": f"环比 {config.ALERT_MOM_CHANGE:.0%} 且绝对变化 "
                                      f"{config.ALERT_MIN_DIFF:g}"}
        total = sum(len(i["jumps"]) for i in items)
        summary = (f"突变检测完成：{len(items)} 个城市共发现 {total} 个异常月份区间"
                   f"（阈值：{ctx['alerts']['threshold']}）。")
        return ToolResult(ok=True, summary=summary, data=ctx["alerts"])
