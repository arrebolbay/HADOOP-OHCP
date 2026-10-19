# -*- coding: utf-8 -*-
"""agent/tools/chart_tool.py —— 可视化工具（折线图 / 柱状图 / 饼图）。"""

from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from agent.tools.base import BaseTool, ToolResult
from core import gb3095
import config


def setup_chinese_font():
    """注册中文字体，避免图表出现方框。"""
    path = config.font_path()
    if path:
        font_manager.fontManager.addfont(path)
        name = font_manager.FontProperties(fname=path).get_name()
        plt.rcParams["font.family"] = [name, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


class ChartTool(BaseTool):
    name = "draw_chart"
    description = "根据聚合结果自动生成图表：折线图（月度趋势）、柱状图（TOP-N）、饼图（省份占比）。"
    args_hint = '{"chart_type": "line"}'

    def run(self, ctx, chart_type="auto", **kwargs):
        agg = ctx.get("aggregate")
        if not agg:
            raise ValueError("请先执行 aggregate 聚合统计")
        analysis = agg["analysis"]
        if chart_type == "auto":
            chart_type = {"monthly_series": "line", "top_n_annual": "bar",
                          "province_exceed": "pie", "city_season_exceed": "bar"}[analysis]

        setup_chinese_font()
        config.CHART_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = config.CHART_DIR / f"{stamp}_{analysis}_{chart_type}.png"
        metric_cn = config.POLLUTANTS[agg["metric"]]["cn"]
        year = agg.get("year", config.DATASET_YEAR)

        if chart_type == "line":
            self._line(agg, path, metric_cn, year)
            title = f"{year}年{metric_cn}月度变化曲线"
        elif chart_type == "pie":
            self._pie(agg, path, metric_cn, year)
            title = f"{year}年各省份{metric_cn}超标天数占比"
        else:
            self._bar(agg, path, metric_cn, year)
            title = f"{year}年{metric_cn}统计柱状图"

        ctx.setdefault("charts", []).append(
            {"path": str(path), "title": title, "chart_type": chart_type})
        rel = path.relative_to(config.PROJECT_DIR)
        summary = f"图表已生成：{rel}"
        return ToolResult(ok=True, summary=summary,
                          data={"path": str(path), "title": title})

    # ------------------------------------------------------------------
    def _line(self, agg, path, metric_cn, year):
        rows = agg["rows"]
        cities = agg["cities"]
        months = [r["month"] for r in rows]
        fig, ax = plt.subplots(figsize=(11, 5.2), dpi=130)
        for city in cities:
            values = [r.get(city) for r in rows]
            ax.plot(months, values, marker="o", markersize=3, linewidth=1.8, label=city)
        limit = gb3095.limit_of(agg["metric"], "24h")
        if limit and agg["metric"] != "o3":
            ax.axhline(limit, color="crimson", linestyle="--", linewidth=1.2,
                       label=f"GB 3095 {limit:g}（24h限值）")
        ax.set_title(f"{year}年 {metric_cn} 月度变化（{len(cities)} 个城市）")
        ax.set_xlabel("月份")
        ax.set_ylabel(f"{metric_cn} 浓度（{config.POLLUTANTS[agg['metric']]['unit']}）")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8, ncol=2)
        fig.text(0.99, 0.01, "数据：本地真实监测分片（分片批处理）", ha="right",
                 fontsize=7, color="#666666")
        fig.autofmt_xdate(rotation=45)
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)

    def _bar(self, agg, path, metric_cn, year):
        if agg["analysis"] == "top_n_annual":
            labels = [r["city"] for r in agg["rows"]]
            values = [r["value"] for r in agg["rows"]]
            colors = ["#C0392B" if r["exceeded"] else "#2E86C1" for r in agg["rows"]]
            title = f"{year}年 {metric_cn} 年均浓度 TOP{len(labels)}"
            limit = gb3095.limit_of(agg["metric"], "annual")
            ylabel = f"年均浓度（{agg.get('unit', '')}）"
        else:
            labels = [m["month"] + "月" for m in agg["monthly"]]
            values = [m["exceed_days"] for m in agg["monthly"]]
            colors = "#C0392B"
            title = (f"{agg['city']} {year}年{agg['season'] or ''}"
                     f"{metric_cn}逐月超标天数")
            limit = None
            ylabel = "超标天数（天）"

        fig, ax = plt.subplots(figsize=(9.5, 5), dpi=130)
        bars = ax.bar(labels, values, color=colors, width=0.62)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                    f"{value:g}", ha="center", va="bottom", fontsize=8)
        if limit:
            ax.axhline(limit, color="crimson", linestyle="--", linewidth=1.2,
                       label=f"GB 3095 {limit:g}（年均限值）")
            ax.legend(fontsize=8)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.25)
        fig.text(0.99, 0.01, "数据：本地真实监测分片（分片批处理）", ha="right",
                 fontsize=7, color="#666666")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)

    def _pie(self, agg, path, metric_cn, year):
        rows = agg["rows"][:10]
        others = agg["rows"][10:]
        labels = [r["province"] for r in rows]
        values = [r["exceed_days"] for r in rows]
        if others:
            labels.append("其他省份")
            values.append(sum(r["exceed_days"] for r in others))
        fig, ax = plt.subplots(figsize=(8.2, 6), dpi=130)
        wedges, _, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%", startangle=120,
            textprops={"fontsize": 8},
            colors=plt.cm.tab20.colors[: len(values)])
        ax.set_title(f"{year}年 各省份 {metric_cn} 超标天数占比"
                     f"（全国 {agg['total_exceed_days']:,} 城市-日）")
        fig.text(0.99, 0.01, "数据：本地真实监测分片（分片批处理）", ha="right",
                 fontsize=7, color="#666666")
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)
