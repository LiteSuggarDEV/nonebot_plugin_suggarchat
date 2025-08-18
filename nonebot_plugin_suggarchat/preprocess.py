from importlib import metadata

from nonebot import get_driver, logger

from . import config
from .chatmanager import chat_manager
from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()
__LOGO = """\033[31m
 ___           ___    ___     _     ___
|   |  |   |  |   |  |   |   / \\   |   |
|___   |   |  |  __  |  __  |___|  |___|
    |  |   |  |   |  |   |  |   |  | \\
|___|  |___|  |___|  |___|  |   |  |  \\  \033[34mLoading SuggarChat \033[33mv‘{version}’......
\033[0m"""


@driver.on_bot_connect
async def hook():
    logger.debug("运行钩子...")
    await run_hooks()


@driver.on_startup
async def onEnable():
    kernel_version = "unknown"
    try:
        kernel_version = metadata.version("nonebot_plugin_suggarchat")
        config.__kernel_version__ = kernel_version
        if "dev" in kernel_version:
            logger.warning("当前版本为开发版本，可能存在不稳定情况！")
    except Exception:
        logger.warning(
            "无法获取到版本！SuggarChat似乎并没有以pypi包方式运行，Debug模式已自动开启。"
        )
        chat_manager.debug = True
    logger.info(__LOGO.format(version=kernel_version))
    logger.debug("加载配置文件...")
    await config_manager.load()
    config_manager.init_watch()
    logger.debug("成功启动！")
