import asyncio
from collections.abc import Awaitable, Callable

from nonebot import logger

hook_registry: list[Callable[..., None] | Callable[..., Awaitable[None]]] = []


def register_hook(hook_func: Callable[[], None] | Callable[[], Awaitable[None]]):
    if hook_func not in hook_registry:
        hook_registry.append(hook_func)
        logger.info(f"钩子注册: {hook_func.__module__}，{hook_func.__name__}")


async def run_hooks():
    for hook in hook_registry:
        if callable(hook):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.exception(e)
