"""设置模型预设命令"""
from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager


async def set_preset(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """切换当前模型预设（无参数时重置为默认）"""
    arg = args.extract_plain_text().strip()
    if arg:
        for model in await config_manager.get_all_presets():
            if model.name == arg:
                config_manager.ins_config.preset = model.name
                await config_manager.save_config()
                await matcher.finish(f"已设置预设为：{model.name}，模型：{model.model}")
        await matcher.finish("未找到预设，请输入/presets查看预设列表。")
    config_manager.ins_config.preset = "default"
    await config_manager.save_config()
    await matcher.finish(
        f"已重置预设为：默认预设，模型：{config_manager.config.default_preset.model}。"
    )
