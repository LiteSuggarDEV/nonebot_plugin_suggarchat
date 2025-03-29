from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    MessageEvent,
    PokeNotifyEvent,
)
from typing_extensions import override


class EventType:
    """
    EventType类用于定义和管理不同的事件类型。
    它封装了事件类型的字符串标识，提供了一种结构化的方式 来处理和获取事件类型。

    属性:
    __CHAT (str): 表示聊天事件的字符串标识。
    __None (str): 表示空事件或未定义事件的字符串标识。
    __POKE (str): 表示戳一戳事件的字符串标识。
    """

    __CHAT = "chat"
    __None = ""
    __POKE = "poke"
    __BEFORE_CHAT = "before_chat"
    __BEFORE_POKE = "before_poke"

    def __init__(self):
        """
        初始化EventType类的实例。
        目前初始化方法内没有实现具体操作。
        """
        return

    def chat(self):
        """
        获取聊天事件的字符串标识。

        返回:
        str: 聊天事件的字符串标识。
        """
        return self.__CHAT

    def before_chat(self):
        """
        获取聊天调用LLM前的的事件类型的字符串标识。

        返回:
        str: 聊天前的事件类型的字符串标识。
        """
        return self.__BEFORE_CHAT

    def before_poke(self):
        """
        获取戳一戳事件调用LLM前的类型的字符串标识。

        返回:
        str: 戳一戳前的事件类型的字符串标识。
        """
        return self.__BEFORE_POKE

    def none(self):
        """
        获取空事件或未定义事件的字符串标识。

        返回:
        str: 空事件或未定义事件的字符串标识。
        """
        return self.__None

    def poke(self):
        """
        获取戳一戳事件的字符串标识。

        返回:
        str: 戳一戳事件的字符串标识。
        """
        return self.__POKE

    def get_event_types(self):
        """
        获取所有事件类型的字符串标识列表。

        返回:
        list of str: 包含所有事件类型字符串标识的列表。
        """
        return [self.__CHAT, self.__None, self.__POKE]


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

    def __init__(
        self,
        model_response: list,
        nbevent: Event,
        user_id: int,
        send_message: list,
    ):
        """
        初始化SuggarEvent对象

        :param model_response: 模型的响应文本位于列表0的位置
        :param nbevent: NoneBot事件对象
        :param user_id: 用户ID
        :param send_message: 发送的模型的上下文
        """
        # 初始化事件类型为none
        self._event_type = EventType().none()
        # 保存NoneBot事件对象
        self._nbevent = nbevent
        # 初始化模型响应文本
        self._modelResponse: list = model_response
        # 这里使用列表是因为Python的底层指针允许列表对象引用同一块内存，所以可以修改列表中的元素，而不需要重新分配内存，这样就能实现修改模型的响应了。

        # 初始化用户ID
        self._user_id: int = user_id
        # 初始化要发送的消息内容
        self._send_message: list = send_message

    def __int__(self):
        """
        防止将对象转换为整数。

        异常:
            TypeError: 表示 SUGGAREVENT 不是一个数字，不应转换为整数。
        """
        raise TypeError("SUGGAREVENT is not a number")

    def __bool__(self):
        """
        防止将对象转换为布尔值。

        异常:
            TypeError: 表示 SUGGAREVENT 不是一个布尔值。
        """
        raise TypeError("SUGGAREVENT is not a bool")

    def __float__(self):
        """
        防止将对象转换为浮点数。

        异常:
            TypeError: 表示 SUGGAREVENT 不是一个浮点数。
        """
        raise TypeError("SUGGAREVENT is not a float")

    def __str__(self):
        """
        返回SuggarEvent对象的字符串表示
        """
        return f"SUGGAREVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @property
    def event_type(self) -> str:
        """
        获取事件类型

        :return: 事件类型字符串
        """
        return self._event_type

    def get_nonebot_event(self) -> Event:
        """
        获取NoneBot事件对象

        :return: NoneBot事件对象
        """
        return self._nbevent

    @property
    def message(self) -> list:
        """
        获取传入到模型的上下文

        :return: 消息内容
        """
        return self._send_message

    @property
    def user_id(self) -> int:
        """
        获取用户ID

        :return: 用户ID
        """
        return self._user_id

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

    def get_send_message(self) -> list:
        """
        获取传入到模型的上下文

        :return: 消息内容
        """
        return self._send_message

    def get_event_type(self) -> str:
        """
        获取事件类型，此方法在基类中未实现，应在子类中重写

        :raise NotImplementedError: 当方法未在子类中实现时抛出异常
        """
        raise NotImplementedError

    def get_model_response(self) -> str:
        """
        获取模型响应文本

        :return: 模型响应文本
        """
        return self._modelResponse[0]

    def get_user_id(self) -> int:
        """
        获取用户ID

        :return: 用户ID
        """
        return self._user_id

    def get_event_on_location(self):
        """
        获取事件发生的位置，此方法在基类中未实现，应在子类中重写

        :raise NotImplementedError: 当方法未在子类中实现时抛出异常
        """
        raise NotImplementedError


