from nonebot import logger
from openai.types.chat.chat_completion_tool_choice_option_param import (
    ChatCompletionToolChoiceOptionParam,
)

from .chatmanager import chat_manager
from .config import Config, ConfigManager, config_manager
from .utils.admin import send_to_admin
from .utils.libchat import (
    AdapterManager,
    ModelAdapter,
    get_chat,
    tools_caller,
)
from .utils.tokenizer import Tokenizer, hybrid_token_count

__all__ = [
    "AdapterManager",
    "ConfigManager",
    "ModelAdapter",
    "Tokenizer",
    "config_manager",
    "hybrid_token_count",
    "tools_caller",
]


class Menu:
    """
    Menu 类用于通过注册菜单项来构建菜单。
    """

    def reg_menu(self, cmd_name: str, describe: str, args: str = "") -> "Menu":
        """
        注册一个新的菜单项。

        参数:
        - cmd_name (str): 菜单项的命令名称。
        - describe (str): 菜单项的描述。

        返回:
        - Menu: 返回 Menu 类的实例，支持方法链式调用。
        """
        chat_manager.menu_msg += f"/{cmd_name} {args} 说明：{describe} \n"
        return self

    @property
    def menu(self) -> str:
        """
        获取菜单项。
        """
        return chat_manager.menu_msg


class Admin:
    """
    管理员管理类，负责处理与管理员相关的操作，如发送消息、错误处理和管理员权限管理。
    """

    config: Config

    def __init__(self):
        """
        构造函数
        """
        self.config = config_manager.ins_config

    async def send_with(self, msg: str) -> "Admin":
        """
        异步发送消息给管理员。

        参数:
        - msg (str): 要发送的消息内容。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        await send_to_admin(msg)
        return self

    async def send_error(self, msg: str) -> "Admin":
        """
        异步发送错误消息给管理员，并记录错误日志。

        参数:
        - msg (str): 要发送的错误消息内容。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        logger.error(msg)
        await send_to_admin(msg)
        return self

    def is_admin(self, user_id: str) -> bool:
        """
        检查用户是否是管理员。

        参数:
        - user_id (str): 用户ID。

        返回:
        - bool: 用户是否是管理员。
        """
        return int(user_id) in self.config.admin.admins

    def add_admin(self, user_id: int) -> "Admin":
        """
        添加新的管理员用户ID到配置中。

        参数:
        - user_id (int): 要添加的用户ID。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        self.config.admin.admins.append(user_id)
        return self._save_config_to_toml()

    def set_admin_group(self, group_id: int) -> "Admin":
        """
        设置管理员组ID。

        参数:
        - group_id (int): 管理员组ID。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        self.config.admin.admin_group = group_id
        return self._save_config_to_toml()

    def _save_config_to_toml(self):
        self.config.save_to_toml(config_manager.toml_config)
        self.config = config_manager.ins_config
        return self


class Chat:
    """
    Chat 类用于处理与LLM相关操作，如获取消息。
    """

    config: Config

    def __init__(self):
        """
        构造函数
        """
        self.config = config_manager.ins_config

    async def get_msg(self, prompt: str, message: list):
        """
        获取LLM响应

        :param prompt[str]: 提示词
        :param message[list]: 消息列表
        """

        message.insert(0, {"role": "assistant", "content": prompt})
        return await self.get_msg_on_list(message)

    async def get_msg_on_list(self, message: list):
        """
        获取LLM响应

        :param message[list]: 消息列表
        """

        return await get_chat(messages=message)

    async def call_tools(
        self,
        messages: list,
        tools: list,
        tool_choice: ChatCompletionToolChoiceOptionParam | None = None,
    ):
        """
        调用工具

        :param messages: 消息列表
        :param tools: 工具列表
        :param tool_choice: 工具选择参数
        """
        return await tools_caller(
            messages=messages, tools=tools, tool_choice=tool_choice
        )
