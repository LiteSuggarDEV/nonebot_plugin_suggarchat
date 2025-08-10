from .event import EventTypeEnum
from .matcher import Matcher


def on_chat(*, priority: int = 10, block: bool = True):
    return Matcher(EventTypeEnum.CHAT, priority, block)


def on_poke(*, priority: int = 10, block: bool = True):
    return Matcher(EventTypeEnum.POKE, priority, block)


def on_before_chat(*, priority: int = 10, block: bool = True):
    return Matcher(EventTypeEnum.BEFORE_CHAT, priority, block)


def on_before_poke(*, priority: int = 10, block: bool = True):
    return Matcher(EventTypeEnum.BEFORE_POKE, priority, block)


def on_event(*, event_type: str, priority: int = 10, block: bool = True):
    return Matcher(event_type, priority, block)
