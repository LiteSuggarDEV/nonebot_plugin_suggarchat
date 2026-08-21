from nonebot import get_driver, logger

from .config import config_manager
from .hook_manager import run_hooks

driver = get_driver()


@driver.on_bot_connect
async def hook():
    logger.debug("运行钩子...")
    await run_hooks()


@driver.on_startup
async def onEnable():
    logger.debug("加载配置文件...")
    # safe_get_config 触发 uniconf 的 _init → add_config 流程，
    # 由 on_reload 回调完成 config/ins_config 赋值后再加载。
    await config_manager.safe_get_config()
    logger.debug("成功启动！")
