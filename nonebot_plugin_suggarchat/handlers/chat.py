"""聊天处理器模块

该模块实现了聊天功能的核心逻辑，包括群聊和私聊的处理、会话管理、消息处理等功能。
"""

import asyncio
import contextlib
import copy
import random
import time
import typing
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from nonebot import get_driver, logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
    Reply,
)
from nonebot.exception import NoneBotException
from nonebot.matcher import Matcher

from ..chatmanager import SessionTemp, chat_manager
from ..check_rule import FakeEvent
from ..config import config_manager
from ..event import BeforeChatEvent, ChatEvent
from ..exception import CancelException
from ..matcher import MatcherManager
from ..utils.functions import (
    get_current_datetime_timestamp,
    get_friend_name,
    split_message_into_chats,
    synthesize_message,
)
from ..utils.libchat import get_chat, get_tokens
from ..utils.lock import get_group_lock, get_private_lock
from ..utils.memory import (
    Memory,
    MemoryModel,
    Message,
    ToolResult,
    get_memory_data,
)
from ..utils.models import (
    ImageContent,
    ImageUrl,
    InsightsModel,
    TextContent,
    UniResponseUsage,
)
from ..utils.protocol import UniResponse
from ..utils.tokenizer import hybrid_token_count

command_prefix = get_driver().config.command_start or "/"


# =============================================================================
# TOKEN 相关函数
# =============================================================================


async def enforce_token_limit(
    data: MemoryModel,
    train: dict[str, Any],
    response: UniResponse[str, None],
) -> UniResponseUsage[int]:
    """控制 token 数量，删除超出限制的旧消息

    Args:
        data: 内存模型数据
        train: 训练数据
        response: 模型响应

    Returns:
        token使用情况
    """
    train_model = Message.model_validate(train)
    memory_l: list[Message | ToolResult] = [train_model, *data.memory.messages]
    tokens = await get_tokens(memory_l, response)
    if not config_manager.config.llm_config.enable_tokens_limit:
        return tokens
    tk_tmp = tokens.total_tokens
    while tk_tmp > config_manager.config.session.session_max_tokens:
        try:
            if len(data.memory.messages) > 0:
                del data.memory.messages[0]
            else:
                logger.warning(
                    f"提示词大小过大！为{hybrid_token_count(train['content'])}>{config_manager.config.session.session_max_tokens}！"
                )
                break
        except Exception as e:
            logger.opt(exception=e, colors=True).exception(
                f"上下文限制清理出现异常！{e!s}"
            )
            break
        tk_tmp = 0
        for st in memory_l:
            if isinstance(st["content"], str):
                string_parts = st["content"]
            else:
                string_parts = "".join(
                    [
                        s.get("text")
                        for s in st["content"]
                        if s["type"] == "text" and s.get("text") is not None
                    ]
                )

            tk_tmp += hybrid_token_count(
                string_parts, config_manager.config.llm_config.tokens_count_mode
            )
        await asyncio.sleep(0)
    return tokens


# =============================================================================
# 消息处理相关函数
# =============================================================================


async def synthesize_message_to_msg(
    event: MessageEvent,
    role: str,
    Date: str,
    user_name: str,
    user_id: str,
    content: str,
):
    """将消息转换为Message"""
    is_multimodal: bool = (
        any(
            [
                (await config_manager.get_preset(preset=preset)).multimodal
                for preset in [
                    config_manager.config.preset,
                    *config_manager.config.preset_extension.backup_preset_list,
                ]
            ]
        )
        or len(config_manager.config.preset_extension.multi_modal_preset_list) > 0
    )

    if config_manager.config.parse_segments:
        text = (
            [
                TextContent(
                    text=f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
                )
            ]
            + [
                ImageContent(image_url=ImageUrl(url=seg.data["url"]))
                for seg in event.message
                if seg.type == "image" and seg.data.get("url")
            ]
            if is_multimodal
            else f"[{role}][{Date}][{user_name}（{user_id}）]说:{content}"
        )
    else:
        text = event.message.extract_plain_text()
    return text


