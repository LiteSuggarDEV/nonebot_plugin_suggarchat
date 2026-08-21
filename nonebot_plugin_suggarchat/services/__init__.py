"""领域服务层。

``ConfigManager`` 只负责配置读写/热重载，
预设/提示词/模型配置等业务语义下沉到独立领域服务，由 ConfigManager 组合。
"""

from .model import ModelConfigService
from .preset import PresetService
from .prompt import PromptService

__all__ = ["ModelConfigService", "PresetService", "PromptService"]
