# -*- coding: utf-8 -*-
"""
agent/tools/base.py —— 工具统一接口
================================================================================
约定：
    - 每个工具是一个类，包含 name / description / run(ctx, **args)
    - run() 返回 dict：{"ok": bool, "summary": str, "data": ...}
    - ctx 是"本次分析的共享上下文"，工具之间靠它传结果（避免大对象在 JSON 里搬来搬去）
    - 任何工具抛异常，Agent 会记录该步失败并继续后续步骤（可解释、可降级）
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class ToolResult:
    ok: bool
    summary: str
    data: Any = None
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {"ok": self.ok, "summary": self.summary,
                "data": self.data, "meta": self.meta}


class BaseTool:
    name = "base"
    description = ""
    args_hint = ""

    def run(self, ctx: dict, **kwargs) -> ToolResult:
        raise NotImplementedError

    def describe(self):
        return {"name": self.name, "description": self.description,
                "args": self.args_hint}
