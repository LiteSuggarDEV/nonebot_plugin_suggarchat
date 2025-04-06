import sys
from collections.abc import Callable, Coroutine
from typing import Any

import nonebot
import openai
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from nonebot_plugin_suggarchat.chatmanager import chat_manager
from nonebot_plugin_suggarchat.config import Config

from .config import config_manager
from .utils import openai_get_chat


async def send_to_admin(msg: str, bot: Bot | None = None) -> None:
    """
    异步发送消息给管理员。

    该函数会检查配置文件是否允许发送消息给管理员，以及是否配置了管理员群号。
    如果满足条件，则发送消息；否则，将记录警告日志。

    参数:
    msg (str): 要发送给管理员的消息。

    返回:
    无返回值。
    """
    # 检查是否允许发送消息给管理员
    if not config_manager.config.allow_send_to_admin:
        return
    # 检查管理员群号是否已配置
    if config_manager.config.admin_group == 0:
        try:
            # 如果未配置管理员群号但尝试发送消息，抛出警告
            raise RuntimeWarning("错误！管理员群组没有被设定！")
        except Exception:
            # 记录警告日志并捕获异常信息
            logger.warning(f'Admin 群组没有被设定，"{msg}"不会被推送！')
            exc_type, exc_vaule, exc_tb = sys.exc_info()
            logger.exception(f"{exc_type}:{exc_vaule}")
        return
    # 获取bot实例并发送消息到管理员群
    if bot:
        await bot.send_group_msg(
            group_id=config_manager.config.admin_group, message=msg
        )
    else:
        await (nonebot.get_bot()).send_group_msg(
            group_id=config_manager.config.admin_group, message=msg
        )


protocols_adapters: dict[
    str, Callable[[str, str, str, list, int, Config, Bot], Coroutine[Any, Any, str]]
] = {"openai-builtin": openai_get_chat}


async def get_chat(
    messages: list,
    bot: Bot | None = None,
) -> str:
    """
    异步获取聊天响应函数

    本函数根据输入的消息列表生成聊天响应文本它根据配置文件中的设置，
    选择适当的API密钥、基础URL和模型进行聊天生成支持流式生成响应文本，
    并处理配置中预设的加载和错误情况下的配置重置

    参数:
    - messages (list): 包含聊天消息的列表，每个消息是一个字典

    返回:
    - str: 生成的聊天响应文本
    """

    # 声明全局变量，用于访问配置和判断是否启用
    # 从配置中获取最大token数量
    max_tokens = config_manager.config.max_tokens
    func = openai_get_chat
    # 根据配置中的预设值，选择不同的API密钥和基础URL
    if config_manager.config.preset == "__main__":
        # 如果是主配置，直接使用配置文件中的设置
        base_url = config_manager.config.open_ai_base_url
        key = config_manager.config.open_ai_api_key
        model = config_manager.config.model
        protocol = config_manager.config.protocol
    else:
        # 如果是其他预设，从模型列表中查找匹配的设置
        for i in config_manager.get_models():
            if i.name == config_manager.config.preset:
                base_url = i.base_url
                key = i.api_key
                model = i.model
                protocol = i.protocol
                break
        else:
            # 如果未找到匹配的预设，记录错误并重置预设为主配置文件
            logger.error(
                f"预设 {config_manager.config.preset} 未找到，已重置为主配置文件"
            )
            logger.info(f"找到：模型：{config_manager.config.model}")
            config_manager.config.preset = "__main__"
            key = config_manager.config.open_ai_api_key
            model = config_manager.config.model
            base_url = config_manager.config.open_ai_base_url
            protocol = config_manager.config.protocol
            # 保存更新后的配置
            config_manager.save_config()
    if protocol == "__main__":
        func = openai_get_chat

    elif protocol not in protocols_adapters:
        raise Exception(f"协议 {protocol} 的适配器未找到!")
    else:
        func = protocols_adapters[protocol]
    # 记录日志，开始获取对话
    logger.debug(f"开始获取 {model} 的对话")
    logger.debug(f"预设：{config_manager.config.preset}")
    logger.debug(f"密钥：{key[:7]}...")
    logger.debug(f"协议：{protocol}")
    logger.debug(f"API地址：{base_url}")
    return await func(
        base_url,
        model,
        key,
        messages,
        max_tokens,
        config_manager.config,
        bot or nonebot.get_bot(),
    )


async def openai_get_chat(
    base_url: str,
    model: str,
    key: str,
    messages: list,
    max_tokens: int,
    config: Config,
    bot: Bot,
) -> str:
    if (
        not str(config.open_ai_base_url).strip()
        or not str(config.open_ai_api_key).strip()
    ):
        raise RuntimeError("错误！OpenAI Url或Key为空！")
    client = openai.AsyncOpenAI(
        base_url=base_url, api_key=key, timeout=config.llm_timeout
    )
    # 创建聊天完成请求
    for index, i in enumerate(range(3)):
        try:
            completion: (
                ChatCompletion | openai.AsyncStream[ChatCompletionChunk]
            ) = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                stream=config.stream,
            )
            break
        except Exception as e:
            logger.error(f"发生了错误: {e}")
            logger.info(f"尝试第{i + 1}次重试")
            if index == 2:
                logger.error("获取对话失败，请检查你的API Key和API base_url是否正确！")
                await send_to_admin(f"在获取对话时发生了错误: {e}", bot)
                raise e
            continue

    response = ""
    if config.stream and isinstance(completion, openai.AsyncStream):
        # 流式接收响应并构建最终的聊天文本
        async for chunk in completion:
            try:
                if chunk.choices[0].delta.content is not None:
                    response += chunk.choices[0].delta.content
                    if chat_manager.debug:
                        logger.debug(chunk.choices[0].delta.content)
            except IndexError:
                break
        # 记录生成的响应日志
    else:
        if chat_manager.debug:
            logger.debug(response)
        if isinstance(completion, ChatCompletion):
            response = completion.choices[0].message.content
        else:
            raise RuntimeError("Unexpected completion type received.")
    return response if response is not None else ""


async def is_member(event: GroupMessageEvent, bot: Bot) -> bool:
    """判断事件触发者是否为群组普通成员"""
    # 获取群组成员信息
    user_role = await bot.get_group_member_info(
        group_id=event.group_id, user_id=event.user_id
    )
    # 提取成员在群组中的角色
    user_role = user_role.get("role")
    # 判断成员角色是否为"member"（普通成员）
    return user_role == "member"