class ChatEvent(SuggarEvent):
    """
    聊天事件类，继承自SuggarEvent。

    该类用于处理聊天相关事件，封装了事件的各个属性，如消息事件、发送的消息、模型响应和用户ID。

    参数:
    - nbevent: MessageEvent - 消息事件对象，包含事件的相关信息。
    - send_message: list - 发送到模型的上下文。
    - model_response: str - 模型的响应内容。
    - user_id: int - 用户ID。
    """

    def __init__(
        self,
        nbevent: MessageEvent,
        send_message: list,
        model_response: list,
        user_id: int,
    ):
        """
        构造函数，初始化聊天事件对象。
        """
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        # 初始化事件类型为聊天事件
        self._event_type = EventType().chat()

    def __str__(self):
        """
        重写__str__方法，返回聊天事件对象的字符串表示。

        返回:
        字符串，包含事件类型、消息事件、模型响应、用户ID和发送到模型的上下文信息。
        """
        return f"SUGGARCHATEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @override
    def get_event_type(self) -> str:
        """
        获取事件类型。

        返回:
        字符串，表示事件类型为聊天事件。
        """
        return EventType().chat()

    @property
    def event_type(self) -> str:
        """
        事件类型属性，用于获取事件类型。

        返回:
        字符串，表示事件类型为聊天事件。
        """
        return EventType().chat()

    @override
    def get_event_on_location(self):
        """
        获取事件发生的位置。

        返回:
        字符串，如果是群聊消息事件，则返回"group"，否则返回"private"。
        """
        if isinstance(self._nbevent, GroupMessageEvent):
            return "group"
        else:
            return "private"


class PokeEvent(SuggarEvent):
    """
    继承自SuggarEvent的PokeEvent类，用于处理戳一戳事件。

    参数:
    - nbevent: PokeNotifyEvent类型，表示戳一戳通知事件。
    - send_message: list 发送到模型的上下文。
    - model_response: str类型，模型的响应。
    - user_id: int类型，用户ID。
    """

    def __init__(
        self,
        nbevent: PokeNotifyEvent,
        send_message: list,
        model_response: list,
        user_id: int,
    ):
        # 初始化PokeEvent类，并设置相关属性
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventType().poke()

    def __str__(self):
        # 重写__str__方法，返回PokeEvent的字符串表示
        return f"SUGGARPOKEEVENT({self._event_type},{self._nbevent},{self._modelResponse},{self._user_id},{self._send_message})"

    @property
    def event_type(self) -> str:
        # event_type属性，返回戳一戳事件类型
        return EventType().poke()

    @override
    def get_event_type(self) -> str:
        # 重写get_event_type方法，返回戳一戳事件类型
        return EventType().poke()

    @override
    def get_event_on_location(self):
        # 重写get_event_on_location方法，判断戳一戳事件发生的地点是群聊还是私聊
        if PokeNotifyEvent.group_id:
            return "group"
        else:
            return "private"


class BeforePokeEvent(PokeEvent):
    """
    继承自PokeEvent的BeforePokeEvent类，用于处理调用模型之前的事件，通常用于依赖注入或权限控制的写法中。
    参数:
    - nbevent: PokeNotifyEvent类型，表示戳一戳通知事件。
    - send_message: list 发送到模型的上下文。
    - model_response: str类型，模型的响应。
    - user_id: int类型，用户ID。
    """

    def __init__(
        self,
        nbevent: PokeNotifyEvent,
        send_message: list,
        model_response: list,
        user_id: int,
    ):
        # 初始化BeforePokeEvent类，并设置相关属性
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventType().before_poke()

    @property
    def event_type(self) -> str:
        # event_type属性，返回戳一戳事件类型
        return self._event_type

    @override
    def get_event_type(self) -> str:
        # 重写get_event_type方法，返回戳一戳事件类型
        return self._event_type


class BeforeChatEvent(ChatEvent):
    """
    继承自ChatEvent的BeforeChatEvent类，用于处理调用模型之前的事件，通常用于依赖注入或权限控制的写法中。
    参数:
    - nbevent: MessageEvent类型，表示消息事件。
    - send_message: list 发送到模型的上下文。
    - model_response: str类型，模型的响应。
    - user_id: int类型，用户ID。

    """

    def __init__(
        self,
        nbevent: MessageEvent,
        send_message: list,
        model_response: list,
        user_id: int,
    ):
        # 初始化BeforeChatEvent类，并设置相关属性
        super().__init__(
            model_response=model_response,
            nbevent=nbevent,
            user_id=user_id,
            send_message=send_message,
        )
        self._event_type = EventType().before_chat()

    @property
    def event_type(self) -> str:
        # event_type属性，返回聊天事件类型
        return self._event_type

    @override
    def get_event_type(self) -> str:
        # 重写get_event_type方法，返回聊天事件类型
        return self._event_type


class FinalObject:
    """
    最终返回的对象
    """

    def __init__(self, send_message: list):
        self.__message = send_message

    @property
    def message(self) -> list:
        return self.__message
