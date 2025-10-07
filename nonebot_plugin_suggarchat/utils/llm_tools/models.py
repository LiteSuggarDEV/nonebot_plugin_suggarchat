from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from nonebot.adapters.onebot.v11 import Bot
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from ...event import SuggarEvent
from ...matcher import Matcher

T = TypeVar("T", str, int, float, bool, list, dict)
OPEN_AI_PARAM_TYPE = Literal[
    "string", "number", "integer", "boolean", "array", "object"
]


class FunctionPropertySchema(BaseModel, Generic[T]):
    """校验函数参数的属性"""

    type: Literal[OPEN_AI_PARAM_TYPE] | list[OPEN_AI_PARAM_TYPE] = Field(
        ..., description="参数类型"
    )
    description: str = Field(..., description="参数描述")
    enum: list[T] | None = Field(default=None, description="枚举的参数")
    properties: dict[str, FunctionPropertySchema] | None = Field(
        default=None, description="参数属性定义,仅当参数类型为object时有效"
    )
    items: FunctionPropertySchema | None = Field(
        default=None, description="仅当type='array'时使用，定义数组元素类型"
    )
    minItems: int | None = Field(
        default=None, description="仅当type='array'时使用，定义数组的最小长度"
    )
    maxItems: int | None = Field(
        default=None, description="仅当type='array'时使用，定义数组元素数量最大长度"
    )
    uniqueItems: bool | None = Field(
        default=None,
        description="是否要求数组元素唯一，当类型为array时，此参数有效默认为False",
    )
    required: list[str] | None = Field(
        default=None, description="参数属性定义,仅当参数类型为object时有效"
    )

    @model_validator(mode="after")
    def validator(self) -> Self:
        if self.type == "object":
            if self.properties is None:
                raise ValueError("When type is object, properties must be set.")
            elif self.required is None:
                self.required = []
            if any(
                i is not None
                for i in (self.maxItems, self.minItems, self.uniqueItems, self.items)
            ):
                raise ValueError(
                    "When type is object, `maxItems`,`minItems`,`uniqueItems`,`Items` must be None."
                )
        elif self.type == "array":
            if self.items is None:
                raise ValueError("When type is array, items must be set.")
            elif self.minItems is not None and self.minItems < 0:
                raise ValueError("minItems must be greater than or equal to 0.")
            elif self.maxItems is not None and self.maxItems < 0:
                raise ValueError("maxItems must be greater than or equal to 0.")
            elif (
                self.maxItems is not None
                and self.minItems is not None
                and self.maxItems < self.minItems
            ):
                raise ValueError("maxItems must be greater than or equal to minItems.")
            elif self.uniqueItems is None:
                self.uniqueItems = False

        return self


class FunctionParametersSchema(BaseModel):
    """校验函数参数结构"""

    type: Literal["object"] = Field(..., description="参数类型")
    properties: dict[str, FunctionPropertySchema] | None = Field(
        default=None, description="参数属性定义"
    )

    required: list[str] = Field([], description="必需参数列表")


class FunctionDefinitionSchema(BaseModel):
    """校验函数定义结构"""

    name: str = Field(..., description="函数名称")
    description: str = Field(..., description="函数描述")
    parameters: FunctionParametersSchema = Field(..., description="函数参数定义")


class ToolFunctionSchema(BaseModel):
    """校验完整的function字段结构"""

    function: FunctionDefinitionSchema = Field(..., description="函数定义")
    type: Literal["function"] = "function"
    strict: bool = Field(default=False, description="是否严格模式")


ToolChoice = Literal["none", "auto", "required"] | ToolFunctionSchema


@dataclass
class ToolContext:
    data: dict[str, Any] = field()
    event: SuggarEvent = field()
    matcher: Matcher = field()
    bot: Bot = field()


class ToolData(BaseModel):
    """用于注册Tool的数据模型"""

    data: ToolFunctionSchema = Field(..., description="工具元数据")
    func: (
        Callable[[dict[str, Any]], Awaitable[str]]
        | Callable[[ToolContext], Awaitable[str | None]]
    ) = Field(..., description="工具函数")
    custom_run: bool = Field(
        default=False,
        description="是否自定义运行，如果启用则会传入Context类而不是dict，并且不会强制要求返回值。",
    )
