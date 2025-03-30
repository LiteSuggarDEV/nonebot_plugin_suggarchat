import asyncio
from collections.abc import Awaitable, Callable

from nonebot import logger
from nonebot.adapters import Bot

hook_registry: list[Callable[..., None] | Callable[..., Awaitable[None]]] = []


def register_hook(hook_func: Callable[..., None] | Callable[..., Awaitable[None]]):
    hook_registry.append(hook_func)
    logger.info(f"钩子注册: {hook_func.__module__}，{hook_func.__name__}")


async def run_hooks(bot: Bot):
    for hook in hook_registry:
        if callable(hook):
            if asyncio.iscoroutinefunction(hook):
                await hook(bot)
            else:
                hook(bot)
        else:
            logger.warning(f"钩子 {hook} 不是可调用的")
