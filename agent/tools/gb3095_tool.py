# -*- coding: utf-8 -*-
"""agent/tools/gb3095_tool.py —— GB 3095—2012 国标超标判定工具。"""

from agent.tools.base import BaseTool, ToolResult
from core import gb3095
import config


class GB3095Tool(BaseTool):
    name = "gb3095_judge"
    description = ("依据《环境空气质量标准》GB 3095—2012 二级标准，对聚合结果逐项判定是否超标，"
                   "并生成研判说明（含限值科普与健康提示）。")
    args_hint = '{}'

    def run(self, ctx, **kwargs):
        agg = ctx.get("aggregate")
        if not agg:
            raise ValueError("请先执行 aggregate 聚合统计")
        metric = agg["metric"]
        cn = config.POLLUTANTS[metric]["cn"]
        unit = config.POLLUTANTS[metric]["unit"]
        analysis = agg["analysis"]
        judgments, exceeded_count = [], 0

        if analysis == "top_n_annual":
            period = "annual"
            for r in agg["rows"]:
                j = gb3095.judge(r["value"], metric, period)
                judgments.append({"city": r["city"], "value": r["value"],
                                  "limit": j["limit"], "exceeded": j["exceeded"],
                                  "text": j["text"]})
                exceeded_count += int(j["exceeded"])
            brief = gb3095.standard_brief(metric, period)

        elif analysis == "province_exceed":
            period = agg["period"]
            limit = agg["limit"]
            brief = gb3095.standard_brief(metric, period)
            judgments.append({
                "city": "全国", "value": agg["total_exceed_days"],
                "limit": limit, "exceeded": agg["total_exceed_days"] > 0,
                "text": (f"全国共有 {agg['total_exceed_days']:,} 个城市-日超过 "
                         f"{cn}{'日最大8小时' if period == '8h' else '24小时'}限值 "
                         f"{limit:g}{unit}（占全部有效城市-日的 "
                         f"{agg['total_exceed_days'] / max(agg['total_city_days'], 1):.2%}）"),
            })
            exceeded_count = int(agg["total_exceed_days"] > 0)

        elif analysis == "city_season_exceed":
            period = agg["period"]
            limit = agg["limit"]
            brief = gb3095.standard_brief(metric, period)
            text = (f"{agg['city']} {agg['season'] or '全年'}共有 {agg['exceed_days']} 天超过 "
                    f"{cn}{'日最大8小时' if period == '8h' else '24小时'}限值 "
                    f"{limit:g}{unit}；有效监测 {agg['total_days']} 天，"
                    f"超标率 {agg['exceed_days'] / max(agg['total_days'], 1):.2%}。")
            judgments.append({"city": agg["city"], "value": agg["exceed_days"],
                              "limit": limit, "exceeded": agg["exceed_days"] > 0,
                              "text": text})
            exceeded_count = int(agg["exceed_days"] > 0)
        else:
            raise ValueError(f"不支持的聚合类型：{analysis}")

        # 重度污染科普小卡片（创新点：识别到高浓度时自动附带）
        cards = []
        if analysis == "top_n_annual" and agg["rows"]:
            top = agg["rows"][0]
            limit = gb3095.limit_of(metric, "annual")
            if limit and top["value"] and top["value"] / limit >= 2:
                cards.append(gb3095.health_card(metric, "重度污染"))
        if analysis == "city_season_exceed" and agg["total_days"]:
            if agg["exceed_days"] / agg["total_days"] >= 0.5:
                cards.append(gb3095.health_card(metric, "重度污染"))

        ctx["judgment"] = {"metric": metric, "period": period if analysis != "top_n_annual"
                           else "annual", "judgments": judgments,
                           "exceeded_count": exceeded_count,
                           "brief": brief, "cards": [c for c in cards if c]}
        summary = (f"国标判定完成：{brief} 判定结果中超标 {exceeded_count} 项"
                   + ("，已附污染科普卡片。" if cards else "。"))
        return ToolResult(ok=True, summary=summary, data=ctx["judgment"])
