import asyncio
from collections import defaultdict
from functools import lru_cache

from nonebot.adapters.onebot.v11 import Event

from .event import GroupEvent

_G_Lock: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
_P_Lock: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


@lru_cache(maxsize=1024)
def get_group_lock(_: int) -> asyncio.Lock:
    return asyncio.Lock()


@lru_cache(maxsize=1024)
def get_private_lock(_: int) -> asyncio.Lock:
    return asyncio.Lock()


def rw_lock(event: Event) -> asyncio.Lock:
    """
    获取读写锁
    :return: asyncio.Lock
    """
    return (
        _G_Lock[event.group_id]
        if isinstance(event, GroupEvent)
        else _P_Lock[int(event.get_user_id())]
    )
