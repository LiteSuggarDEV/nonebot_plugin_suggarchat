from nonebot import get_driver, logger

from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()

STARTUP_BANNER = r"""
 ____                                ____ _           _    __     ___  _
/ ___| _   _  __ _  __ _  __ _ _ __ / ___| |__   __ _| |_  \ \   / / || |
\___ \| | | |/ _` |/ _` |/ _` | '__| |   | '_ \ / _` | __|  \ \ / /| || |_
 ___) | |_| | (_| | (_| | (_| | |  | |___| | | | (_| | |_    \ V / |__   _|
|____/ \__,_|\__, |\__, |\__,_|_|   \____|_| |_|\__,_|\__|    \_/     |_|
             |___/ |___/
"""


@driver.on_bot_connect
async def hook():
    logger.debug("运行钩子...")
    await run_hooks()


@driver.on_startup
async def onEnable():
    logger.debug("加载配置文件...")
    print(STARTUP_BANNER)
    logger.info("SuggarChat V4 启动中...")
    # safe_get_config 触发 uniconf 的 _init → add_config 流程，
    # 由 on_reload 回调完成 config/ins_config 赋值后再加载。
    await config_manager.safe_get_config()
    logger.debug("成功启动！")
