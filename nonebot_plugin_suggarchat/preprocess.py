from importlib import metadata

from nonebot import get_driver, logger

from . import config
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()

@driver.on_bot_connect
async def hook():
    await run_hooks()

@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    try:
        kernel_version = metadata.version("nonebot_plugin_suggarchat")
        config.__KERNEL_VERSION__ = kernel_version
    except Exception:
        logger.error("无法获取到版本!")
    logger.info(f"Loading SuggarChat V {kernel_version}")
    logger.info("加载配置文件...")
    await config_manager.load()
    logger.info("运行钩子...")
    logger.info("成功启动！")
