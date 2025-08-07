from importlib import metadata

from nonebot import get_driver, logger

from . import config
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()
__LOGO = r"""
 __  _ _  __   __   _   ___
/ _|| | |/ _| / _| / \ | o \
\_ \| U ( |_n( |_n| o ||   /
|__/|___|\__/ \__/|_n_||_|\\"""

@driver.on_bot_connect
async def hook():
    logger.debug("运行钩子...")
    await run_hooks()


@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    logger.info(__LOGO)
    try:
        kernel_version = metadata.version("nonebot_plugin_suggarchat")
        config.__kernel_version__ = kernel_version
        logger.info(f"正在加载 SuggarChat V{kernel_version}")
    except Exception:
        logger.warning("无法获取到版本！SuggarChat似乎并没有以pypi包方式运行。")
    logger.debug("加载配置文件...")
    await config_manager.load()
    logger.debug("成功启动！")
