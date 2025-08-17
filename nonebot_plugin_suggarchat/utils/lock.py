import asyncio
from functools import lru_cache


@lru_cache(maxsize=1024)
def get_group_lock(_: int) -> asyncio.Lock:
    return asyncio.Lock()


@lru_cache(maxsize=1024)
def get_private_lock(_: int) -> asyncio.Lock:
    return asyncio.Lock()


@lru_cache(maxsize=2048)
def database_lock(*args, **kwargs) -> asyncio.Lock:
    return asyncio.Lock()
