from nonebot.plugin import require

require("nonebot_plugin_suggarchat")
from . import (
    example,
    example_change_model_msg,
    example_matcher_usage,
    example_reg_config,
)

__all__ = [
    "example",
    "example_change_model_msg",
    "example_matcher_usage",
    "example_reg_config",
]
