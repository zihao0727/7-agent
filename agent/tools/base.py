"""
Tool 抽象基类 —— 对应 Claude Code 中每个原子能力单元
每个 Tool 声明自己的 JSON Schema，Agent 循环自动将其注入到 API 调用中
"""

from __future__ import annotations

import abc
import inspect
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSchema:
    """
    对应 Anthropic Tools API 的 tool 定义格式：
    {
        "name": "bash",
        "description": "Run shell commands",
        "input_schema": { "type": "object", "properties": {...}, "required": [...] }
    }
    """
    name: str
    description: str
    input_schema: dict[str, Any]

    def to_api(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def to_openai_api(self) -> dict:
        """返回 OpenAI / DeepSeek 兼容的 function tool 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


class BaseTool(abc.ABC):
    """
    所有工具的抽象基类。

    子类必须实现：
    - schema()  → ToolSchema
    - execute() → str（工具输出字符串）

    工具可以是同步或异步的，框架会自动适配。
    """

    # ── 子类需要定义的类属性 ────────────────────────────────────────────────────
    name: str = ""
    description: str = ""

    @abc.abstractmethod
    def schema(self) -> ToolSchema:
        """返回 JSON Schema 描述，供 LLM 识别和调用"""
        ...

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        执行工具，返回字符串结果。

        - 成功：返回结果文本
        - 失败：raise ToolExecutionError
        """
        ...

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"


class ToolExecutionError(Exception):
    """工具执行失败时抛出"""
    def __init__(self, tool_name: str, message: str, cause: Exception | None = None):
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(f"[{tool_name}] {message}")


def tool(
    name: str | None = None,
    description: str = "",
    schema: dict | None = None,
):
    """
    装饰器：将普通异步函数快速包装成 BaseTool。

    用法::

        @tool(name="greet", description="向用户打招呼")
        async def greet(username: str) -> str:
            return f"Hello, {username}!"
    """
    def decorator(fn):
        fn_name = name or fn.__name__
        sig = inspect.signature(fn)

        # 自动从类型注解生成 JSON Schema
        properties: dict[str, Any] = {}
        required: list[str] = []
        type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            ann = param.annotation
            json_type = type_map.get(ann, "string")
            properties[param_name] = {"type": json_type, "description": ""}
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        input_schema = schema or {
            "type": "object",
            "properties": properties,
            "required": required,
        }

        class _WrappedTool(BaseTool):
            _name = fn_name
            _description = description or (fn.__doc__ or "").strip()

            def schema(self) -> ToolSchema:
                return ToolSchema(
                    name=fn_name,
                    description=self._description,
                    input_schema=input_schema,
                )

            async def execute(self, **kwargs: Any) -> str:
                result = fn(**kwargs)
                if inspect.iscoroutine(result):
                    result = await result
                return str(result)

        _WrappedTool.__name__ = f"Tool_{fn_name}"
        _WrappedTool.name = fn_name
        _WrappedTool.description = description
        instance = _WrappedTool()
        return instance

    return decorator
