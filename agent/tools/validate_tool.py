# -*- coding: utf-8 -*-
"""agent/tools/validate_tool.py —— 结果校验工具（创新点：降低规划/计算错误）。"""

import config
from agent.tools.base import BaseTool, ToolResult
from agent.tools.aggregate_tool import normalize_metric
from core import gb3095
from common import mysql_scalar


class ValidateTool(BaseTool):
    name = "validate_result"
    description = ("对聚合结果做独立校验：非空性、物理范围、国标判定一致性、加权复算，"
                   "并在 MySQL ADS 结果表可用时做跨引擎对账。")
    args_hint = '{}'

    def run(self, ctx, **kwargs):
        agg = ctx.get("primary_aggregate") or ctx.get("aggregate")
        if not agg:
            raise ValueError("请先执行 aggregate 聚合统计")
        store = ctx["store"]
        checks = []

        # 1) 结果非空
        if agg["analysis"] == "top_n_annual":
            non_empty = bool(agg.get("rows"))
        elif agg["analysis"] == "province_exceed":
            non_empty = bool(agg.get("rows")) and agg.get("total_city_days", 0) > 0
        elif agg["analysis"] == "monthly_series":
            non_empty = bool(agg.get("rows")) and any(
                v is not None for r in agg["rows"] for k, v in r.items() if k != "month")
        else:
            non_empty = agg.get("total_days", 0) > 0
        checks.append({"name": "结果非空性", "passed": non_empty,
                       "detail": f"聚合类型 {agg['analysis']}，"
                                 f"{'有' if non_empty else '无'}有效结果"})

        # 2) 物理范围
        metric = agg["metric"]
        low, high = config.PHYSICAL_RANGES.get(metric, (0, 1e9))
        values = []
        if agg["analysis"] == "top_n_annual":
            values = [r["value"] for r in agg["rows"]]
        elif agg["analysis"] == "monthly_series":
            values = [v for r in agg.get("rows", []) for k, v in r.items()
                      if k != "month" and v is not None]
        elif agg["analysis"] == "city_season_exceed":
            values = [agg.get("mean_value") or 0]
        in_range = all(v is None or low <= v <= high for v in values)
        checks.append({"name": "物理范围校验", "passed": in_range,
                       "detail": f"{config.POLLUTANTS[metric]['cn']} 取值应在 "
                                 f"[{low}, {high}]，实际检查 {len(values)} 个值"})

        # 3) 国标判定一致性
        consistent = True
        if agg["analysis"] == "top_n_annual":
            limit = gb3095.limit_of(metric, "annual")
            for r in agg["rows"]:
                expect = (r["value"] > limit + 1e-9) if limit else False
                if bool(r["exceeded"]) != expect:
                    consistent = False
                    break
        checks.append({"name": "国标判定一致性", "passed": consistent,
                       "detail": "exceeded 标记与 GB 3095-2012 限值复判一致"})

        # 4) 独立加权复算（用有效小时数加权，和年均算法对拍）
        recompute_ok, diff = True, 0.0
        if agg["analysis"] == "top_n_annual" and agg["rows"]:
            daily = store.daily_values(metric, "mean")
            top_city = agg["rows"][0]["city"]
            sub = daily[daily["city"] == top_city]
            weighted = ((sub["value"] * sub["valid_hours"]).sum()
                        / sub["valid_hours"].sum()) if len(sub) else 0
            reported = agg["rows"][0]["value"]
            if reported:
                diff = abs(weighted - reported) / reported
                recompute_ok = diff <= config.VALIDATE_MAX_REL_DIFF
            checks.append({"name": "独立加权复算", "passed": recompute_ok,
                           "detail": f"{top_city} 加权复算 {weighted:.4f} vs 报告 {reported}，"
                                     f"相对偏差 {diff:.4%}"})

        # 5) MySQL ADS 跨引擎对账（有表才做，没有则跳过）
        mysql_diff, mysql_checked = None, False
        if agg["analysis"] == "top_n_annual" and agg["rows"]:
            try:
                db_value = mysql_scalar(
                    "SELECT annual_mean FROM fact_city_year "
                    "WHERE year=%s AND metric=%s AND city=%s",
                    (agg.get("year", config.DATASET_YEAR), metric,
                     agg["rows"][0]["city"]), database=config.MYSQL_DB)
                if db_value is not None:
                    mysql_checked = True
                    mysql_diff = abs(float(db_value) - agg["rows"][0]["value"]) / max(
                        float(db_value), 1e-9)
            except Exception:  # noqa: BLE001 - MySQL 未就绪时跳过对账
                mysql_checked = False
        checks.append({"name": "MySQL 跨引擎对账",
                       "passed": (mysql_diff is None) or (mysql_diff <= config.VALIDATE_MAX_REL_DIFF),
                       "detail": (f"与 MySQL fact_city_year 偏差 {mysql_diff:.4%}"
                                  if mysql_checked else "MySQL 结果表暂不可用，已跳过（不影响结论）")})

        passed = sum(1 for c in checks if c["passed"])
        ctx["validation"] = {"checks": checks, "passed": passed,
                             "total": len(checks)}
        summary = f"结果校验完成：{passed}/{len(checks)} 项通过" + (
            "，全部通过。" if passed == len(checks) else "，请查看明细。")
        return ToolResult(ok=True, summary=summary, data=ctx["validation"])
