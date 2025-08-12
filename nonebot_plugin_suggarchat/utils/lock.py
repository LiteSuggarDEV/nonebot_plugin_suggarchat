import asyncio
from collections import defaultdict
from functools import lru_cache
from typing import overload

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


@overload
def rw_lock(*, user_id: int) -> asyncio.Lock: ...


@overload
def rw_lock(*, group_id: int) -> asyncio.Lock: ...


@overload
def rw_lock(event: Event) -> asyncio.Lock: ...


def rw_lock(
    event: Event | None = None,
    *,
    user_id: int | None = None,
    group_id: int | None = None,
) -> asyncio.Lock:
    """
    获取读写锁
    :return: asyncio.Lock
    """
    if event:
        return (
            _G_Lock[event.group_id]
            if isinstance(event, GroupEvent)
            else _P_Lock[int(event.get_user_id())]
        )
    elif user_id:
        return _P_Lock[user_id]
    elif group_id:
        return _G_Lock[group_id]
    else:
        raise ValueError("event or user_id or group_id must be provided")
