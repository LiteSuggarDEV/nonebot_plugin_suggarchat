from nonebot import get_driver
from nonebot.plugin import require

require("nonebot_plugin_suggarchat")
from nonebot_plugin_suggarchat.API import Config


@get_driver().on_startup
async def startup():
    config = Config
    await config.reg_config("example")
    # 在主配置文件注册一个为example的配置文件项，此操作会自动重载配置文件。
    config.reg_model_config("example_model_config")
    # 在每个模型配置文件都注册一个为example_model_config的配置项，此操作会自动重载配置文件。
