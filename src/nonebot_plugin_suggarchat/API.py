# 施工中。。。。。。敬请期待
from collections.abc import Callable
import json

from nonebot import logger

from nonebot_plugin_suggarchat.conf import get_custom_models_dir

from . import resources, suggar
from .resources import get_config, get_models, save_config
from .suggar import get_chat, reload_from_memory, send_to_admin


class Config:
    """用于处理Config注册的类"""

    def __init__(self):
        """
        初始化 Config 类的新实例。
        """
        pass

    def get_config(self, value: str | None = None):
        """
        获取配置。

        参数:

        :param value: (str|None): 配置键（不填则返回所有配置）。
        """
        if value == None:
            return get_config()
        else:
            return (get_config())[value]

    def set_config(self, key: str, value: str):
        """
        设置配置。

        :param key[str]: 配置键。
        :param value[str]: 配置值。
        """
        config = get_config()
        config[key] = value
        save_config(config)

    def add_model(self, file_name: str, data: dict):
        """
        添加模型。
        """
        path = get_custom_models_dir()
        file = path / f"{file_name}.json"
        if file.exists():
            raise FileExistsError("模型文件已存在")
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def get_models(self):
        """
        获取模型列表。

        返回:
        - list: 模型列表
        """
        return get_models()

    def reg_config(self, key: str):
        """
        注册一个配置项。

        :param key:
        """
        if key not in resources.__default_config__:
            resources.__default_config__[key] = None
            get_config()
            reload_from_memory()
        else:
            raise Exception(f"Config key {key} already exists!")

    def reg_model_config(self, key: str):
        """
        注册配置项到模型配置

        :param key: 配置项名
        """
        if key not in resources.__default_model_conf__:
            resources.__default_model_conf__[key] = None
            get_models()
            reload_from_memory()
        else:
            raise Exception(f"Config key {key} already exists!")


class Adapter:
    """用于处理Adapter注册的类"""

    def __init__(self):
        """
        初始化 Adapter 类的新实例。
        """
        pass

    def register_adapter(self, func: Callable, protocol: str):
        """
        注册一个适配器。
        """
        if not callable(func):
            raise TypeError("适配器必须是可调用的")
        if protocol in suggar.protocols_adapters:
            raise ValueError("协议适配器已存在")
        suggar.protocols_adapters[protocol] = func


class Menu:
    """
    Menu 类用于通过注册菜单项来构建菜单。
    """

    def __init__(self):
        """
        初始化 Menu 类的新实例。
        """
        pass

    def reg_menu(self, cmd_name: str, describe: str):
        """
        注册一个新的菜单项。

        参数:
        - cmd_name (str): 菜单项的命令名称。
        - describe (str): 菜单项的描述。

        返回:
        - Menu: 返回 Menu 类的实例，支持方法链式调用。
        """
        suggar.menu_msg += f"{cmd_name} \n"
        return self


class Admin:
    config: dict
    """
    管理员管理类，负责处理与管理员相关的操作，如发送消息、错误处理和管理员权限管理。
    """

    def __init__(self):
        """
        构造函数
        """
        self.config = get_config()

    async def send_with(self, msg: str):
        """
        异步发送消息给管理员。

        参数:
        - msg (str): 要发送的消息内容。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        await send_to_admin(msg)
        return self

    async def send_error(self, msg: str):
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

    def is_admin(self, user_id: int) -> bool:
        config = self.config
        """
        检查用户是否是管理员。

        参数:
        - user_id (int): 用户ID。

        返回:
        - bool: 用户是否是管理员。
        """
        return user_id in config["admins"]

    def add_admin(self, user_id: int):
        config = self.config
        """
        添加新的管理员用户ID到配置中。

        参数:
        - user_id (int): 要添加的用户ID。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        config["admins"].append(user_id)
        save_config(config)
        self.config = get_config()
        return self

    def set_admin_group(self, group_id: int):
        config = self.config
        """
        设置管理员组ID。

        参数:
        - group_id (int): 管理员组ID。

        返回:
        - Admin: 返回Admin实例，支持链式调用。
        """
        config["admin_group"] = group_id
        save_config(config)
        self.config = get_config()
        return self


class Chat:
    config: dict
    """
    Chat 类用于处理与LLM相关操作，如获取消息。
    """

    def __init__(self):
        """
        构造函数
        """
        self.config = get_config()

    async def get_msg(self, prompt: str, message: list):
        """
        获取LLM响应

        :param prompt[str]: 提示词
        :param message[list]: 消息列表
        """
        message.insert(0, {"role": "assistant", "content": prompt})
        return await get_chat(messages=message)

    async def get_msg_on_list(self, message: list):
        """
        获取LLM响应

        :param message[list]: 消息列表
        """
        return await get_chat(messages=message)
