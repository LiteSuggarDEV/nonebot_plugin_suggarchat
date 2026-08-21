from nonebot.plugin import PluginMetadata, require

require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")
require("nonebot_plugin_amrita")

from . import (
    builtin_hook,
    config,
    handlers,
    matcher_manager,
    preprocess,
)

__all__ = [
    "builtin_hook",
    "config",
    "handlers",
    "matcher_manager",
    "preprocess",
]

__plugin_meta__ = PluginMetadata(
    name="SuggarChat Agent聊天插件",
    description="基于AmritaCore的强大的智能体聊天插件",
    usage="https://docs.suggar.top/project/suggarchat/",
    homepage="https://github.com/LiteSuggarDEV/nonebot_plugin_suggarchat/",
    type="application",
    supported_adapters={"~onebot.v11"},
)
