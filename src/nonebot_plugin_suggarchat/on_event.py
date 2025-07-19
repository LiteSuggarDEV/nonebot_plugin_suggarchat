from .event import EventType
from .matcher import Matcher


def on_chat(*, priority: int = 10, block: bool = True):
    return Matcher(EventType().chat(), priority, block)


def on_poke(*, priority: int = 10, block: bool = True):
    return Matcher(EventType().poke(), priority, block)


def on_before_chat(*, priority: int = 10, block: bool = True):
    return Matcher(EventType().before_chat(), priority, block)


def on_before_poke(*, priority: int = 10, block: bool = True):
    return Matcher(EventType().before_poke(), priority, block)


def on_event(*, event_type: str, priority: int = 10, block: bool = True):
    return Matcher(event_type, priority, block)
