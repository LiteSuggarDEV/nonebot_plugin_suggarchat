import asyncio
import sys
from collections.abc import Awaitable, Callable

from nonebot import logger

hook_registry: list[Callable[..., None] | Callable[..., Awaitable[None]]] = []


def register_hook(hook_func: Callable[..., None] | Callable[..., Awaitable[None]]):
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
            except Exception:
                logger.error(f"钩子 {hook} 执行失败！")
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error(
                    f"Exception type: {exc_type.__name__}"
                    if exc_type
                    else "Exception type: None"
                )
                logger.error(f"Exception message: {exc_value!s}")
                import traceback

                logger.error(
                    f"Detailed exception info:\n{''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}"
                )

        else:
            logger.warning(f"钩子 {hook} 不是可调用的")
