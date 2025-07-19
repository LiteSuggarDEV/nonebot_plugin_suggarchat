from importlib import metadata

from nonebot import get_driver, logger

from . import config
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()


@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    kernel_version = metadata.version("nonebot_plugin_suggarchat")
    config.__KERNEL_VERSION__ = kernel_version
    logger.info(f"Loading SuggarChat V{kernel_version}")
    await config_manager.load()
    await run_hooks()
    logger.info("Start successfully!Waitting for bot connection...")
