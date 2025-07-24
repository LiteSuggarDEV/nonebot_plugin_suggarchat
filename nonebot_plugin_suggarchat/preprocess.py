from importlib import metadata

from nonebot import get_driver, logger

from . import config
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()


@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    try:
        kernel_version = metadata.version("nonebot_plugin_suggarchat")
        config.__KERNEL_VERSION__ = kernel_version
    except Exception:
        logger.error("无法获取到版本!")
    logger.info(f"Loading SuggarChat V {kernel_version}")
    await config_manager.load()
    await run_hooks()
    logger.info("成功启动！")
