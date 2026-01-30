from typing import Protocol

from nonebot import logger

debug: bool = False


class CastToStringAble(Protocol):
    def __str__(self) -> str: ...


def debug_log(msg: CastToStringAble):
    global debug
    if debug:
        logger.debug(msg)
