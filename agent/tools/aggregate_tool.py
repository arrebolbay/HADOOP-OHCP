# -*- coding: utf-8 -*-
"""agent/tools/aggregate_tool.py —— 聚合统计工具（时序 / 地域维度）。"""

from agent.tools.base import BaseTool, ToolResult
import config

METRIC_ALIASES = {
    "pm2.5": "pm25", "pm25": "pm25", "PM2.5": "pm25",
    "pm10": "pm10", "PM10": "pm10",
    "o3": "o3", "O3": "o3", "O₃": "o3", "臭氧": "o3",
    "so2": "so2", "SO2": "so2", "SO₂": "so2",
    "no2": "no2", "NO2": "no2", "NO₂": "no2",
    "co": "co", "CO": "co", "一氧化碳": "co",
    "aqi": "aqi", "AQI": "aqi",
}


def normalize_metric(metric):
    key = str(metric or "pm25").strip()
    return METRIC_ALIASES.get(key, METRIC_ALIASES.get(key.lower(), "pm25"))


def _round(value, digits=2):
    return round(float(value), digits) if value is not None else None


class AggregateTool(BaseTool):
    name = "aggregate"
    description = ("按城市/省份/年月/季节聚合统计。支持 top_n_annual（年均浓度 TOP-N）、"
                   "monthly_series（逐月曲线）、province_exceed（各省超标天数占比）、"
                   "city_season_exceed（某城市某季节超标天数）。")
    args_hint = ('{"analysis": "top_n_annual", "metric": "pm25", "top_n": 5, '
                 '"cities": [], "season": "夏季", "year": 2024}')

    def run(self, ctx, analysis="top_n_annual", metric="pm25", top_n=5,
            cities=None, season=None, period=None, city=None, **kwargs):
        store = ctx["store"]
        metric = normalize_metric(metric)
        year = int(kwargs.get("year") or store.year)
        result = {"analysis": analysis, "metric": metric, "year": year}

        if analysis == "top_n_annual":
            df = store.annual_mean(metric, top_n=top_n)
            rows = [{"city": r["city"], "province": r["province"],
                     "value": _round(r["value"]), "days": int(r["days"]),
                     "limit": r["limit"], "exceeded": bool(r["exceeded"])}
                    for r in df.to_dict("records")]
            ctx["top_cities"] = [r["city"] for r in rows]
            result.update({"top_n": int(top_n), "rows": rows,
                           "unit": config.POLLUTANTS[metric]["unit"]})
            summary = (f"已完成 {year} 年 {config.POLLUTANTS[metric]['cn']} 年均浓度排序，"
                       f"共 {len(store.annual_mean(metric))} 个城市参与，TOP{top_n} 为："
                       + "、".join(f"{r['city']} {r['value']}" for r in rows))

        elif analysis == "monthly_series":
            chosen = cities or ctx.get("top_cities") or \
                store.annual_mean(metric, top_n=3)["city"].tolist()
            wide = store.monthly_series(chosen, metric)
            records = []
            for month, row in wide.iterrows():
                item = {"month": str(month)}
                for name, value in row.items():
                    item[str(name)] = _round(value) if value == value else None
                records.append(item)
            result.update({"cities": list(chosen), "rows": records,
                           "unit": config.POLLUTANTS[metric]["unit"]})
            summary = (f"已生成 {len(chosen)} 个城市 {year} 年的逐月 "
                       f"{config.POLLUTANTS[metric]['cn']} 均值序列"
                       f"（{len(records)} 个月）。")

        elif analysis == "province_exceed":
            res = store.province_exceed(metric, period="8h" if metric == "o3" else "24h")
            rows = [{**r,
                     "share": _round(r["share"], 4),
                     "exceed_rate": _round(r["exceed_rate"], 4),
                     "value": _round(r["exceed_days"])} for r in res["rows"]]
            result.update({"period": res["period"], "limit": res["limit"],
                           "total_exceed_days": res["total_exceed_days"],
                           "total_city_days": res["total_city_days"], "rows": rows})
            summary = (f"已统计各省份 {config.POLLUTANTS[metric]['cn']} "
                       f"{'日最大8小时' if res['period'] == '8h' else '24小时'}均值超标城市-天数："
                       f"全国合计 {res['total_exceed_days']:,} 个，"
                       f"涉及 {len(rows)} 个省级行政区。")

        elif analysis == "city_season_exceed":
            target = city or (cities[0] if cities else None) or \
                (ctx.get("top_cities") or ["北京"])[0]
            res = store.city_season_exceed(target, metric, season)
            monthly = [{**m, "mean_value": _round(m["mean_value"])}
                       for m in res["monthly"]]
            result.update({"city": target, "period": res["period"],
                           "season": season, "limit": res["limit"],
                           "total_days": res["total_days"],
                           "exceed_days": res["exceed_days"],
                           "mean_value": _round(res["mean_value"]),
                           "monthly": monthly})
            summary = (f"{target} {year} 年{season or '全年'} "
                       f"{config.POLLUTANTS[metric]['cn']} 有效监测 {res['total_days']} 天，"
                       f"超标 {res['exceed_days']} 天"
                       f"（限值 {res['limit']:g}{config.POLLUTANTS[metric]['unit']}）。")
        else:
            raise ValueError(f"不支持的聚合类型：{analysis}")

        ctx["aggregate"] = result
        if analysis == "monthly_series":
            ctx["monthly_aggregate"] = result
        else:
            ctx["primary_aggregate"] = result
        return ToolResult(ok=True, summary=summary, data=result)
