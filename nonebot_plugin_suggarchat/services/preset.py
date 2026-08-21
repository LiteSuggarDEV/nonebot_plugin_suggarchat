"""预设解析领域服务。

负责"配置选中预设 + 磁盘预设"的解析、回退与校验语义，与磁盘访问
（``PresetStore``）解耦。热路径默认走缓存（``cache=True``），
热重载等需要强制刷新的场景显式传 ``cache=False``。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

from amrita_core import ModelPreset

from ..preset_store import PresetStore

if TYPE_CHECKING:
    from ..config import Config


class PresetService:
    """预设领域服务（由 ConfigManager 组合注入）"""

    def __init__(
        self,
        store: PresetStore,
        get_config: Callable[[], Config],
        get_ins_config: Callable[[], Config],
        save_config: Callable[[], Awaitable[None]],
    ) -> None:
        self._store = store
        self._get_config = get_config
        self._get_ins_config = get_ins_config
        self._save_config = save_config

    @property
    def _config(self) -> Config:
        """env 替换后的配置副本（读 default_preset 用）"""
        return self._get_config()

    @property
    def _ins_config(self) -> Config:
        """实际配置实例（fix 写回用）"""
        return self._get_ins_config()

    def validate(self) -> None:
        """校验目录下所有预设文件"""
        self._store.validate()

    async def get_all_presets(self, *, cache: bool = True) -> list[ModelPreset]:
        """获取全部预设（默认走缓存）。

        Args:
            cache: 是否使用磁盘预设缓存；热重载时显式传 ``False`` 强制刷新
        """
        return [
            self._config.default_preset,
            *(await self._store.load_all(cache=cache)),
        ]

    async def get_preset(
        self, preset: str, fix: bool = False, *, cache: bool = True
    ) -> ModelPreset:
        """解析预设名 → ``ModelPreset``。

        - ``"default"`` 直接返回配置默认预设（env 已替换）
        - 磁盘预设按名查找（默认缓存）
        - ``fix=True`` 且找不到时回退 ``default`` 并持久化写回

        Args:
            preset: 预设名称
            fix: 找不到时是否修正为 ``default`` 并保存配置
            cache: 是否使用磁盘预设缓存（默认 True）
        """
        if preset == "default":
            return self._config.default_preset
        if (model := await self._store.find(preset, cache=cache)) is not None:
            return model
        if fix:
            self._ins_config.preset = "default"
            await self._save_config()
        return await self.get_preset("default", fix, cache=cache)

    def get_preset_path(self, name: str) -> Path:
        """预设名对应的文件路径"""
        return self._store.path_of(name)

    def forget_preset(self, name: str) -> None:
        """移除预设名到路径的记录"""
        self._store.forget(name)
