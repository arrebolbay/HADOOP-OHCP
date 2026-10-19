# -*- coding: utf-8 -*-
"""agent/tools/dataset_read_tool.py —— 数据集读取工具（分片元数据）。"""

from agent.tools.base import BaseTool, ToolResult
import config


class DatasetReadTool(BaseTool):
    name = "dataset_read"
    description = ("读取本地空气质量分片数据集（按月 chunk），返回行数、分片数、"
                   "覆盖城市/省份、时间范围、各污染物缺失率。")
    args_hint = '{"refresh": false}'

    def run(self, ctx, refresh=False, **kwargs):
        store = ctx["store"]
        if not store.available():
            raise FileNotFoundError(
                f"数据分片不存在：{store.chunk_dir}；请先运行 step02_prepare_data.py")
        stats = store.stats(refresh=refresh)
        ctx["dataset"] = stats

        missing = stats.get("missing_ratio", {})
        avg_missing = (sum(missing.values()) / len(missing)) if missing else 0
        summary = (f"数据读取完成：{stats['rows']:,} 行 / {stats['chunks']} 个按月分片，"
                   f"覆盖 {stats['cities']} 个城市、{stats['provinces']} 个省级行政区，"
                   f"时间范围 {stats['date_min']} ~ {stats['date_max']}，"
                   f"数据源 {stats['source'].split('/')[-1]}，"
                   f"平均缺失率 {avg_missing:.2%}")
        return ToolResult(ok=True, summary=summary,
                          data={"rows": stats["rows"], "chunks": stats["chunks"],
                                "cities": stats["cities"], "provinces": stats["provinces"],
                                "date_range": [stats["date_min"], stats["date_max"]],
                                "missing_ratio": missing, "cleaned": stats["cleaned"]})
