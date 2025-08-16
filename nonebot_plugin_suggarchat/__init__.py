from nonebot.plugin import PluginMetadata, require

require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")

from . import builtin_hook, config, matcher_manager, preprocess

__all__ = [
    "builtin_hook",
    "config",
    "matcher_manager",
    "preprocess",
]

__plugin_meta__ = PluginMetadata(
    name="SuggarChat 高可扩展性大模型聊天插件/框架",
    description="强大的聊天框架插件，内建OpenAI协议客户端实现，高可扩展性，多模型切换，事件API提供，DeepSeek/Gemini支持，多模态模型支持，适配Nonebot2-Onebot-V11适配器",
    usage="https://github.com/LiteSuggarDEV/nonebot_plugin_suggarchat/wiki",
    homepage="https://github.com/LiteSuggarDEV/nonebot_plugin_suggarchat/",
    type="application",
    supported_adapters={"~onebot.v11"},
)
