from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionTemp(BaseModel):
    message_id: int
    timestamp: datetime = Field(default_factory=datetime.now)


@dataclass
class ChatManager:
    debug: bool = False
    session_clear_group: dict[str, SessionTemp] = field(default_factory=dict)
    session_clear_user: dict[str, SessionTemp] = field(default_factory=dict)
    custom_menu: list[dict[str, str]] = field(default_factory=list)
    running_messages_poke: dict[str, Any] = field(default_factory=dict)
    menu_msg: str = "聊天功能菜单:\n" + "/聊天菜单 唤出菜单 \n"
    menu_msg += "/del_memory 丢失这个群/聊天的记忆 \n"
    menu_msg += "/enable 在群聊启用聊天 \n"
    menu_msg += "/disable 在群聊里关闭聊天\n"
    menu_msg += "/prompt <arg> [text] 设置聊群自定义补充prompt（--(show) 展示当前提示词，--(clear) 清空当前prompt，--(set) [文字]则设置提示词，e.g.:/prompt --(show)）,/prompt --(set) [text]。）\n"
    menu_msg += "/sessions指令帮助：\n"
    menu_msg += "set：覆盖当前会话为指定编号的会话\n"
    menu_msg += "del：删除指定编号的会话\n"
    menu_msg += "archive：归档当前会话\n"
    menu_msg += "clear：清空所有会话\n"
    menu_msg += "Preset帮助：\n"
    menu_msg += "/presets 列出所有读取到的模型预设\n"
    menu_msg += (
        "/set_preset 或 /设置预设 或 /设置模型预设  <预设名> 设置当前使用的预设\n"
    )
    menu_msg += "/prompts 展示当前的prompt预设\n"
    menu_msg += (
        "/choose_prompt <group/private> <预设名称> 设置群聊/私聊的全局提示词预设\n"
    )
    menu_msg += "/fakepeople <on/off>模拟聊天"
    menu_msg += "/insights [global] 获取当前群聊/私聊的用量，参数：global(可选)"


chat_manager = ChatManager()
