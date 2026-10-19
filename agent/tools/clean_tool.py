# -*- coding: utf-8 -*-
"""agent/tools/clean_tool.py —— 数据清洗工具（缺失值 / 异常值）。"""

from agent.tools.base import BaseTool, ToolResult
from core import cleaning
import config


class CleanTool(BaseTool):
    name = "clean_data"
    description = ("对分片执行数据清洗：物理范围校验、城市 IQR 异常截断、同城市中位数填充、"
                   "去重与全空行剔除；清洗结果写入 data/cache/cleaned。")
    args_hint = '{"force": false}'

    def run(self, ctx, force=False, **kwargs):
        store = ctx["store"]
        cleaned_files = list(config.CLEAN_CHUNK_DIR.glob(
            f"air_quality_{store.year}-*.csv"))
        if cleaned_files and not force:
            store.use_cleaned_if_available()
            stats = store.stats(refresh=True)
            report = {"skipped": True, "chunks": len(cleaned_files),
                      "rows_out": stats.get("rows"),
                      "output_dir": str(config.CLEAN_CHUNK_DIR)}
            target = cleaned_files
            summary = (f"检测到已有清洗结果（{len(cleaned_files)} 个分片，"
                       f"{stats.get('rows', 0):,} 行），直接复用；"
                       f"如需重算可传 force=true。")
        else:
            report = cleaning.clean_all()
            store.use_cleaned_if_available()
            report["skipped"] = False
            target = sorted(config.CLEAN_CHUNK_DIR.glob(
                f"air_quality_{store.year}-*.csv"))
            summary = (f"清洗完成：{report['chunks']} 个分片，"
                       f"{report['rows_in']:,} → {report['rows_out']:,} 行；"
                       f"物理越界 {report['out_of_range']:,} 个、IQR 截断 {report['iqr_clipped']:,} 个、"
                       f"中位数填充 {report['filled']:,} 个、去重 {report['duplicates']:,} 行、"
                       f"全空行剔除 {report['dropped_all_missing']:,} 行。")
        ctx["cleaning"] = report
        ctx["store"] = store
        return ToolResult(ok=True, summary=summary, data={
            "chunks": len(target),
            "rows_out": report.get("rows_out"),
            "out_of_range": report.get("out_of_range"),
            "iqr_clipped": report.get("iqr_clipped"),
            "filled": report.get("filled"),
            "duplicates": report.get("duplicates"),
            "skipped": report.get("skipped", False),
        })
