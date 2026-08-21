"""模型配置领域服务。

负责模型相关配置项的注册与预设 extra 字段的维护，
供 WebUI / 模型管理命令复用。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..preset_store import PresetStore

if TYPE_CHECKING:
    from ..config import Config


class ModelConfigService:
    """模型配置领域服务（由 ConfigManager 组合注入）"""

    def __init__(
        self,
        preset_store: PresetStore,
        get_ins_config: Callable[[], Config],
    ) -> None:
        self._preset_store = preset_store
        self._get_ins_config = get_ins_config

    def reg_model_config(self, key: str, default_value: Any = None) -> None:
        """注册模型配置项：写入默认预设 extra，并为全部已加载预设补默认值。

        Args:
            key: 配置项名称
            default_value: 默认值（None 时以字符串 ``"null"`` 落盘）
        """
        if default_value is None:
            default_value = "null"
        ins = self._get_ins_config()
        if key not in ins.default_preset.extra:
            ins.default_preset.extra.setdefault(key, default_value)
        self._preset_store.register_extra(key, default_value)