# =============================================================================
# 主聊天处理函数
# =============================================================================


async def chat(event: MessageEvent, matcher: Matcher, bot: Bot):
    """聊天处理主函数，根据消息类型（群聊或私聊）调用对应的处理逻辑。

    Args:
        event: 消息事件
        matcher: 匹配器
        bot: Bot实例
    """

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 图片处理
    # -------------------------------------------------------------------------

    async def handle_reply_pics(
        reply: Reply | None,
    ) -> AsyncGenerator[ImageContent, None]:
        if not reply:
            return
        msg = reply.message
        for seg in msg:
            if seg.type == "image":
                url = seg.data.get("url")
                if url:
                    yield ImageContent(image_url=ImageUrl(url=url))
        return

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 群聊消息处理
    # -------------------------------------------------------------------------

    async def handle_group_message(
        event: GroupMessageEvent,
        matcher: Matcher,
        bot: Bot,
        data: MemoryModel,
        memory_length_limit: int,
        Date: str,
    ):
        """处理群聊消息：
        - 检查是否启用群聊功能。
        - 管理会话上下文。
        - 处理消息内容和引用消息。
        - 控制记忆长度和 token 限制。
        - 调用聊天模型生成回复并发送。

        Args:
            event: 群消息事件
            matcher: 匹配器
            bot: Bot实例
            data: 内存模型数据
            memory_length_limit: 记忆长度限制
            Date: 当前时间戳
        """
        if not config_manager.config.function.enable_group_chat:
            matcher.skip()

        # 管理会话上下文
        await manage_sessions(event, data, chat_manager.session_clear_group)

        group_id = event.group_id
        user_id = event.user_id
        user_name = (
            (await bot.get_group_member_info(group_id=group_id, user_id=user_id))[
                "nickname"
            ]
            if not config_manager.config.function.use_user_nickname
            else event.sender.nickname
        )
        content = await synthesize_message(event.get_message(), bot)

        if content.strip() == "":
            content = ""

        # 获取用户角色
        role = await get_user_role(bot, group_id, user_id)
        if chat_manager.debug:
            logger.debug(f"{Date}{user_name}（{user_id}）说:{content}")

        # 处理引用消息
        if event.reply:
            content = await handle_reply(event.reply, bot, group_id, content)
        reply_pics = [pic async for pic in handle_reply_pics(event.reply)]
        # 记录用户消息
        text = await synthesize_message_to_msg(
            event, role, Date, str(user_name), str(user_id), content
        )
        if isinstance(text, list):
            text += reply_pics
        data.memory.messages.append(Message(role="user", content=text))
        if chat_manager.debug:
            logger.debug(f"当前群组提示词：\n{config_manager.group_train}")
        # 控制记忆长度和 token 限制
        await enforce_memory_limit(data, memory_length_limit)

        # 准备发送给模型的消息
        send_messages = prepare_send_messages(
            data, copy.deepcopy(Message.model_validate(config_manager.group_train))
        )
        response = await process_chat(event, send_messages)

        await send_response(event, response.content)

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 私聊消息处理
    # -------------------------------------------------------------------------

    async def handle_private_message(
        event: PrivateMessageEvent,
        matcher: Matcher,
        bot: Bot,
        data: MemoryModel,
        memory_length_limit: int,
        Date: str,
    ):
        """处理私聊消息：
        - 检查是否启用私聊功能。
        - 管理会话上下文。
        - 处理消息内容和引用消息。
        - 控制记忆长度和 token 限制。
        - 调用聊天模型生成回复并发送。

        Args:
            event: 私聊消息事件
            matcher: 匹配器
            bot: Bot实例
            data: 内存模型数据
            memory_length_limit: 记忆长度限制
            Date: 当前时间戳
        """
        if not config_manager.config.function.enable_private_chat:
            matcher.skip()

        # 管理会话上下文
        await manage_sessions(event, data, chat_manager.session_clear_user)

        content = await synthesize_message(event.get_message(), bot)

        if content.strip() == "":
            content = ""

        # 处理引用消息
        if event.reply:
            content = await handle_reply(event.reply, bot, None, content)
        user_name = await get_friend_name(event.user_id, bot=bot)
        text = await synthesize_message_to_msg(
            event, "", Date, str(user_name), str(event.user_id), content
        )
        reply_pics = [pic async for pic in handle_reply_pics(event.reply)]
        if isinstance(text, list):
            text += reply_pics
        # 记录用户消息
        data.memory.messages.append(Message(role="user", content=text))
        if chat_manager.debug:
            logger.debug(f"当前私聊提示词：\n{config_manager.private_train}")
        # 控制记忆长度和 token 限制
        await enforce_memory_limit(data, memory_length_limit)

        # 准备发送给模型的消息
        send_messages = prepare_send_messages(
            data, copy.deepcopy(Message.model_validate(config_manager.private_train))
        )
        response = await process_chat(event, send_messages)
        await send_response(event, response.content)

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 会话管理
    # -------------------------------------------------------------------------

    async def manage_sessions(
        event: GroupMessageEvent | PrivateMessageEvent,
        data: MemoryModel,
        session_clear_map: dict[str, SessionTemp],
    ):
        """管理会话上下文：
        - 控制会话超时和历史记录。
        - 提供"继续"功能以恢复上下文。

        Args:
            event: 消息事件
            data: 内存模型数据
            session_clear_map: 会话清理映射
        """
        if config_manager.config.session.session_control:
            session_id = str(
                event.group_id
                if isinstance(event, GroupMessageEvent)
                else event.user_id
            )
            try:
                if session := session_clear_map.get(session_id):
                    if "继续" not in event.message.extract_plain_text():
                        del session_clear_map[session_id]
                        return

                # 检查会话超时
                time_now = time.time()
                if (time_now - data.timestamp) >= (
                    float(config_manager.config.session.session_control_time * 60)
                ):
                    data.sessions.append(
                        Memory(messages=data.memory.messages, time=time_now)
                    )
                    while (
                        len(data.sessions)
                        > config_manager.config.session.session_control_history
                    ):
                        data.sessions.remove(data.sessions[0])
                    data.memory.messages = []
                    timestamp = data.timestamp
                    data.timestamp = time_now
                    await data.save(event, raise_err=True)
                    if not (
                        (time_now - timestamp)
                        > float(
                            config_manager.config.session.session_control_time * 60 * 2
                        )
                    ):
                        chated = await matcher.send(
                            f'如果想和我继续用之前的上下文聊天，快at我回复✨"继续"✨吧！\n（超过{config_manager.config.session.session_control_time}分钟没理我我就会被系统抱走存档哦！）'
                        )
                        session_clear_map[session_id] = SessionTemp(
                            message_id=chated["message_id"], timestamp=datetime.now()
                        )

                        raise CancelException()
                elif (
                    session := session_clear_map.get(session_id)
                ) and "继续" in event.message.extract_plain_text():
                    with contextlib.suppress(Exception):
                        if time_now - session.timestamp.timestamp() < 100:
                            await bot.delete_msg(message_id=session.message_id)

                    del session_clear_map[session_id]

                    data.memory.messages = data.sessions[-1].messages
                    data.sessions.pop()
                    await matcher.send("让我们继续聊天吧～")
                    await data.save(event, raise_err=True)
                    raise CancelException()

            finally:
                data.timestamp = time.time()

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 引用消息处理
    # -------------------------------------------------------------------------

    async def handle_reply(
        reply: Reply, bot: Bot, group_id: int | None, content: str
    ) -> str:
        """处理引用消息：
        - 提取引用消息的内容和时间信息。
        - 格式化为可读的引用内容。

        Args:
            reply: 回复消息
            bot: Bot实例
            group_id: 群组ID（私聊为None）
            content: 原始内容

        Returns:
            格式化后的内容
        """
        if not reply.sender.user_id:
            return content
        dt_object = datetime.fromtimestamp(reply.time)
        weekday = dt_object.strftime("%A")
        formatted_time = dt_object.strftime("%Y-%m-%d %I:%M:%S %p")
        role = (
            await get_user_role(bot, group_id, reply.sender.user_id) if group_id else ""
        )

        reply_content = await synthesize_message(reply.message, bot)
        return f"{content}\n（（（引用的消息）））：\n{formatted_time} {weekday} [{role}]{reply.sender.nickname}（QQ:{reply.sender.user_id}）说：{reply_content}"

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 用户角色获取
    # -------------------------------------------------------------------------

    async def get_user_role(bot: Bot, group_id: int, user_id: int) -> str:
        """获取用户在群聊中的身份（群主、管理员或普通成员）。

        Args:
            bot: Bot实例
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            用户角色字符串
        """
        role = (await bot.get_group_member_info(group_id=group_id, user_id=user_id))[
            "role"
        ]
        return {"admin": "群管理员", "owner": "群主", "member": "普通成员"}.get(
            role, "[获取身份失败]"
        )

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 记忆长度限制
    # -------------------------------------------------------------------------

    async def enforce_memory_limit(data: MemoryModel, memory_length_limit: int):
        """控制记忆长度，删除超出限制的旧消息，移除不支持的消息。

        Args:
            data: 内存模型数据
            memory_length_limit: 记忆长度限制
        """
        is_multimodal = (
            await config_manager.get_preset(config_manager.config.preset)
        ).multimodal
        # Process multimodal messages when needed
        for message in data.memory.messages:
            if (
                isinstance(message.content, list)
                and not is_multimodal
                and message.role == "user"
            ):
                message_text = ""
                for content_part in message.content:
                    if content_part.type == "text":
                        message_text += content_part.text
                message.content = message_text

        # Enforce memory length limit
        while len(data.memory.messages) > 0:
            if (
                len(data.memory.messages) > memory_length_limit
                or data.memory.messages[0].role != "user"
            ):
                del data.memory.messages[0]
            else:
                break

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 准备发送消息
    # -------------------------------------------------------------------------

    def prepare_send_messages(data: MemoryModel, train: Message[str]) -> list:
        """准备发送给聊天模型的消息列表，包括系统提示词数据和上下文。

        Args:
            data: 内存模型数据
            train: 训练数据

        Returns:
            准备发送的消息列表
        """
        train = copy.deepcopy(train)
        train.content = typing.cast(str, train.content)
        if config_manager.config.llm_config.use_base_prompt:
            train.content = (
                "你在纯文本环境工作，不允许使用MarkDown回复，我会提供聊天记录，你可以从这里面获取一些关键信息，比如时间与用户身份（e.g.: [管理员/群主/自己/群员][YYYY-MM-DD weekday hh:mm:ss AM/PM][昵称（QQ号）]说:<内容>），但是请不要以这个格式回复。对于消息上报我给你的有几个类型，除了文本还有,\\（戳一戳消息）\\：就是QQ的戳一戳消息是戳一戳了你，而不是我，请参与讨论。交流时不同话题尽量不使用相似句式回复，用户与你交谈的信息在<内容>。\n"
                + (
                    train.content.replace(
                        "{cookie}", config_manager.config.cookies.cookie
                    )
                    .replace("{self_id}", str(event.self_id))
                    .replace("{user_id}", str(event.user_id))
                    .replace("{user_name}", str(event.sender.nickname))
                )
            )
        train.content += f"\n以下是一些补充内容，如果与上面任何一条有冲突请忽略。\n{data.prompt if data.prompt != '' else '无'}"
        send_messages = copy.deepcopy(data.memory.messages)
        send_messages.insert(0, Message.model_validate(train))
        return send_messages

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 处理聊天
    # -------------------------------------------------------------------------

    async def process_chat(
        event: MessageEvent, send_messages: list[Message | ToolResult]
    ) -> UniResponse[str, None]:
        """调用聊天模型生成回复，并触发相关事件。

        Args:
            event: 消息事件
            send_messages: 发送消息列表

        Returns:
            模型响应
        """
        if config_manager.config.matcher_function:
            chat_event = BeforeChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response="",
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(chat_event, event, bot)
            send_messages = chat_event.get_send_message()

        response = await get_chat(send_messages)

        if config_manager.config.matcher_function:
            chat_event = ChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=response.content or "",
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(chat_event, event, bot)

        tokens = await enforce_token_limit(
            data, copy.deepcopy(config_manager.group_train), response
        )
        # 记录模型回复
        data.memory.messages.append(
            Message(
                content=response.content,
                role="assistant",
            )
        )

        insights = await InsightsModel.get()

        # 写入全局统计
        insights.usage_count += 1
        insights.token_output += tokens.completion_tokens
        insights.token_input += tokens.prompt_tokens
        await insights.save()

        # 写入记忆数据
        for d, ev in (
            (
                (data, event),
                (
                    await get_memory_data(user_id=event.user_id),
                    FakeEvent(
                        time=0,
                        self_id=0,
                        post_type="",
                        user_id=event.user_id,
                    ),
                ),
            )
            if hasattr(event, "group_id")
            else ((data, event),)
        ):
            d.usage += 1  # 增加使用次数
            d.output_token_usage += tokens.completion_tokens
            d.input_token_usage += tokens.prompt_tokens
            await d.save(ev)

        return response

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 发送响应
    # -------------------------------------------------------------------------

    async def send_response(event: MessageEvent, response: str):
        """发送聊天模型的回复，根据配置选择不同的发送方式。

        Args:
            event: 消息事件
            response: 模型响应内容
        """
        if not config_manager.config.function.nature_chat_style:
            await matcher.send(
                MessageSegment.reply(event.message_id) + MessageSegment.text(response)
            )
        elif response_list := split_message_into_chats(response):
            for message in response_list:
                await matcher.send(MessageSegment.text(message))
                await asyncio.sleep(
                    random.randint(1, 3) + (len(message) // random.randint(80, 100))
                )

    # -------------------------------------------------------------------------
    # 内部辅助函数 - 异常处理
    # -------------------------------------------------------------------------

    async def handle_exception(e: BaseException):
        """处理异常：
        - 通知用户出错。
        - 记录日志并通知管理员。

        Args:
            e: 异常对象
        """
        await matcher.send("出错了稍后试试吧（错误已反馈）")
        logger.opt(exception=e, colors=True).exception("程序发生了未捕获的异常")

    # 函数进入运行点

    memory_length_limit = config_manager.config.llm_config.memory_lenth_limit
    Date = get_current_datetime_timestamp()

    if any(
        event.message.extract_plain_text().strip().startswith(prefix)
        for prefix in command_prefix
        if prefix.strip()
    ):
        matcher.skip()

    try:
        data = await get_memory_data(event)
        if isinstance(event, GroupMessageEvent):
            async with get_group_lock(event.group_id):
                await handle_group_message(
                    event, matcher, bot, data, memory_length_limit, Date
                )

        elif isinstance(event, PrivateMessageEvent):
            async with get_private_lock(event.user_id):
                await handle_private_message(
                    event, matcher, bot, data, memory_length_limit, Date
                )

        else:
            matcher.skip()
    except NoneBotException as e:
        raise e
    except CancelException:
        return
    except Exception as e:
        await handle_exception(e)
