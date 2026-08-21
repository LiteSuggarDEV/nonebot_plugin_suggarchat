"""统一预设解析入口

消灭各调用点散落的 ``config_manager.get_preset(config.preset, cache=...)``
样板：默认取配置选中的预设，默认走缓存（``cache=True``）。
"""

from __future__ import annotations

from amrita_core import ModelPreset

from ..config import config_manager


async def resolve_preset(
    name: str | None = None, *, fix: bool = False, cache: bool = True
) -> ModelPreset:
    """解析预设名 → ``ModelPreset``。

    Args:
        name: 预设名；``None`` 时取配置选中的预设（``config.preset``）
        fix: 找不到时修正为 ``default`` 并持久化
        cache: 是否走磁盘预设缓存（默认 ``True``，热路径友好）
    """
    if name is None:
        name = config_manager.config.preset
    return await config_manager.presets.get_preset(name, fix=fix, cache=cache)
