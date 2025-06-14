import json
import re
import sys
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any

import chardet
import jieba
import nonebot
import openai
import pytz
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import (
    Event,
    GroupMessageEvent,
    Message,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk

from .chatmanager import chat_manager
from .config import Config, config_manager


class Tokenizer:
    def __init__(self, max_tokens=2048, mode="bpe", truncate_mode="head"):
        """
        通用文本分词器

        :param max_tokens: 最大token限制，默认2048（仅在Word模式下生效）
        :param mode: 分词模式 ['char'(字符级), 'word'(词语级), 'bpe'(混合模式)]，默认bpe
        :param truncate_mode: 截断模式 ['head'(头部截断), 'tail'(尾部截断), 'middle'(中间截断)]，默认head
        """
        self.max_tokens = max_tokens
        self.mode = mode
        self.truncate_mode = truncate_mode
        self._word_pattern = re.compile(r"\w+|[^\w\s]")  # 匹配单词或标点符号

    def tokenize(self, text):
        """执行分词操作，返回token列表"""
        if self.mode == "char":
            return list(text)

        # 中英文混合分词策略
        tokens = []
        for chunk in re.findall(self._word_pattern, text):
            if chunk.strip() == "":
                continue

            if self._is_english(chunk):
                tokens.extend(chunk.split())
            else:
                tokens.extend(jieba.lcut(chunk))

        return tokens[: self.max_tokens] if self.mode == "word" else tokens

    def truncate(self, tokens):
        """执行token截断操作"""
        if len(tokens) <= self.max_tokens:
            return tokens

        if self.truncate_mode == "head":
            return tokens[-self.max_tokens :]
        elif self.truncate_mode == "tail":
            return tokens[: self.max_tokens]
        else:  # middle模式保留首尾
            head_len = self.max_tokens // 2
            tail_len = self.max_tokens - head_len
            return tokens[:head_len] + tokens[-tail_len:]

    def count_tokens(self, text):
        """统计文本token数量"""
        return len(self.tokenize(text))

    def _is_english(self, text):
        """判断是否为英文文本"""
        return all(ord(c) < 128 for c in text)


async def send_to_admin_as_error(msg: str, bot: Bot | None = None) -> None:
    logger.error(msg)
    await send_to_admin(msg, bot)


async def send_to_admin(msg: str, bot: Bot | None = None) -> None:
    """发送消息给管理员"""
    # 检查是否允许发送消息给管理员
    if not config_manager.config.allow_send_to_admin:
        return
    # 检查管理员群号是否已配置
    if config_manager.config.admin_group == 0:
        try:
            raise RuntimeWarning("管理员群组未设定！")
        except Exception:
            # 记录警告日志
            logger.warning(f'管理员群组未设定，消息 "{msg}" 不会被发送！')
            exc_type, exc_value, _ = sys.exc_info()
            logger.exception(f"{exc_type}:{exc_value}")
        return
    # 发送消息到管理员群
    if bot:
        await bot.send_group_msg(
            group_id=config_manager.config.admin_group, message=msg
        )
    else:
        await (nonebot.get_bot()).send_group_msg(
            group_id=config_manager.config.admin_group, message=msg
        )


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


async def get_chat(
    messages: list,
    bot: Bot | None = None,
    tokens: int = 0,
) -> str:
    """获取聊天响应"""
    # 获取最大token数量
    max_tokens = config_manager.config.max_tokens
    func = openai_get_chat
    # 根据预设选择API密钥和基础URL
    preset = config_manager.get_preset(
        config_manager.config.preset, fix=True, cache=False
    )
    is_thought_chain_model = preset.thought_chain_model

    # 检查协议适配器
    if preset.protocol == "__main__":
        func = openai_get_chat
    elif preset.protocol not in protocols_adapters:
        raise ValueError(f"协议 {preset.protocol} 的适配器未找到!")
    else:
        func = protocols_adapters[preset.protocol]
    # 记录日志
    logger.debug(f"开始获取 {preset.model} 的对话")
    logger.debug(f"预设：{config_manager.config.preset}")
    logger.debug(f"密钥：{preset.api_key[:7]}...")
    logger.debug(f"协议：{preset.protocol}")
    logger.debug(f"API地址：{preset.base_url}")
    logger.debug(f"当前对话Tokens:{tokens}")
    # 调用适配器获取聊天响应
    response = await func(
        preset.base_url,
        preset.model,
        preset.api_key,
        messages,
        max_tokens,
        config_manager.config,
        bot or nonebot.get_bot(),
    )
    if chat_manager.debug:
        logger.debug(response)
    return remove_think_tag(response) if is_thought_chain_model else response


async def openai_get_chat(
    base_url: str,
    model: str,
    key: str,
    messages: list,
    max_tokens: int,
    config: Config,
    bot: Bot,
) -> str:
    """核心聊天响应获取函数"""
    # 创建OpenAI客户端
    client = openai.AsyncOpenAI(
        base_url=base_url, api_key=key, timeout=config.llm_timeout
    )
    # 尝试获取聊天响应，最多重试3次
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
            logger.error(f"发生错误: {e}")
            logger.info(f"第 {i + 1} 次重试")
            if index == 2:
                await send_to_admin_as_error(
                    f"请检查API Key和API base_url！获取对话时发生错误: {e}", bot
                )
                raise e
            continue

    response: str = ""
    # 处理流式响应
    if config.stream and isinstance(completion, openai.AsyncStream):
        async for chunk in completion:
            try:
                if chunk.choices[0].delta.content is not None:
                    response += chunk.choices[0].delta.content
                    if chat_manager.debug:
                        logger.debug(chunk.choices[0].delta.content)
            except IndexError:
                break
    else:
        if chat_manager.debug:
            logger.debug(response)
        if isinstance(completion, ChatCompletion):
            response = (
                completion.choices[0].message.content
                if completion.choices[0].message.content is not None
                else ""
            )
        else:
            raise RuntimeError("收到意外的响应类型")
    return response if response is not None else ""


async def is_member(event: GroupMessageEvent, bot: Bot) -> bool:
    """判断用户是否为群组普通成员"""
    # 获取群成员信息
    user_role = await bot.get_group_member_info(
        group_id=event.group_id, user_id=event.user_id
    )
    # 判断角色是否为普通成员
    user_role = user_role.get("role")
    return user_role == "member"


# 协议适配器映射
protocols_adapters: dict[
    str, Callable[[str, str, str, list, int, Config, Bot], Coroutine[Any, Any, str]]
] = {"openai-builtin": openai_get_chat}


def format_datetime_timestamp(time: int) -> str:
    """将时间戳格式化为日期、星期和时间字符串"""
    now = datetime.fromtimestamp(time)
    formatted_date = now.strftime("%Y-%m-%d")
    formatted_weekday = now.strftime("%A")
    formatted_time = now.strftime("%I:%M:%S %p")
    return f"[{formatted_date} {formatted_weekday} {formatted_time}]"


def hybrid_token_count(text: str, mode: str = "word", truncate_mode="head") -> int:
    """
    计算中英文混合文本的 Token 数量，支持词、子词、字符模式
    """

    return Tokenizer(mode=mode, truncate_mode=truncate_mode).count_tokens(text=text)


# 在文件顶部预编译正则表达式
SENTENCE_DELIMITER_PATTERN = re.compile(
    r'([。！？!?~\.;；:：\n]+)[""\'\'"\s]*', re.UNICODE
)


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


def convert_to_utf8(file_path) -> bool:
    """将文件编码转换为 UTF-8"""
    file_path = str(file_path)
    with open(file_path, "rb") as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result["encoding"]
    if encoding is None:
        try:
            with open(file_path) as f:
                contents = f.read()
                if contents.strip() == "":
                    return True
        except Exception:
            logger.warning(f"无法读取文件{file_path}")
            return False
        logger.warning(f"无法检测到编码{file_path}")
        return False
    with open(file_path, encoding=encoding) as file:
        content = file.read()
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)
    return True


