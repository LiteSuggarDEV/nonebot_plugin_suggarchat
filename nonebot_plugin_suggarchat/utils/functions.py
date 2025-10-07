import json
import re
from datetime import datetime
from typing import Any

import pytz
from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    Message,
)

from ..chatmanager import chat_manager
from ..config import config_manager


def remove_think_tag(text: str) -> str:
    """移除第一次出现的think标签

    Args:
        text (str): 处理的参数

    Returns:
        str: 处理后的文本
    """

    start_tag = "<think>"
    end_tag = "</think>"

    # 查找第一个起始标签的位置
    start_idx = text.find(start_tag)
    if start_idx == -1:
        return text  # 没有找到起始标签，直接返回原文本

    # 在起始标签之后查找结束标签的位置
    end_idx = text.find(end_tag, start_idx + len(start_tag))
    if end_idx == -1:
        return text  # 没有找到对应的结束标签，返回原文本

    # 计算结束标签的结束位置
    end_of_end_tag = end_idx + len(end_tag)

    # 拼接移除标签后的文本
    text_new = text[:start_idx] + text[end_of_end_tag:]
    while text_new.startswith("\n"):
        text_new = text_new[1:]
    return text_new


async def is_member(event: GroupMessageEvent, bot: Bot) -> bool:
    """判断用户是否为群组普通成员"""
    # 获取群成员信息
    user_role = (
        (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["role"]
        if not event.sender.role
        else event.sender.role
    )
    return user_role == "member"


def format_datetime_timestamp(time: int) -> str:
    """将时间戳格式化为日期、星期和时间字符串"""
    now = datetime.fromtimestamp(time)
    formatted_date = now.strftime("%Y-%m-%d")
    formatted_weekday = now.strftime("%A")
    formatted_time = now.strftime("%I:%M:%S %p")
    return f"[{formatted_date} {formatted_weekday} {formatted_time}]"


# 在文件顶部预编译正则表达式
SENTENCE_DELIMITER_PATTERN = re.compile(r'([。！？!?;；\n]+)[""\'\'"\s]*', re.UNICODE)


def split_message_into_chats(text: str, max_length: int = 100) -> list[str]:
    """
    根据标点符号分割文本为句子

    Args:
        text: 要分割的文本
        max_length: 单个句子的最大长度，默认100个字符

    Returns:
        list[str]: 分割后的句子列表
    """
    if not text or not text.strip():
        return []

    sentences = []
    start = 0
    for match in SENTENCE_DELIMITER_PATTERN.finditer(text):
        end = match.end()
        if sentence := text[start:end].strip():
            sentences.append(sentence)
        start = end

    # 处理剩余部分
    if start < len(text):
        if remaining := text[start:].strip():
            sentences.append(remaining)

    # 处理过长的句子
    result = []
    for sentence in sentences:
        if len(sentence) <= max_length:
            result.append(sentence)
        else:
            # 如果句子过长且没有适当的分隔点，按最大长度切分
            chunks = [
                sentence[i : i + max_length]
                for i in range(0, len(sentence), max_length)
            ]
            result.extend(chunks)

    return result


async def synthesize_forward_message(forward_msg: dict, bot: Bot) -> str:
    """合成消息数组内容为字符串
    这是一个示例的消息集合/数组：
    [
        {
            "type": "node",
            "data": {
                "user_id": "10001000",
                "nickname": "某人",
                "content": "[CQ:face,id=123]哈喽～",
            }
        },
        {
            "type": "node",
            "data": {
                "user_id": "10001001",
                "nickname": "某人",
                "content": [
                    {"type": "face", "data": {"id": "123"}},
                    {"type": "text", "data": {"text": "哈喽～"}},
                ]
            }
        }
    ]
    """
    result = ""
    for segment in forward_msg:
        try:
            if isinstance(segment["data"], str):
                try:
                    segment["data"] = json.loads(segment["data"])
                except Exception:
                    result += segment["data"] + "<!--该消息段无法被解析-->"
            nickname: str = segment["data"]["nickname"]
            qq: str = segment["data"]["user_id"]
            result += f"[{nickname}({qq})]说："
            if isinstance(segment["data"]["content"], str):
                result += f"{segment['data']['content']}"
            elif isinstance(segment["data"]["content"], list):
                for segments in segment["data"]["content"]:
                    match segments["type"]:
                        case "text":
                            result += f"{segments['data']['text']}"
                        case "at":
                            result += f" [@{segments['data']['qq']}]"
                        case "forward":
                            result += f"\\（合并转发:{await synthesize_forward_message(await bot.get_forward_msg(id=segments['data']['id']), bot)}）\\"
        except Exception as e:
            logger.opt(colors=True, exception=e).warning(f"解析消息时出错：{e!s}'")
            result += f"\n<!--该消息段无法被解析--><origin>{segment!s}</origin>"
        result += "\n"
    return result


async def synthesize_message(message: Message, bot: Bot) -> str:
    """合成消息内容为字符串"""
    content = ""
    for segment in message:
        if segment.type == "text":
            content += segment.data["text"]
        elif segment.type == "at":
            content += f"\\（at: @{segment.data.get('name')}(QQ:{segment.data['qq']}))"
        elif (
            segment.type == "forward"
            and config_manager.config.function.synthesize_forward_message
        ):
            forward = await bot.get_forward_msg(id=segment.data["id"])
            if chat_manager.debug:
                logger.debug(forward)
            content += (
                " \\（合并转发\n"
                + await synthesize_forward_message(forward, bot)
                + "）\\\n"
            )
    return content


def split_list(lst: list, threshold: int) -> list[Any]:
    """将列表分割为多个子列表，每个子列表长度不超过阈值"""
    if len(lst) <= threshold:
        return [lst]
    return [lst[i : i + threshold] for i in range(0, len(lst), threshold)]


def get_current_datetime_timestamp():
    """获取当前时间并格式化为日期、星期和时间字符串"""
    utc_time = datetime.now(pytz.utc)
    asia_shanghai = pytz.timezone("Asia/Shanghai")
    now = utc_time.astimezone(asia_shanghai)
    formatted_date = now.strftime("%Y-%m-%d")
    formatted_weekday = now.strftime("%A")
    formatted_time = now.strftime("%H:%M:%S")
    return f"[{formatted_date} {formatted_weekday} {formatted_time}]"


async def get_friend_name(qq_number: int, bot: Bot) -> str:
    """获取好友昵称"""
    friend_list = await bot.get_friend_list()
    return next(
        (
            friend["nickname"]
            for friend in friend_list
            if friend["user_id"] == qq_number
        ),
        "",
    )
