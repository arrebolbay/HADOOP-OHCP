# -*- coding: utf-8 -*-
"""agent/tools 注册表：统一暴露工具实例与描述（供 Planner / LLM 使用）。"""

from agent.tools.alert_tool import AlertTool
from agent.tools.aggregate_tool import AggregateTool
from agent.tools.chart_tool import ChartTool
from agent.tools.clean_tool import CleanTool
from agent.tools.dataset_read_tool import DatasetReadTool
from agent.tools.gb3095_tool import GB3095Tool
from agent.tools.report_tool import ReportTool
from agent.tools.validate_tool import ValidateTool

ALL_TOOLS = [
    DatasetReadTool(), CleanTool(), AggregateTool(), GB3095Tool(),
    ChartTool(), AlertTool(), ValidateTool(), ReportTool(),
]

TOOLS = {tool.name: tool for tool in ALL_TOOLS}


def get_tool(name):
    if name not in TOOLS:
        raise KeyError(f"未知工具：{name}")
    return TOOLS[name]


def tool_descriptions():
    return [tool.describe() for tool in ALL_TOOLS]