async def synthesize_forward_message(forward_msg: dict) -> str:
    """合成转发消息内容为字符串"""
    result = ""
    for segment in forward_msg:
        nickname = segment["data"]["nickname"]
        qq = segment["data"]["user_id"]
        result += f"[{nickname}({qq})]说："
        for segments in segment["content"]:
            segments_type = segments["type"]
            if segments_type == "text":
                result += f"{segments['data']['text']}"
            elif segments_type == "at":
                result += f" [@{segments['data']['qq']}]"
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
        elif segment.type == "forward":
            forward = await bot.get_forward_msg(id=segment.data["id"])
            if chat_manager.debug:
                logger.debug(forward)
            content += (
                " \\（合并转发\n" + await synthesize_forward_message(forward) + "）\\\n"
            )
    return content


def get_memory_data(event: Event) -> dict[str, Any]:
    """获取事件对应的记忆数据，如果不存在则创建初始数据"""
    if chat_manager.debug:
        logger.debug(f"获取{event.get_type()} {event.get_session_id()} 的记忆数据")
    private_memory = config_manager.private_memory
    group_memory = config_manager.group_memory

    if not Path(private_memory).exists() or not Path(private_memory).is_dir():
        Path.mkdir(private_memory)
    if not Path(group_memory).exists() or not Path(group_memory).is_dir():
        Path.mkdir(group_memory)

    if (
        not isinstance(event, PrivateMessageEvent)
        and not isinstance(event, GroupMessageEvent)
        and isinstance(event, PokeNotifyEvent)
        and event.group_id
    ) or (
        not isinstance(event, PrivateMessageEvent)
        and isinstance(event, GroupMessageEvent)
    ):
        group_id = event.group_id
        conf_path = Path(group_memory / f"{group_id}.json")
        if not conf_path.exists():
            with open(str(conf_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "id": group_id,
                        "enable": True,
                        "memory": {"messages": []},
                        "full": False,
                    },
                    f,
                    ensure_ascii=True,
                    indent=0,
                )
    elif (
        not isinstance(event, PrivateMessageEvent)
        and isinstance(event, PokeNotifyEvent)
    ) or isinstance(event, PrivateMessageEvent):
        user_id = event.user_id
        conf_path = Path(private_memory / f"{user_id}.json")
        if not conf_path.exists():
            with open(str(conf_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "id": user_id,
                        "enable": True,
                        "memory": {"messages": []},
                        "full": False,
                    },
                    f,
                    ensure_ascii=True,
                    indent=0,
                )
    convert_to_utf8(conf_path)
    with open(str(conf_path), encoding="utf-8") as f:
        conf = json.load(f)
        if chat_manager.debug:
            logger.debug(f"读取到记忆数据{conf}")
        return conf


