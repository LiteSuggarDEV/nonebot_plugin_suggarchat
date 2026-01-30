from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from nonebot.adapters.onebot.v11 import Bot
from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

from ...event import SuggarEvent
from ...matcher import Matcher

T = TypeVar("T", str, int, float, bool, list, dict)  # JSON类型
JOT_T = TypeVar(
    "JOT_T",
    Literal["string"],
    Literal["number"],
    Literal["integer"],
    Literal["boolean"],
    Literal["array"],
    Literal["object"],
)
NUM_T = TypeVar("NUM_T", int, float)
JSON_OBJECT_TYPE = Literal[
    "string",
    "number",
    "integer",
    "boolean",
    "array",
    "object",
]


def on_none(value: Any | None) -> bool:
    """用于Pydantic的exclude_if

    Args:
        value (Any | None): 待判断的值

    Returns:
        bool: 当Value为None返回True
    """
    return value is None


def cast_mcp_properties_to_openai(
    property: dict[str, MCP_OBJECT_TYPE],
) -> dict[str, FunctionPropertySchema]:
    """
    将MCPPropertySchemaObject字典转换为FunctionPropertySchema对象
    """
    properties_dict: dict[str, FunctionPropertySchema] = {}

    for key, prop in deepcopy(property).items():
        # 根据MCP属性类型转换为相应的FunctionPropertySchema
        converted_prop = _convert_single_property(prop)
        properties_dict[key] = converted_prop

    return properties_dict


def _convert_single_property(mcp_prop: MCP_OBJECT_TYPE) -> FunctionPropertySchema:
    """
    将单个MCP_PROPERTY转换为FunctionPropertySchema
    """
    # 获取基本属性
    description = getattr(
        mcp_prop,
        "description",
        "No description",
    )
    prop_type: JSON_OBJECT_TYPE = mcp_prop.type

    # 准备基础参数
    base_params = {
        "type": prop_type,
        "description": description,
    }

    # 如果有枚举值，添加到参数中
    if hasattr(mcp_prop, "enum") and mcp_prop.enum is not None:
        base_params["enum"] = mcp_prop.enum

    if isinstance(mcp_prop, MCPPropertySchemaObject):
        # 对象类型需要递归转换其属性
        if hasattr(mcp_prop, "properties") and mcp_prop.properties:
            obj_properties = {}
            for key, sub_prop in mcp_prop.properties.items():
                obj_properties[key] = _convert_single_property(sub_prop)
            base_params["properties"] = obj_properties
        if hasattr(mcp_prop, "required") and mcp_prop.required:
            base_params["required"] = mcp_prop.required

    elif isinstance(mcp_prop, MCPPropertySchemaArray):
        if hasattr(mcp_prop, "items"):
            base_params["items"] = _convert_single_property(mcp_prop.items)
        if hasattr(mcp_prop, "minItems") and mcp_prop.minItems > 0:
            base_params["minItems"] = mcp_prop.minItems
        if hasattr(mcp_prop, "maxItems") and mcp_prop.maxItems < 100:
            base_params["maxItems"] = mcp_prop.maxItems
        if hasattr(mcp_prop, "uniqueItems"):
            base_params["uniqueItems"] = mcp_prop.uniqueItems

    # 对于数值和布尔类型，不需要额外的字段，因为FunctionPropertySchema不包含minimum/maximum等字段
    return FunctionPropertySchema(**base_params)


class MCPPropertySchema(BaseModel, Generic[JOT_T]):
    """MCP属性的基础结构定义"""

    type: JOT_T = Field(..., description="参数类型")
    title: str = Field("NO_TITLE", description="参数标题")
    description: str = Field(default="No description", description="参数描述")
    default: None = Field(default=None, description="参数默认值", exclude_if=on_none)
    enum: list[str | int | float] | None = Field(
        default=None, description="枚举的参数", exclude_if=on_none
    )


class MCPPropertySchemaString(MCPPropertySchema[Literal["string"]]):
    """校验字符串类型的MCP属性结构"""

    pattern: str | None = Field(
        default=None, description="正则表达式", exclude_if=on_none
    )
    minLength: int = Field(default=0, description="最小长度")
    maxLength: int = Field(default=100, description="最大长度")


