"""Chat 插件数据后端（AmritaCore MemoryBackend 实现）"""

from amrita_core import MemoryModel
from amrita_core.base.backend import AbilityBackend, MemoryBackend
from amrita_core.contexts import AbilityContext
from amrita_core.preset import MultiPresetManager
from amrita_core.tools.manager import MultiToolsManager
from amrita_core.tools.mcp import MultiClientManager
from nonebot_plugin_amrita.memory import (
    CachedUserDataRepository,
    MemorySchema,
)


class ChatMemoryBackend(MemoryBackend):
    """绑定本次会话已预加载/预处理的 ``MemorySchema`` 的记忆后端。

    与 ``nonebot_plugin_amrita.backends.AmritaMemoryBackend`` 同构：
    ``load_memory`` 返回预处理后的 ``memory_json``，``commit_memory``
    增量写回数据库。由 Core 工作流在 ``LOAD_STATE`` / ``COMMIT_MEMORY``
    节点自动调用，无需手动注入 / 回写 ``chat.data``。
    """

    repo = CachedUserDataRepository()

    def __init__(self, memory: MemorySchema):
        self.memory_val = memory

    async def load_memory(self, session_id: str) -> MemoryModel:
        del session_id
        return self.memory_val.memory_json

    async def commit_memory(self, session_id: str, memory: MemoryModel) -> None:
        del session_id
        if self.memory_val.memory_json is not memory:
            # 运行时 Core 传入的 memory 即来自 load_memory 的
            # MemoryModel 实例；此处做一次类型收窄以通过类型检查
            self.memory_val.memory_json = (
                memory
                if isinstance(memory, MemoryModel)
                else MemoryModel.model_validate(memory)
            )
        await self.repo.update_memory_data(self.memory_val)


class NoopAbilityBackend(AbilityBackend):
    """能力后端：构建本插件的实际能力容器。

    其中 ``load_presets`` 构建并返回一个以配置选中预设为默认预设的
    ``MultiPresetManager``，由 Core 在 ``LOAD_STATE`` 节点抓取，从而
    彻底脱离全局单例 ``PresetManager``（其默认预设受热重载 / 脏状态影响，
    且 Core 已改为 FailFast）。其余能力（MCP / tools / ability）由
    ``DatabackendOptions`` 决定是否抓取。
    """

    async def load_ability_all(self, session_id: str) -> AbilityContext:
        del session_id
        return AbilityContext()

    async def load_mcp_clients(self, session_id: str) -> MultiClientManager:
        del session_id
        return MultiClientManager()

    async def load_tools(self, session_id: str) -> MultiToolsManager:
        del session_id
        return MultiToolsManager()

    async def load_presets(self, session_id: str) -> MultiPresetManager:
        del session_id
        # 延迟导入避免与 config 模块产生循环依赖
        from .config import config_manager

        manager = MultiPresetManager()
        # 配置选中的预设即默认预设；set_default_preset 会自动登记进管理器
        manager.set_default_preset(config_manager.config.default_preset)
        return manager
