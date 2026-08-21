"""提示词领域服务。

负责提示词加载、角色匹配与运行时训练数据（train dict）的访问，
与磁盘访问（``PromptStore``）解耦。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ..prompt_store import Prompts, PromptStore

if TYPE_CHECKING:
    from ..config import Config


class PromptService:
    """提示词领域服务（由 ConfigManager 组合注入）"""

    def __init__(
        self,
        store: PromptStore,
        get_ins_config: Callable[[], Config],
    ) -> None:
        self._store = store
        self._get_ins_config = get_ins_config

    @property
    def prompts(self) -> Prompts:
        """当前已加载的提示词集合"""
        return self._store.prompts

    async def get_prompts(
        self, cache: bool = False, load_only: bool = False
    ) -> Prompts:
        """加载提示词（磁盘读取；调用方需显式决定是否缓存）。

        Args:
            cache: 是否复用已加载结果
            load_only: 仅加载不写盘（热重载场景）
        """
        return await self._store.load(cache=cache, load_only=load_only)

    def load_prompt(self) -> None:
        """按配置的角色名匹配当前提示词（生成 group_train/private_train）"""
        cfg = self._get_ins_config()
        self._store.apply(cfg.group_prompt_character, cfg.private_prompt_character)

    @property
    def private_train(self) -> dict[str, str]:
        """私聊角色提示词（train dict）"""
        return self._store.private_train

    @property
    def group_train(self) -> dict[str, str]:
        """群聊角色提示词（train dict）"""
        return self._store.group_train
