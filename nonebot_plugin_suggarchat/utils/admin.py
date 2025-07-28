import sys

import nonebot
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
)

from ..config import config_manager


async def send_to_admin_as_error(msg: str, bot: Bot | None = None) -> None:
    logger.error(msg)
    await send_to_admin(msg, bot)


async def send_to_admin(msg: str, bot: Bot | None = None) -> None:
    """发送消息给管理员"""
    # 检查是否允许发送消息给管理员
    if not config_manager.config.admin.allow_send_to_admin:
        return
    # 检查管理员群号是否已配置
    if config_manager.config.admin.admin_group == 0:
        try:
            raise RuntimeWarning("管理员群组未设定！")
        except Exception:
            # 记录警告日志
            logger.warning(f'管理员群组未设定，消息 "{msg}" 不会被发送！')
            exc_type, exc_value, _ = sys.exc_info()
            logger.exception(f"{exc_type}:{exc_value}")
        return
    # 发送消息到管理员群
    if bot:
        await bot.send_group_msg(
            group_id=config_manager.config.admin.admin_group, message=msg
        )
    else:
        await (nonebot.get_bot()).send_group_msg(
            group_id=config_manager.config.admin.admin_group, message=msg
        )
