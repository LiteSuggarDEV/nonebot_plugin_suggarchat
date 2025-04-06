from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatManager:
    debug: bool = False
    session_clear_group: list[dict[str, Any]] = field(default_factory=list)
    session_clear_user: list[dict[str, Any]] = field(default_factory=list)
    custom_menu: list[dict[str, str]] = field(default_factory=list)
    running_messages_poke: dict[str, Any] = field(default_factory=dict)
    menu_msg: str = "聊天功能菜单:\n/聊天菜单 唤出菜单 \n/del_memory 丢失这个群/聊天的记忆 \n/enable 在群聊启用聊天 \n/disable 在群聊里关闭聊天\n/prompt <arg> [text] 设置聊群自定义补充prompt（--(show) 展示当前提示词，--(clear) 清空当前prompt，--(set) [文字]则设置提示词，e.g.:/prompt --(show)）,/prompt --(set) [text]。）\n/sessions指令帮助：\nset：覆盖当前会话为指定编号的会话\ndel：删除指定编号的会话\narchive：归档当前会话\nclear：清空所有会话\nPreset帮助：\n/presets 列出所有读取到的模型预设\n/set_preset 或 /设置预设 或 /设置模型预设  <预设名> 设置当前使用的预设"


chat_manager = ChatManager()
