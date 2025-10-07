from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from nonebot import logger

from ..config import Config, ModelPreset
from .llm_tools.models import ToolChoice, ToolFunctionSchema
from .models import ToolCall, UniResponse


@dataclass
class ModelAdapter:
    """模型适配器基础类"""

    preset: ModelPreset
    config: Config
    __override__: bool = False  # 是否允许覆盖现有适配器

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if not getattr(cls, "__abstract__", False):
            AdapterManager().register_adapter(cls)

    @abstractmethod
    async def call_api(self, messages: Iterable[Any]) -> UniResponse[str, None]: ...

    async def call_tools(
        self,
        messages: Iterable,
        tools: list[ToolFunctionSchema],
        tool_choice: ToolChoice | None = None,
    ) -> UniResponse[None, list[ToolCall] | None]:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_adapter_protocol() -> str | tuple[str, ...]: ...

    @property
    def protocol(self):
        """获取模型协议适配器"""
        return self.get_adapter_protocol()


class AdapterManager:
    __instance = None
    _adapter_class: dict[str, type[ModelAdapter]]

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = super().__new__(cls)
            cls.__instance._adapter_class = {}
        return cls.__instance

    def get_adapters(self) -> dict[str, type[ModelAdapter]]:
        """获取所有注册的适配器"""
        return self._adapter_class

    def safe_get_adapter(self, protocol: str) -> type[ModelAdapter] | None:
        """获取适配器"""
        return self._adapter_class.get(protocol)

    def get_adapter(self, protocol: str) -> type[ModelAdapter]:
        """获取适配器"""
        if protocol not in self._adapter_class:
            raise ValueError(f"No adapter found for protocol {protocol}")
        return self._adapter_class[protocol]

    def register_adapter(self, adapter: type[ModelAdapter]):
        """注册适配器"""
        protocol = adapter.get_adapter_protocol()
        override = adapter.__override__ if hasattr(adapter, "__override__") else False
        if isinstance(protocol, str):
            if protocol in self._adapter_class:
                if not override:
                    raise ValueError(f"模型协议适配器 {protocol} 已经被注册")
                logger.warning(
                    f"模型协议适配器 {protocol} 已经被{self._adapter_class[protocol].__name__}注册，覆盖原有适配器"
                )

            self._adapter_class[protocol] = adapter
        elif isinstance(protocol, tuple):
            for p in protocol:
                if not isinstance(p, str):
                    raise TypeError("模型协议适配器必须是字符串或字符串元组")
                if p in self._adapter_class:
                    if not override:
                        raise ValueError(f"模型协议适配器 {p} 已经被注册")
                    logger.warning(
                        f"模型协议适配器 {p} 已经被{self._adapter_class[p].__name__}注册，覆盖原有适配器"
                    )
                self._adapter_class[p] = adapter