class MCPPropertySchemaNumeric(MCPPropertySchema[JOT_T], Generic[JOT_T, NUM_T]):
    """校验数值类型的MCP属性结构"""

    minimum: NUM_T | None = Field(
        default=None, description="最小值", exclude_if=on_none
    )
    maximum: NUM_T | None = Field(
        default=None, description="最大值", exclude_if=on_none
    )
    exclusiveMinimum: bool | None = Field(
        default=None,
        description="最小值是否被不包含（即'左开区间'）",
        exclude_if=on_none,
    )
    exclusiveMaximum: bool | None = Field(
        default=None,
        description="最大值是否被不包含（即'右开区间'）",
        exclude_if=on_none,
    )


class MCPPropertySchemaInteger(MCPPropertySchemaNumeric[Literal["integer"], int]):
    """校验整数类型的MCP属性结构"""


class MCPPropertySchemaNumber(MCPPropertySchemaNumeric[Literal["number"], float]):
    """校验浮点数类型的MCP属性结构"""


class MCPPropertySchemaObject(MCPPropertySchema[Literal["object"]]):
    """校验对象类型的MCP属性结构"""

    properties: dict[str, MCP_OBJECT_TYPE] = Field(
        ..., description="参数属性定义", exclude_if=on_none
    )
    required: list[str] = Field(default_factory=list, description="必填参数列表")

    @model_validator(mode="after")
    def validator(self) -> Self:
        if self.required:
            for req in self.required:
                if req not in self.properties:
                    raise ValueError(
                        f"Required property '{req}' not found in properties."
                    )
        return self


class MCPPropertySchemaArray(MCPPropertySchema[Literal["array"]]):
    """校验数组类型的MCP属性结构"""

    items: MCP_OBJECT_TYPE = Field(..., description="参数属性定义", exclude_if=on_none)
    maxItems: int = Field(default=100, description="最大元素数量")
    minItems: int = Field(default=0, description="最小元素数量")
    uniqueItems: bool = Field(
        default=False,
        description="是否要求数组元素唯一，当类型为array时，此参数有效默认为False",
    )


class MCPPropertySchemaBoolean(MCPPropertySchema[Literal["boolean"]]):
    """校验布尔类型的MCP属性结构"""


MCP_OBJECT_TYPE = (
    MCPPropertySchemaObject
    | MCPPropertySchemaString
    | MCPPropertySchemaNumber
    | MCPPropertySchemaInteger
    | MCPPropertySchemaArray
    | MCPPropertySchemaBoolean
)


class MCPToolSchema(BaseModel):
    """定义MCP工具的结构"""

    name: str = Field(..., description="工具名称")
    description: str = Field("No description", description="工具描述")
    inputSchema: MCPPropertySchemaObject = Field(..., description="工具参数定义")


class FunctionPropertySchema(BaseModel, Generic[T]):
    """校验函数参数的属性"""

    type: Literal[JSON_OBJECT_TYPE] | list[JSON_OBJECT_TYPE] = Field(
        ..., description="参数类型"
    )
    description: str = Field("No description", description="参数描述")
    enum: list[T] | None = Field(
        default=None, description="枚举的参数", exclude_if=on_none
    )
    properties: dict[str, FunctionPropertySchema] | None = Field(
        default=None,
        description="参数属性定义,仅当参数类型为object时有效",
        exclude_if=on_none,
    )
    items: FunctionPropertySchema | None = Field(
        default=None,
        description="仅当type='array'时使用，定义数组元素类型",
        exclude_if=on_none,
    )
    minItems: int | None = Field(
        default=None,
        description="仅当type='array'时使用，定义数组的最小长度",
        exclude_if=on_none,
    )
    maxItems: int | None = Field(
        default=None,
        description="仅当type='array'时使用，定义数组元素数量最大长度",
        exclude_if=on_none,
    )
    uniqueItems: bool | None = Field(
        default=None,
        description="是否要求数组元素唯一，当类型为array时，此参数有效默认为False",
        exclude_if=on_none,
    )
    required: list[str] | None = Field(
        default=None,
        description="参数属性定义,仅当参数类型为object时有效",
        exclude_if=on_none,
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
        default=None, description="参数属性定义", exclude_if=on_none
    )

    required: list[str] = Field(default_factory=list, description="必需参数列表")


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
    on_call: Literal["hide", "show"] = Field(
        default="show",
        description="是否显示此工具调用",
    )
    enable_if: Callable[[], bool] = Field(
        default=lambda: True,
        description="是否启用此工具",
    )
