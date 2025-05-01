from dataclasses import dataclass
from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    MessageEvent,
    PokeNotifyEvent,
)
from typing import List

@dataclass
class EventType:
    CHAT: str = "chat"
    NONE: str = ""
    POKE: str = "poke"
    BEFORE_CHAT: str = "before_chat"
    BEFORE_POKE: str = "before_poke"


class BasicEvent:
    """
    所有事件的基类
    """
    def __init__(self):
        pass


class SuggarEvent(BasicEvent):
    """
    与消息收发相关的事件基类
    """
    def __init__(self, model_response: List[str], nbevent: Event, user_id: int, send_message: List[str]):
        """
        初始化 SuggarEvent 对象

        :param model_response: 模型的响应文本列表
        :param nbevent: NoneBot 事件对象
        :param user_id: 用户 ID
        :param send_message: 发送的模型上下文
        """
        self._event_type = EventType.NONE
        self._nbevent = nbevent
        self._modelResponse = model_response
        self._user_id = user_id
        self._send_message = send_message

    def __str__(self):
        """
        返回 SuggarEvent 对象的字符串表示
        """
        return f"SUGGAREVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @property
    def event_type(self) -> str:
        """
        获取事件类型
        :return: 事件类型标识字符串
        """
        return self._event_type

    @property
    def model_response(self) -> str:
        """
        获取模型响应文本
        :return: 模型响应文本
        """
        return self._modelResponse[0]

    @model_response.setter
    def model_response(self, value: str):
        """
        设置模型响应文本
        """
        self._modelResponse[0] = value

    @property
    def message(self) -> List[str]:
        """
        获取传入到模型的上下文
        :return: 消息内容
        """
        return self._send_message

    @property
    def user_id(self) -> int:
        """
        获取用户 ID
        :return: 用户 ID
        """
        return self._user_id

    def get_nonebot_event(self) -> Event:
        """
        获取 NoneBot 事件对象
        :return: NoneBot 事件对象
        """
        return self._nbevent


class BaseSuggarEvent(SuggarEvent):
    def __init__(self, event_type: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_type = event_type

    @property
    def event_type(self) -> str:
        """
        获取事件类型
        :return: 事件类型标识字符串
        """
        return self._event_type


class ChatEvent(BaseSuggarEvent):
    def __init__(self, *args, **kwargs):
        super().__init__(EventType.CHAT, *args, **kwargs)

    def __str__(self):
        """
        返回 ChatEvent 对象的字符串表示
        """
        return f"SUGGARCHATEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"


class PokeEvent(BaseSuggarEvent):
    def __init__(self, *args, **kwargs):
        super().__init__(EventType.POKE, *args, **kwargs)

    def __str__(self):
        """
        返回 PokeEvent 对象的字符串表示
        """
        return f"SUGGARPOKEEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"


class BeforeChatEvent(ChatEvent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_type = EventType.BEFORE_CHAT


class BeforePokeEvent(PokeEvent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_type = EventType.BEFORE_POKE


class FinalObject:
    """
    最终返回的对象
    """
    def __init__(self, send_message: List[str]):
        self.__message = send_message

    @property
    def message(self) -> List[str]:
        return self.__message
