from __future__ import annotations

from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from nonebot import logger

from ..config import Config, ModelPreset


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
    async def call_api(self, messages: Iterable[Any]) -> str:
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def get_adapter_protocol() -> str | tuple[str, ...]:
        raise NotImplementedError

    @property
    def protocol(self):
        """获取适配器协议"""
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
        try:
            protocol = adapter.get_adapter_protocol()
        except NotImplementedError as e:
            logger.error(
                f"Adapter {adapter.__name__} does not implement get_adapter_protocol: {e}"
            )
            return
        override = adapter.__override__ if hasattr(adapter, "__override__") else False
        if isinstance(protocol, str):
            if protocol in self._adapter_class:
                if not override:
                    raise ValueError(f"适配器协议 {protocol} 已经被注册")
                logger.warning(
                    f"适配器协议 {protocol} 已经被{self._adapter_class[protocol].__name__}注册，覆盖原有适配器"
                )

            self._adapter_class[protocol] = adapter
        elif isinstance(protocol, tuple):
            for p in protocol:
                if not isinstance(p, str):
                    raise TypeError("适配器协议必须是字符串或字符串元组")
                if p in self._adapter_class:
                    if not override:
                        raise ValueError(f"适配器协议 {p} 已经被注册")
                    logger.warning(
                        f"适配器协议 {p} 已经被{self._adapter_class[p].__name__}注册，覆盖原有适配器"
                    )
                self._adapter_class[p] = adapter
