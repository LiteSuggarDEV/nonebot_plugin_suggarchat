from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from typing_extensions import Self

from .models import FunctionDefinitionSchema, ToolContext, ToolData, ToolFunctionSchema


class ToolsManager:
    _instance = None
    _models: ClassVar[dict[str, ToolData]] = {}

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_tool(self, name: str, default: Any | None = None) -> ToolData | None | Any:
        return self._models.get(name, default)

    def get_tool_meta(
        self, name: str, default: Any | None = None
    ) -> ToolFunctionSchema | None | Any:
        func_data = self._models.get(name)
        if func_data is None:
            return default
        if isinstance(func_data, ToolData):
            return func_data.data
        return default

    def get_tool_func(
        self, name: str, default: Any | None = None
    ) -> Callable[[dict[str, Any]], Awaitable[str]] | None | Any:
        func_data = self._models.get(name)
        if func_data is None:
            return default
        if isinstance(func_data, ToolData):
            return func_data.func
        return default

    def get_tools(self) -> dict[str, ToolData]:
        return self._models

    def tools_meta(self) -> dict[str, ToolFunctionSchema]:
        return {k: v.data for k, v in self._models.items()}

    def tools_meta_dict(self, **kwargs) -> dict[str, dict[str, Any]]:
        return {k: v.data.model_dump(**kwargs) for k, v in self._models.items()}

    def register_tool(self, tool: ToolData) -> None:
        if tool.data.function.name not in self._models:
            self._models[tool.data.function.name] = tool

    def remove_tool(self, name: str) -> None:
        if name in self._models:
            del self._models[name]


def on_tools(
    data: FunctionDefinitionSchema,
    custom_run: bool = False,
    strict: bool = False,
):
    def decorator(
        func: Callable[[dict[str, Any]], Awaitable[str]]
        | Callable[[ToolContext], Awaitable[str | None]],
    ):
        tool_data = ToolData(
            func=func,
            data=ToolFunctionSchema(function=data, type="function", strict=strict),
            custom_run=custom_run,
        )
        ToolsManager().register_tool(tool_data)
        return func

    return decorator
