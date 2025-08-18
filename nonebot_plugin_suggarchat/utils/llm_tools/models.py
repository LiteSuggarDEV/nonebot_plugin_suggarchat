from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationInfo, field_validator

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
    items: dict[str, FunctionPropertySchema] | None = Field(
        default=None, description="仅当type='array'时使用，定义数组元素类型"
    )
    minItems: int | None = Field(
        default=None, description="仅当type='array'时使用，定义数组的最小长度"
    )
    maxItems: int | None = Field(
        default=None, description="仅当type='array'时使用，定义数组元素数量最大长度"
    )
    uniqueItems: bool | None = Field(default=None, description="是否要求数组元素唯一")
    required: list[str] = Field(
        default_factory=list, description="参数属性定义,仅当参数类型为object时有效"
    )

    @field_validator(
        "properties",
    )
    def validate_properties_and_items(cls, v: dict[str, Any], info: ValidationInfo):
        if v is not None:
            # 检查properties非空时type必须为object
            if v and info.data.get("type") != "object":
                raise ValueError("When properties is not empty, type must be object")
            elif info.data.get("items") is not None:
                raise ValueError("Cannot specify both properties and items")
            elif (
                info.data.get("minItems") is not None
                or info.data.get("maxItems") is not None
                or info.data.get("uniqueItems") is not None
            ):
                raise ValueError(
                    "Cannot specify minItems, maxItems, or uniqueItems for an object"
                )
            for key, value in v.items():
                if not isinstance(value, FunctionPropertySchema):
                    raise ValueError(f"Invalid value for {key}: {value}")
        return v

    @field_validator("items")
    def validate_items(cls, v: dict[str, Any], info: ValidationInfo):
        if v is not None:
            # 检查items非空时type必须为array
            if v and info.data.get("type") != "array":
                raise ValueError("When items is not empty, type must be array")
            elif info.data.get("properties") is not None:
                raise ValueError("items and properties cannot be used together")
            elif info.data.get("required") is not None:
                raise ValueError("items and required cannot be used together")
            for key, value in v.items():
                if not isinstance(value, FunctionPropertySchema):
                    raise ValueError(f"Invalid value for {key}: {value}")
        return v


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

    type: Literal["function"] = Field(
        default="function", description="工具类型必须是function"
    )
    function: FunctionDefinitionSchema = Field(..., description="函数定义")
    strict: bool = Field(default=False, description="是否严格模式")


class ToolContext(BaseModel):
    data: dict[str, Any]
    event: SuggarEvent
    matcher: Matcher = Field(..., description="当前SuggarMatcher对象")


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