def write_memory_data(event: Event, data: dict) -> None:
    """将记忆数据写入对应的文件"""
    if chat_manager.debug:
        logger.debug(f"写入记忆数据{data}")
        logger.debug(f"事件：{type(event)}")
    group_memory = config_manager.group_memory
    private_memory = config_manager.private_memory

    if isinstance(event, GroupMessageEvent):
        group_id = event.group_id
        conf_path = Path(group_memory / f"{group_id}.json")
    elif isinstance(event, PrivateMessageEvent):
        user_id = event.user_id
        conf_path = Path(private_memory / f"{user_id}.json")
    elif isinstance(event, PokeNotifyEvent):
        if event.group_id:
            group_id = event.group_id
            conf_path = Path(group_memory / f"{group_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": group_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
        else:
            user_id = event.user_id
            conf_path = Path(private_memory / f"{user_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": user_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
    with open(str(conf_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=True)


def split_list(lst: list, threshold: int) -> list[Any]:
    """将列表分割为多个子列表，每个子列表长度不超过阈值"""
    if len(lst) <= threshold:
        return [lst]
    return [lst[i : i + threshold] for i in range(0, len(lst), threshold)]


async def is_same_day(timestamp1: int, timestamp2: int) -> bool:
    """判断两个时间戳是否为同一天"""
    date1 = datetime.fromtimestamp(timestamp1).date()
    date2 = datetime.fromtimestamp(timestamp2).date()
    return date1 == date2


def get_current_datetime_timestamp():
    """获取当前时间并格式化为日期、星期和时间字符串"""
    utc_time = datetime.now(pytz.utc)
    asia_shanghai = pytz.timezone("Asia/Shanghai")
    now = utc_time.astimezone(asia_shanghai)
    formatted_date = now.strftime("%Y-%m-%d")
    formatted_weekday = now.strftime("%A")
    formatted_time = now.strftime("%H:%M:%S")
    return f"[{formatted_date} {formatted_weekday} {formatted_time}]"


async def get_friend_info(qq_number: int, bot: Bot) -> str:
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
