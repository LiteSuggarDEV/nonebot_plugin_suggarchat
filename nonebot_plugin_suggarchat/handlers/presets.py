"""模型预设列表命令"""
from __future__ import annotations

from nonebot.matcher import Matcher

from ..config import ModelPreset, config_manager


def _format_preset_line(preset: ModelPreset) -> str:
    """格式化单个预设行（标记当前使用的）"""
    marker = "⭐ " if preset.name == config_manager.config.preset else "   "
    return f"{marker}{preset.name}（{preset.model}）"


async def presets(matcher: Matcher) -> None:
    """列出所有可用模型"""
    msg = f"当前模型：{config_manager.config.preset}\n\n可用模型：\n"
    for preset in await config_manager.get_all_presets():
        msg += _format_preset_line(preset) + "\n"
    await matcher.finish(msg)
