# Todo: 重构Event类实现
from __future__ import annotations

import typing
from enum import Enum
from typing import Literal

from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    MessageEvent,
    PokeNotifyEvent,
)
from typing_extensions import override

from .utils.models import SEND_MESSAGES, SendMessageWrap


class EventTypeEnum(str, Enum):
    """
    EventTypeEnum类用于定义和管理不同的事件类型。
    它封装了事件类型的字符串标识，提供了一种结构化的方式 来处理和获取事件类型。

    """

    CHAT = "chat"
    Nil = ""
    POKE = "poke"
    BEFORE_CHAT = "before_chat"
    BEFORE_POKE = "before_poke"

    def validate(self, name: str) -> bool:
        return name in self


class BasicEvent:
    pass


class SuggarEvent(BasicEvent):
    def __init__(
        self,
        model_response: str,
        nbevent: Event,
        user_id: int,
        send_message: SEND_MESSAGES,
    ):
        # 初始化事件类型为none
        self._event_type = EventTypeEnum.Nil
        # 保存NoneBot事件对象
        self._nbevent = nbevent
        # 初始化模型响应文本
        self._modelResponse: list[str] = [model_response]
        # 初始化用户ID
        self._user_id: int = user_id
        # 使用SendMessageWrap校验并存储消息
        self._send_message: SendMessageWrap = SendMessageWrap.validate_messages(
            send_message
        )

    def __str__(self):
        return f"SUGGAREVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @property
    def event_type(self) -> str:
        return self._event_type

    def get_nonebot_event(self) -> Event:
        return self._nbevent

    @property
    def message(self) -> SendMessageWrap:
        return self._send_message

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def model_response(self) -> str:
        return self._modelResponse[0]

    @model_response.setter
    def model_response(self, value: str):
        self._modelResponse[0] = value

    def get_send_message(self) -> SendMessageWrap:
        return self._send_message

    def get_event_type(self) -> str:
        raise NotImplementedError

    def get_model_response(self) -> str:
        return self._modelResponse[0]

    def get_user_id(self) -> int:
        return self._user_id

    def get_event_on_location(self) -> Literal["group", "private"]:
        raise NotImplementedError


class ChatEvent(SuggarEvent):
    def __init__(
        self,
        nbevent: MessageEvent,
        send_message: SEND_MESSAGES,
        model_response: str,
        user_id: int,
    ):
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        # 初始化事件类型为聊天事件
        self._event_type = EventTypeEnum.CHAT

    def __str__(self):
        return f"SUGGARCHATEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @override
    def get_event_type(self) -> str:
        return EventTypeEnum.CHAT

    @property
    def event_type(self) -> str:
        return EventTypeEnum.CHAT

    @override
    def get_event_on_location(self) -> Literal["group", "private"]:
        return "group" if isinstance(self._nbevent, GroupMessageEvent) else "private"

    @property
    def event_message(self):
        return typing.cast(MessageEvent, self._nbevent).message


class PokeEvent(SuggarEvent):
    def __init__(
        self,
        nbevent: PokeNotifyEvent,
        send_message: SEND_MESSAGES,
        model_response: str,
        user_id: int,
    ):
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventTypeEnum.POKE

    def __str__(self):
        return f"SUGGARPOKEEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @property
    def event_type(self) -> str:
        return EventTypeEnum.POKE

    @override
    def get_event_type(self) -> str:
        return EventTypeEnum.POKE

    @override
    def get_event_on_location(self) -> Literal["group", "private"]:
        return "group" if getattr(self._nbevent, "group_id", None) else "private"


class BeforePokeEvent(PokeEvent):
    def __init__(
        self,
        nbevent: PokeNotifyEvent,
        send_message: SEND_MESSAGES,
        model_response: str,
        user_id: int,
    ):
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventTypeEnum.BEFORE_POKE

    @property
    def event_type(self) -> str:
        return self._event_type

    @override
    def get_event_type(self) -> str:
        return self._event_type


class BeforeChatEvent(ChatEvent):
    def __init__(
        self,
        nbevent: MessageEvent,
        send_message: SEND_MESSAGES,
        model_response: str,
        user_id: int,
    ):
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventTypeEnum.BEFORE_CHAT

    @property
    def event_type(self) -> str:
        return self._event_type

    @override
    def get_event_type(self) -> str:
        return self._event_type
