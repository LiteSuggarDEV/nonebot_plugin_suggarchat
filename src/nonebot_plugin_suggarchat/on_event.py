from .event import EventType
from .matcher import SuggarMatcher


def on_chat():
    return SuggarMatcher(event_type=EventType().chat())


def on_poke():
    return SuggarMatcher(event_type=EventType().poke())


def on_before_chat():
    return SuggarMatcher(event_type=EventType().before_chat())


def on_before_poke():
    return SuggarMatcher(event_type=EventType().before_poke())
