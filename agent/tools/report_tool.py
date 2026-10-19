# -*- coding: utf-8 -*-
"""agent/tools/report_tool.py —— 结构化报告生成（简易版 / 专业版双模板）。"""

from datetime import datetime
from pathlib import Path

from agent.tools.base import BaseTool, ToolResult
from core import gb3095
import config


def _display_path(path):
    """报告里展示仓库相对路径，避免把本机绝对路径带进公开仓库。"""
    try:
        return str(Path(path).resolve().relative_to(config.PROJECT_DIR))
    except (ValueError, OSError):
        return str(path)


class ReportTool(BaseTool):
    name = "build_report"
    description = ("把统计结果、国标研判、图表、校验信息组织成结构化中文结论，"
                   "支持 simple（公众简易解读版）与 pro（从业者专业统计版）两种模板。")
    args_hint = '{"template": "simple"}'

    def run(self, ctx, template=None, **kwargs):
        template = template or config.REPORT_TEMPLATE
        agg = ctx.get("primary_aggregate") or ctx.get("aggregate") or {}
        judgment = ctx.get("judgment") or {}
        charts = ctx.get("charts") or []
        dataset = ctx.get("dataset") or {}
        cleaning = ctx.get("cleaning") or {}
        validation = ctx.get("validation") or {}
        alerts = ctx.get("alerts") or {}
        metric = agg.get("metric", "pm25")
        unit = config.POLLUTANTS[metric]["unit"]
        year = agg.get("year", config.DATASET_YEAR)

        lines = [f"【分析任务】{ctx.get('question', '')}", "", "【统计结果】"]
        lines += self._result_lines(agg, unit)
        lines += ["", "【超标研判说明】"]
        lines += self._judgment_lines(agg, judgment)
        lines += ["", "【图表输出】"]
        lines += [f"- {c['title']}：{_display_path(c['path'])}"
                  for c in charts] or ["- 本次分析未生成图表"]

        # 异常告警（simple / pro 都展示，保持简短）
        if alerts.get("items"):
            jumps = []
            for item in alerts["items"]:
                for jump in item["jumps"][:3]:
                    jumps.append(
                        f"- {item['city']}：{jump['from']} → {jump['to']} "
                        f"{jump['prev']} → {jump['curr']}（{jump['change_pct']:+.1f}%）")
            if jumps:
                lines += ["", "【异常告警】"] + jumps[:6]
            else:
                lines += ["", "【异常告警】", "- 未发现超过阈值的月度突变"]

        # 专业版附加信息（面向环境从业者）
        if template == "pro":
            lines += ["", "【数据与清洗】"]
            if dataset:
                lines.append(
                    f"- 数据：{dataset.get('rows', 0):,} 行 / {dataset.get('chunks', 0)} 个分片，"
                    f"{dataset.get('cities', 0)} 城 / {dataset.get('provinces', 0)} 省份，"
                    f"{dataset.get('date_min', '')}~{dataset.get('date_max', '')}")
            if cleaning:
                lines.append(
                    f"- 清洗：物理越界 {cleaning.get('out_of_range') or 0}，"
                    f"IQR 截断 {cleaning.get('iqr_clipped') or 0}，"
                    f"中位数填充 {cleaning.get('filled') or 0}，"
                    f"去重 {cleaning.get('duplicates') or 0}")
            if validation:
                lines += ["", "【结果校验】"]
                lines.append(f"- 通过 {validation['passed']}/{validation['total']} 项")
                for c in validation["checks"]:
                    lines.append(f"  {'✓' if c['passed'] else '✗'} {c['name']}：{c['detail']}")

        lines += ["", "【数据来源】",
                  f"{config.DATASET_NAME} · {config.DATASET_SOURCE}；"
                  f"本地分片计算，未使用模拟数据。", "",
                  f"【环境小感悟】{gb3095.eco_tip(judgment.get('exceeded_count', 0) > 0)}"]

        text = "\n".join(lines)
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = config.OUTPUT_DIR / f"analysis_{stamp}.md"
        path.write_text(text + "\n", encoding="utf-8")
        with open(config.OUTPUT_DIR / "analysis_history.md", "a", encoding="utf-8") as f:
            f.write("\n\n---\n\n" + text + "\n")

        ctx["report"] = {"text": text, "path": str(path), "template": template}
        return ToolResult(ok=True, summary=f"分析报告已生成：{path.name}",
                          data={"text": text, "path": str(path), "template": template})

    # ------------------------------------------------------------------
    def _result_lines(self, agg, unit):
        analysis = agg.get("analysis")
        if analysis == "top_n_annual":
            lines = []
            for i, r in enumerate(agg.get("rows", []), 1):
                flag = "超过" if r["exceeded"] else "未超过"
                limit = r.get("limit")
                tail = f"，{flag}GB 3095-2012 年均二级标准（{limit:g}{unit}）" \
                    if limit else ""
                lines.append(f"{i}. {r['city']}（{r['province']}）："
                             f"{r['value']:.2f}{unit}{tail}")
            return lines or ["- 无结果"]
        if analysis == "province_exceed":
            lines = [f"全国{config.POLLUTANTS[agg['metric']]['cn']}超标城市-日合计 "
                     f"{agg['total_exceed_days']:,} 个，涉及 {len(agg.get('rows', []))} 个省份。"]
            for i, r in enumerate(agg.get("rows", [])[:8], 1):
                lines.append(f"{i}. {r['province']}：超标 {r['exceed_days']:,} 城市-日，"
                             f"占全国 {r['share']:.1%}，省内超标率 {r['exceed_rate']:.1%}")
            return lines
        if analysis == "city_season_exceed":
            return [f"{agg['city']} {agg['season'] or '全年'}：有效监测 {agg['total_days']} 天，"
                    f"超标 {agg['exceed_days']} 天，超标率 "
                    f"{agg['exceed_days'] / max(agg['total_days'], 1):.1%}，"
                    f"{config.POLLUTANTS[agg['metric']]['cn']}平均浓度 "
                    f"{agg.get('mean_value')}{unit}。"]
        if analysis == "monthly_series":
            rows = agg.get("rows", [])
            cities = agg.get("cities", [])
            if not rows:
                return ["- 无结果"]
            from core import gb3095
            metric = agg["metric"]
            limit = gb3095.limit_of(metric, "8h" if metric == "o3" else "24h")
            lines = [f"{len(cities)} 个城市 {agg.get('year')} 年逐月均值"
                     f"（共 {len(rows)} 个月）："]
            for city in cities:
                pairs = [(r["month"], r.get(city)) for r in rows if r.get(city) is not None]
                if not pairs:
                    continue
                values = [v for _, v in pairs]
                peak_month, peak = max(pairs, key=lambda x: x[1])
                low_month, low = min(pairs, key=lambda x: x[1])
                lines.append(
                    f"- {city}：月均 {sum(values) / len(values):.2f}{unit}，"
                    f"峰值 {peak:.2f}（{peak_month}），最低 {low:.2f}（{low_month}）")
            if limit and metric != "o3":
                over = sorted({r["month"] for r in rows
                               if any(v is not None and v > limit for k, v in r.items()
                                      if k != "month")})
                lines.append(f"- 参考：{config.POLLUTANTS[metric]['cn']} 24 小时二级限值 "
                             f"{limit:g}{unit}；月均超过限值的月份 "
                             f"{len(over)} 个" + (f"（{', '.join(over)}）" if over else ""))
            return lines
        return ["- 无结果"]

    def _judgment_lines(self, agg, judgment):
        lines = []
        if judgment.get("brief"):
            lines.append(judgment["brief"])
        for j in judgment.get("judgments", [])[:5]:
            lines.append(f"- {j['text']}")
        for card in judgment.get("cards", []):
            lines.append(f"- {card}")
        if not lines:
            lines.append("- 本次为趋势对比分析，不作单点超标判定；"
                         "国标限值参考已写在统计结果中。")
        return lines
