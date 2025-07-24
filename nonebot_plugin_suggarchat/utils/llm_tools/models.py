from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel, Field


class FunctionPropertySchema(BaseModel):
    """校验函数参数的属性"""

    type: str | list[str] = Field(..., description="参数类型")
    description: str = Field(..., description="参数描述")
    enum: list[str | int | float] | None = Field(default=None, description="枚举的参数")


class FunctionParametersSchema(BaseModel):
    """校验函数参数结构"""

    type: Literal["object"] = Field(..., description="参数类型必须是object")
    properties: dict[str, FunctionPropertySchema] = Field(
        ..., description="参数属性定义"
    )
    required: list[str] = Field([], description="必需参数列表")


class FunctionDefinitionSchema(BaseModel):
    """校验函数定义结构"""

    name: str = Field(..., description="函数名称")
    description: str = Field(..., description="函数描述")
    parameters: FunctionParametersSchema = Field(..., description="函数参数定义")
    strict: bool = Field(default=False, description="是否严格模式")


class ToolFunctionSchema(BaseModel):
    """校验完整的function字段结构"""

    type: Literal["function"] = Field(..., description="工具类型必须是function")
    function: FunctionDefinitionSchema = Field(..., description="函数定义")


class ToolData(BaseModel):
    """用于注册Tool的数据模型"""

    data: ToolFunctionSchema = Field(..., description="工具元数据")
    func: Callable[[dict[str, Any]], Awaitable[str]] = Field(
        ..., description="工具函数"
    )
