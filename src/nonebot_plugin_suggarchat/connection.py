from importlib import metadata

from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import Bot

from . import config
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()


@driver.on_bot_connect
async def onConnect(bot: Bot):
    await run_hooks(bot)


@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    kernel_version = metadata.version("nonebot_plugin_suggarchat")
    config.__KERNEL_VERSION__ = kernel_version
    logger.info(f"Loading SuggarChat V{kernel_version}")
    await config_manager.load()
    logger.info("Start successfully!Waitting for bot connection...")
