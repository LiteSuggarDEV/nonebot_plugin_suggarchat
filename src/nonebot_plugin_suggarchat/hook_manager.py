from collections.abc import Callable

from nonebot import logger
from nonebot.adapters import Bot

hook_registry: list[Callable] = []


def register_hook(hook_func: Callable):
    hook_registry.append(hook_func)
    logger.info(f"钩子注册: {hook_func.__module__}，{hook_func.__name__}")


async def run_hooks(bot: Bot):
    for hook in hook_registry:
        await hook()
