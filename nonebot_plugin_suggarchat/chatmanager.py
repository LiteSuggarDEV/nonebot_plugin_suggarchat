import asyncio
import contextlib
import copy
import random
import time
from asyncio import CancelledError, Lock, Task
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    MessageSegment,
)
from nonebot.adapters.onebot.v11.event import (
    GroupMessageEvent,
    MessageEvent,
    Reply,
)
from nonebot.matcher import Matcher
from nonebot_plugin_orm import get_session
from pydantic import BaseModel, Field
from pytz import utc
from typing_extensions import Self

from nonebot_plugin_suggarchat.matcher import ChatException
from nonebot_plugin_suggarchat.utils.event import GroupEvent
from nonebot_plugin_suggarchat.utils.logging import debug_log

from .check_rule import FakeEvent
from .config import Config, ConfigManager
from .event import BeforeChatEvent, ChatEvent
from .matcher import MatcherManager
from .utils.functions import (
    get_current_datetime_timestamp,
    get_friend_name,
    split_message_into_chats,
    synthesize_message,
)
from .utils.libchat import get_chat, get_tokens, text_generator
from .utils.lock import get_group_lock, get_private_lock
from .utils.memory import (
    Memory,
    MemoryModel,
    get_memory_data,
)
from .utils.models import (
    CT_MAP,
    SEND_MESSAGES,
    Content,
    ImageContent,
    ImageUrl,
    InsightsModel,
    Message,
    SessionMemoryModel,
    TextContent,
    ToolResult,
    UniResponseUsage,
)
from .utils.protocol import UniResponse
from .utils.tokenizer import hybrid_token_count

LOCK = Lock()


async def synthesize_message_to_msg(
    event: MessageEvent,
    role: str,
    date: str,
    user_name: str,
    user_id: str,
    content: str,
):
    """将消息转换为Message

    根据配置和多模态支持情况，将事件消息转换为适当的格式，
    支持文本和图片内容的组合。

    Args:
        event: 消息事件
        role: 用户角色
        date: 时间戳
        user_name: 用户名
        user_id: 用户ID
        content: 消息内容

    Returns:
        转换后的消息内容
    """
    is_multimodal: bool = (
        any(
            [
                (await ConfigManager().get_preset(preset=preset)).multimodal
                for preset in [
                    ConfigManager().config.preset,
                    *ConfigManager().config.preset_extension.backup_preset_list,
                ]
            ]
        )
        or len(ConfigManager().config.preset_extension.multi_modal_preset_list) > 0
    )

    if ConfigManager().config.parse_segments:
        text = (
            [
                TextContent(
                    text=f"[{role}][{date}][{user_name}（{user_id}）]说:{content}"
                )
            ]
            + [
                ImageContent(image_url=ImageUrl(url=seg.data["url"]))
                for seg in event.message
                if seg.type == "image" and seg.data.get("url")
            ]
            if is_multimodal
            else f"[{role}][{date}][{user_name}（{user_id}）]说:{content}"
        )
    else:
        text = event.message.extract_plain_text()
    return text


class ChatObjectMeta(BaseModel):
    """聊天对象元数据模型

    用于存储聊天对象的标识、事件和时间信息。
    """

    stream_id: str  # 聊天流ID
    event: MessageEvent  # 消息事件
    time: datetime = Field(default_factory=datetime.now)  # 创建时间
    last_call: datetime = Field(default_factory=datetime.now)  # 最后一次调用时间


class MemoryLimiter:
    """上下文处理器

    该类负责处理聊天上下文的记忆长度和token数量限制，通过上下文摘要和消息删除等方式，
    确保聊天上下文在预设的限制范围内，避免超出模型处理能力。
    """

    memory: MemoryModel  # 要处理的记忆模型
    config: Config  # 配置对象
    usage: UniResponseUsage | None = None  # token使用情况，初始为None
    _train: dict[str, str]  # 训练数据（系统提示词）
    _dropped_messages: list[Message[str] | ToolResult]  # 被删除的消息列表
    _copied_messages: Memory  # 原始消息副本（用于异常时回滚）
    _abstract_instruction = """<<SYS>>
你是一个专业的上下文摘要器，严格按照用户指令执行摘要任务。
<</SYS>>

<<INSTRUCTIONS>>
1. 直接摘要用户输入的内容
2. 保持原文的核心信息和关键细节
3. 不产生任何额外内容、解释或评论
4. 摘要应简洁、准确、完整
<</INSTRUCTIONS>>

<<RULE>>
- 仅对用户提供文本进行摘要
- 不添加任何解释、评论或补充信息
- 不改变原文的主要意思
- 保持客观中立的语调
<</RULE>>

<<FORMATTING>>
用户输入 → 直接输出摘要结果
<</FORMATTING>>"""

    def __init__(self, memory: MemoryModel, train: dict[str, str]) -> None:
        """初始化上下文处理器

        Args:
            memory: 要处理的记忆模型
            train: 训练数据（系统提示词）
        """
        self.memory = memory
        self.config = ConfigManager().config
        self._train = train

    async def __aenter__(self) -> Self:
        """异步上下文管理器入口，初始化处理状态

        Returns:
            返回自身实例以供使用
        """
        self._dropped_messages = []
        self._copied_messages = copy.deepcopy(self.memory.memory)
        debug_log(f"MemoryLimiter初始化，消息数量: {len(self.memory.memory.messages)}")
        return self

    async def _make_abstract(self):
        """生成上下文摘要

        通过调用LLM将当前记忆中的所有消息内容摘要为一段简短的内容，
        以减少上下文长度，同时保留关键信息。
        """
        debug_log("开始进行上下文摘要..")
        proportion = self.config.llm_config.memory_abstract_proportion  # 摘要比例
        dropped_part: SEND_MESSAGES = copy.deepcopy(self._dropped_messages)
        index = int(len(self.memory.memory.messages) * proportion) - len(dropped_part)
        if index < 0:
            index = 0
        idx: int | None = None
        if index:
            for idx, element in enumerate(self.memory.memory.messages):
                dropped_part.append(element)
                if (
                    getattr(element, "tool_calls", None) is not None
                ):  # 连带去除工具调用(system(tool_call),tool_call)
                    continue
                elif idx >= index:
                    break
        self.memory.memory.messages = self.memory.memory.messages[
            (idx if idx is not None else index) :  # 删除部分消息
        ]
        if dropped_part:
            msg_list: SEND_MESSAGES = [
                Message[str](role="system", content=self._abstract_instruction),
                Message[str](
                    role="user",
                    content=(
                        "消息列表：\n```text\n".join(
                            [
                                f"{it}\n"
                                for it in text_generator(
                                    dropped_part,
                                    split_role=True,
                                )
                            ]
                        )
                        + "\n```"
                    ),
                ),
            ]
            debug_log("正在进行上下文摘要...")
            response = await get_chat(msg_list)
            usage = await get_tokens(msg_list, response)
            self.usage = usage
            debug_log(f"获取到上下文摘要：{response.content}")
            self.memory.memory.abstract = response.content
            debug_log("上下文摘要完成")
        else:
            debug_log("未进行上下文摘要")

    def _drop_message(self):
        data = self.memory
        if len(data.memory.messages) < 2:
            return
        self._dropped_messages.append(data.memory.messages.pop(0))
        if data.memory.messages[0].role == "tool":
            self._dropped_messages.append(data.memory.messages.pop(0))

    async def run_enforce(self):
        """执行记忆限制处理

        按顺序执行记忆长度限制和token数量限制，确保聊天上下文在预设范围内。
        该方法必须在异步上下文管理器中使用。

        Raises:
            RuntimeError: 当未在异步上下文管理器中使用时抛出
        """
        debug_log("开始执行记忆限制处理..")
        if not hasattr(self, "_dropped_messages") and not hasattr(
            self, "_copied_messages"
        ):
            raise RuntimeError(
                "MemoryLimiter is not initialized, please use use `async with MemoryLimiter(memory)` before calling."
            )
        await self._limit_length()
        await self._limit_tokens()
        if self.config.llm_config.enable_memory_abstract and self._dropped_messages:
            await self._make_abstract()
        debug_log("记忆限制处理完成")

    async def _limit_length(self):
        """控制记忆长度，删除超出限制的旧消息，移除不支持的消息。"""
        debug_log("开始执行记忆长度限制..")
        is_multimodal = (
            await ConfigManager().get_preset(ConfigManager().config.preset)
        ).multimodal
        data: MemoryModel = self.memory

        # Process multimodal messages when needed
        for message in data.memory.messages:
            if (
                isinstance(message.content, list)
                and not is_multimodal
                and message.role == "user"
            ):
                message_text = ""
                for content_part in message.content:
                    if isinstance(content_part, dict):
                        validator = CT_MAP.get(content_part["type"])
                        if not validator:
                            raise ValueError(
                                f"Invalid content type: {content_part['type']}"
                            )
                        content_part: Content = validator.model_validate(content_part)
                    if content_part["type"] == "text":
                        message_text += content_part["text"]
                message.content = message_text

        # Enforce memory length limit
        initial_count = len(data.memory.messages)
        while len(data.memory.messages) >= 2:
            if data.memory.messages[0].role == "tool":
                data.memory.messages.pop(0)
            elif len(data.memory.messages) > self.config.llm_config.memory_lenth_limit:
                self._drop_message()
            else:
                break
        final_count = len(data.memory.messages)
        debug_log(f"记忆长度限制完成，删除了 {initial_count - final_count} 条消息")

    async def _limit_tokens(self):
        """控制 token 数量，删除超出限制的旧消息

        通过计算当前消息列表的token数量，当超出配置的session最大token限制时，
        逐步删除最早的消息直到满足token数量限制。
        """

        def get_token(memory: SEND_MESSAGES) -> int:
            tk_tmp: int = 0
            for msg in text_generator(memory):
                tk_tmp += hybrid_token_count(
                    msg,
                    ConfigManager().config.llm_config.tokens_count_mode,
                )
            return tk_tmp

        train = self._train
        train_model = Message.model_validate(train)
        data = self.memory
        debug_log("开始执行token数量限制..")
        memory_l: SEND_MESSAGES = [train_model, *data.memory.messages]
        if not ConfigManager().config.llm_config.enable_tokens_limit:
            debug_log("token限制未启用，跳过处理")
            return
        prompt_length = hybrid_token_count(train["content"])
        if prompt_length > ConfigManager().config.session.session_max_tokens:
            logger.warning(
                f"提示词大小过大！为{prompt_length}>{ConfigManager().config.session.session_max_tokens}！请调整提示词或者设置！"
            )
            return
        tk_tmp: int = get_token(memory_l)

        initial_count = len(data.memory.messages)
        while tk_tmp > ConfigManager().config.session.session_max_tokens:
            if len(data.memory.messages) >= 2:
                self._drop_message()
            else:
                break

            tk_tmp: int = get_token(memory_l)
            memory_l = [train_model, *data.memory.messages]
            await asyncio.sleep(0)  # CPU 密集型任务可能造成性能问题，我们在这里让出协程
        final_count = len(data.memory.messages)
        debug_log(f"token数量限制完成，删除了 {initial_count - final_count} 条消息")
        debug_log(f"最终token数量: {tk_tmp}")

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口，处理异常情况下的回滚

        当发生异常时，将消息恢复到处理前的状态，确保数据一致性。

        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常追踪栈
        """
        if exc_type is not None:
            logger.warning("发生异常，正在回滚消息...")
            self.memory.memory.messages = self._copied_messages.messages
            return


class ChatObject:
    """聊天处理对象

    该类负责处理单次聊天会话，包括消息接收、上下文管理、模型调用和响应发送。
    """

    stream_id: str  # 聊天对象ID
    matcher: Matcher  # (lateinit) 匹配器
    bot: Bot  # (lateinit) Bot实例
    event: MessageEvent  # (lateinit) 消息事件
    config: Config  # 配置
    timestamp: str  # 时间戳(用于LLM)
    time: datetime  # 时间
    end_at: datetime | None = None
    data: MemoryModel  # (lateinit) 记忆文件
    train: dict[str, str]  # 训练数据（根据群聊/私聊选择）
    last_call: datetime  # 最后一次调用内部函数的时间
    _is_running: bool = False  # 是否正在运行
    _is_done: bool = False  # 是否已经完成
    _task: Task[None]
    _has_task: bool = False
    _err: BaseException | None = None
    _wait: bool = True
    _pending: bool = False  # 是否在等待队列中

    def __init__(self, run_blocking: bool = True) -> None:
        """初始化聊天对象"""
        self.timestamp = get_current_datetime_timestamp()
        self.time = datetime.now(utc)
        self.config = ConfigManager().config
        self.last_call = datetime.now(utc)
        self._wait = run_blocking

    def get_exception(self) -> BaseException | None:
        """
        获取任务执行过程中发生的异常

        Returns:
            BaseException | None: 如果任务执行中有异常则返回异常对象，否则返回None
        """
        return self._err

    def caller(self):
        """
        获取调用对象

        Returns:
            调用对象（通常是类的__call__方法）
        """
        return self.__call__

    def is_waitting(self) -> bool:
        """
        检查任务是否处于等待状态

        Returns:
            bool: 如果任务正在等待则返回True，否则返回False
        """
        return self._pending

    def is_running(self) -> bool:
        """
        检查任务是否正在运行

        Returns:
            bool: 如果任务正在运行则返回True，否则返回False
        """
        return self._is_running

    def is_done(self) -> bool:
        """
        检查任务是否已完成

        Returns:
            bool: 如果任务已完成则返回True，否则返回False
        """
        return self._is_done

    def terminate(self) -> None:
        """
        终止任务的执行
        设置任务状态为已完成，并取消内部任务
        """
        self._is_done = True
        self._is_running = False
        self._task.cancel()

    def __await__(self):
        if not hasattr(self, "_task"):
            raise RuntimeError("ChatObject not running")
        return self._task.__await__()

    async def __call__(self, event: MessageEvent, matcher: Matcher, bot: Bot) -> None:
        """调用聊天对象处理消息

        Args:
            event: 消息事件
            matcher: 匹配器
            bot: Bot实例
        """
        if not self._has_task:
            debug_log("正在启动聊天对象任务...")
            self._has_task = True
            self._task = asyncio.create_task(self.__call__(event, matcher, bot))
            return await self._task if self._wait else None
        if not self._is_running and not self._is_done:
            debug_log(f"开始处理聊天事件，用户ID: {event.user_id}")
            self.stream_id = uuid4().hex
            self.bot = bot
            self.matcher = matcher
            self.event = event
            self.train = copy.deepcopy(
                ConfigManager().group_train
                if isinstance(event, GroupMessageEvent)
                else ConfigManager().private_train
            )

            try:
                lock = (
                    get_group_lock(event.group_id)
                    if isinstance(event, GroupMessageEvent)
                    else get_private_lock(event.user_id)
                )
                await chat_manager.add_chat_object(self)

                match self.config.function.chat_pending_mode:
                    case "queue":
                        debug_log("聊天队列模式")
                        self._pending = lock.locked()
                    case "single":
                        if lock.locked():
                            debug_log("聊天已被锁定，跳过")
                            return matcher.stop_propagation()
                    case "single_with_report":
                        if lock.locked():
                            debug_log("聊天已被锁定，发送报告")
                            await matcher.finish("聊天任务正在处理中，请稍后再试")

                async with lock:
                    self._is_running = True
                    self.last_call = datetime.now(utc)
                    self._pending = False
                    debug_log("获取锁成功，开始获取记忆数据")
                    self.data = await get_memory_data(event)
                    debug_log("记忆数据获取完成，开始运行聊天流程")

                    await self._run()
            except BaseException as e:
                if isinstance(e, ChatException):
                    raise
                debug_log(f"处理聊天事件时发生异常: {e}")
                await self._throw(e)
            finally:
                self._is_running = False
                self._is_done = True
                self._pending = False
                self.end_at = datetime.now(utc)
                chat_manager.running_chat_object_id2map.pop(self.stream_id, None)
                debug_log("聊天事件处理完成")

        else:
            raise RuntimeError(
                f"ChatObject of event <{event.model_dump_json()}> is already running or done"
            )

    async def _run(self):
        """运行聊天处理流程

        执行消息处理的主要逻辑，包括获取用户信息、处理消息内容、
        管理上下文长度和token限制，以及发送响应。
        """
        debug_log("开始运行聊天处理流程..")
        event = self.event
        data = self.data
        bot = self.bot
        user_id = event.user_id
        config = self.config
        debug_log("管理会话上下文..")
        await self._manage_sessions()
        debug_log("会话管理完成")

        if isinstance(event, GroupMessageEvent):
            # 群聊消息处理
            debug_log("处理群聊消息")
            group_id = event.group_id

            user_name = (
                (await bot.get_group_member_info(group_id=group_id, user_id=user_id))[
                    "nickname"
                ]
                if not config.function.use_user_nickname
                else event.sender.nickname
            )
            role = await self._get_user_role(group_id, user_id)
        else:
            debug_log("处理私聊消息")
            user_name = (
                await get_friend_name(event.user_id, bot=bot)
                if not isinstance(event, GroupMessageEvent)
                else event.sender.nickname
            )
            role = ""
        debug_log(f"获取用户信息完成: {user_name}, 角色: {role}")

        content = await synthesize_message(event.get_message(), bot)
        self.last_call = datetime.now(utc)
        debug_log(f"合成消息完成: {content}")

        if content.strip() == "":
            content = ""
        if event.reply:
            group_id = event.group_id if isinstance(event, GroupMessageEvent) else None
            debug_log("处理引用消息..")
            content = await self._handle_reply(event.reply, bot, group_id, content)

        reply_pics = self._get_reply_pics()
        debug_log(f"获取引用图片完成，共 {len(reply_pics)} 张")

        content = await synthesize_message_to_msg(
            event, role, self.timestamp, str(user_name), str(user_id), content
        )
        if isinstance(content, list):
            content.extend(reply_pics)
        data.memory.messages.append(Message(role="user", content=content))
        debug_log(f"添加用户消息到记忆，当前消息总数: {len(data.memory.messages)}")

        self.train["content"] = (
            "<SCHEMA>\n"
            + "你在纯文本环境工作，不允许使用MarkDown回复，你的工作环境是一个社交软件，我会提供聊天记录，你可以从这里面获取一些关键信息，比如时间与用户身份"
            + "（e.g.: [管理员/群主/自己/群员][YYYY-MM-DD weekday hh:mm:ss AM/PM][昵称（QQ号）]说:<内容>），但是请不要以聊天记录的格式做回复，而是纯文本方式。"
            + "请以你自己的角色身份参与讨论，交流时不同话题尽量不使用相似句式回复，用户与你交谈的信息在用户的消息输入内。"
            + "你的设定将在<SYSTEM_INSTRUCTIONS>标签对内，对于先前对话的摘要位于<SUMMARY>标签对内，"
            + "\n</SCHEMA>\n"
            + "<SYSTEM_INSTRUCTIONS>\n"
            + (
                self.train["content"]
                .replace("{cookie}", config.cookies.cookie)
                .replace("{self_id}", str(event.self_id))
                .replace("{user_id}", str(event.user_id))
                .replace("{user_name}", str(event.sender.nickname))
            )
            + "\n</SYSTEM_INSTRUCTIONS>"
            + f"\n<SUMMARY>\n{data.memory.abstract if config.llm_config.enable_memory_abstract else ''}\n</SUMMARY>"
        )

        debug_msg = (
            f"当前群组提示词：\n{ConfigManager().group_train}"
            if isinstance(event, GroupMessageEvent)
            else f"当前私聊提示词：\n{ConfigManager().private_train}"
        )
        debug_log(debug_msg)
        debug_log(self.train["content"])

        debug_log("开始应用记忆限制..")
        async with MemoryLimiter(self.data, self.train) as lim:
            await lim.run_enforce()
            abs_usage = lim.usage
            self.data = lim.memory
        debug_log("记忆限制应用完成")

        send_messages = self._prepare_send_messages()
        debug_log(f"准备发送消息完成，消息数量: {len(send_messages)}")
        response = await self._process_chat(send_messages, abs_usage)
        debug_log("聊天处理完成，准备发送响应")
        await self.send_response(response.content)
        debug_log("开始保存记忆数据..")
        await self.data.save(event)
        debug_log("记忆数据保存完成")

    async def send_response(self, response: str):
        """发送聊天模型的回复，根据配置选择不同的发送方式。

        Args:
            response: 模型响应内容
        """
        self.last_call = datetime.now(utc)
        debug_log(f"发送响应: {response[:50]}..")  # 只显示前50个字符
        if not self.config.function.nature_chat_style:
            await self.matcher.send(
                MessageSegment.reply(self.event.message_id)
                + MessageSegment.text(response)
            )
        elif response_list := split_message_into_chats(response):
            for message in response_list:
                await self.matcher.send(MessageSegment.text(message))
                await asyncio.sleep(
                    random.randint(1, 3) + (len(message) // random.randint(80, 100))
                )

    async def _process_chat(
        self,
        send_messages: SEND_MESSAGES,
        extra_usage: UniResponseUsage[int] | None = None,
    ) -> UniResponse[str, None]:
        """调用聊天模型生成回复，并触发相关事件。

        Args:
            send_messages: 发送消息列表
            extra_usage: 额外的token使用量信息

        Returns:
            模型响应
        """
        self.last_call = datetime.now(utc)

        def add_usage(ins: InsightsModel | MemoryModel, usage: UniResponseUsage[int]):
            if isinstance(ins, InsightsModel):
                ins.token_output += usage.completion_tokens
                ins.token_input += usage.prompt_tokens
            else:
                ins.input_token_usage += usage.prompt_tokens
                ins.output_token_usage += usage.completion_tokens

        event = self.event
        bot = self.bot
        data = self.data
        debug_log(f"开始处理聊天，发送消息数量: {len(send_messages)}")

        if ConfigManager().config.matcher_function:
            debug_log("触发匹配器函数..")
            chat_event = BeforeChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response="",
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(chat_event, event, bot)
            send_messages = chat_event.get_send_message().unwrap()

        debug_log("调用聊天模型..")
        response = await get_chat(send_messages)

        if ConfigManager().config.matcher_function:
            debug_log("触发聊天事件..")
            chat_event = ChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=response.content or "",
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(chat_event, event, bot)
            response.content = chat_event.model_response

        debug_log("计算token使用情况..")
        tokens = await get_tokens(send_messages, response)
        # 记录模型回复
        data.memory.messages.append(
            Message[str](
                content=response.content,
                role="assistant",
            )
        )
        debug_log(f"添加助手回复到记忆，当前消息总数: {len(data.memory.messages)}")

        insights = await InsightsModel.get()
        debug_log(f"获取洞察数据完成，使用计数: {insights.usage_count}")

        # 写入全局统计
        insights.usage_count += 1
        add_usage(insights, tokens)
        if extra_usage:
            add_usage(insights, extra_usage)
        await insights.save()
        debug_log(f"更新全局统计完成，使用计数: {insights.usage_count}")

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
            add_usage(d, tokens)
            if extra_usage:
                add_usage(d, extra_usage)
            debug_log(f"更新记忆数据，使用次数: {d.usage}")
            await d.save(ev)

        debug_log("聊天处理完成")
        return response

    def _prepare_send_messages(
        self,
    ) -> list:
        """准备发送给聊天模型的消息列表，包括系统提示词数据和上下文。

        Returns:
            准备发送的消息列表
        """
        self.last_call = datetime.now(utc)
        debug_log("准备发送消息..")
        train: Message[str] = Message[str].model_validate(self.train)
        assert isinstance(train.content, str)
        data = self.data
        train.content += (
            f"\n以下是一些补充内容，如果与上面任何一条有冲突请忽略。\n<EXTRA>\n{data.prompt if data.prompt != '' else '无'}\n<EXTRA>"
            if self.config.function.allow_custom_prompt
            else ""
        )
        messages = [Message.model_validate(train), *copy.deepcopy(data.memory.messages)]
        debug_log(f"发送消息准备完成，共 {len(messages)} 条消息")
        return messages

    async def _handle_reply(
        self, reply: Reply, bot: Bot, group_id: int | None, content: str
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
        self.last_call = datetime.now(utc)
        if not reply.sender.user_id:
            return content
        dt_object = datetime.fromtimestamp(reply.time)
        weekday = dt_object.strftime("%A")
        formatted_time = dt_object.strftime("%Y-%m-%d %I:%M:%S %p")
        role = (
            await self._get_user_role(group_id, reply.sender.user_id)
            if group_id
            else ""
        )

        reply_content = await synthesize_message(reply.message, bot)
        result = f"{content}\n<引用的消息>\n{formatted_time} {weekday} [{role}]{reply.sender.nickname}（QQ:{reply.sender.user_id}）说：{reply_content}\n</引用的消息>"
        debug_log(f"处理引用消息完成: {result[:50]}..")
        return result

    def _get_reply_pics(
        self,
    ) -> list[ImageContent]:
        """获取引用消息中的图片内容

        Returns:
            图片内容列表
        """
        self.last_call = datetime.now(utc)
        if reply := self.event.reply:
            msg = reply.message
            images = [
                ImageContent(image_url=ImageUrl(url=url))
                for seg in msg
                if seg.type == "image" and (url := seg.data.get("url")) is not None
            ]
            debug_log(f"获取引用图片完成，共 {len(images)} 张")
            return images
        return []

    async def _get_user_role(self, group_id: int, user_id: int) -> str:
        """获取用户在群聊中的身份（群主、管理员或普通成员）。

        Args:
            group_id: 群组ID
            user_id: 用户ID

        Returns:
            用户角色字符串
        """
        self.last_call = datetime.now(utc)
        role_data = await self.bot.get_group_member_info(
            group_id=group_id, user_id=user_id
        )
        role = role_data["role"]
        role_str = {"admin": "群管理员", "owner": "群主", "member": "普通成员"}.get(
            role, "[获取身份失败]"
        )
        debug_log(f"获取用户角色完成: {role_str}")
        return role_str

    async def _manage_sessions(
        self,
    ):
        """管理会话上下文：
        - 控制会话超时和历史记录。
        - 提供"继续"功能以恢复上下文。

        """
        self.last_call = datetime.now(utc)
        debug_log("开始管理会话上下文..")
        event = self.event
        data = self.data
        matcher = self.matcher
        bot = self.bot
        config = self.config
        if config.session.session_control:
            session_clear_map: dict[str, SessionTemp] = (
                chat_manager.session_clear_group
                if isinstance(event, GroupEvent)
                else chat_manager.session_clear_user
            )
            session_id = str(
                event.group_id
                if isinstance(event, GroupMessageEvent)
                else event.user_id
            )
            try:
                if session := session_clear_map.get(session_id):
                    debug_log(f"找到会话清除记录: {session_id}")
                    if "继续" not in event.message.extract_plain_text():
                        debug_log("消息中不包含'继续'，清除会话记录")
                        del session_clear_map[session_id]
                        return

                # 检查会话超时
                time_now = time.time()
                debug_log(
                    f"检查会话超时，当前时间: {time_now}, 数据时间戳: {data.timestamp}"
                )
                if (time_now - data.timestamp) >= (
                    float(ConfigManager().config.session.session_control_time * 60)
                ):
                    debug_log("会话超时，开始创建新会话..")
                    data.sessions.append(
                        SessionMemoryModel(messages=data.memory.messages, time=time_now)
                    )
                    if (
                        len(data.sessions)
                        > ConfigManager().config.session.session_control_history
                    ):
                        offset = (
                            len(data.sessions)
                            - ConfigManager().config.session.session_control_history
                        )
                        dropped_sesssions = data.sessions[:offset]
                        data.sessions = data.sessions[offset:]
                        async with get_session() as session:
                            for i in dropped_sesssions:
                                try:
                                    debug_log(f"删除过期会话: {i.id}")
                                    await i.delete(session)
                                except Exception as e:  # noqa: PERF203
                                    logger.warning(f"删除Session{i.id}失败\n{e}")
                            await session.commit()
                    data.memory.messages = []
                    timestamp = data.timestamp
                    data.timestamp = time_now
                    await data.save(event, raise_err=True)
                    if not (
                        (time_now - timestamp)
                        > float(config.session.session_control_time * 60 * 2)
                    ):
                        debug_log("发送继续聊天提示")
                        chated = await matcher.send(
                            f'如果想和我继续用之前的上下文聊天，快at我回复✨"继续"✨吧！\n（超过{config.session.session_control_time}分钟没理我我就会被系统抱走存档哦！）'
                        )
                        session_clear_map[session_id] = SessionTemp(
                            message_id=chated["message_id"], timestamp=datetime.now()
                        )

                        return await matcher.finish()

                elif (
                    session := session_clear_map.get(session_id)
                ) and "继续" in event.message.extract_plain_text():
                    debug_log("检测到'继续'消息，恢复上下文..")
                    with contextlib.suppress(Exception):
                        if time_now - session.timestamp.timestamp() < 100:
                            await bot.delete_msg(message_id=session.message_id)

                    session_clear_map.pop(session_id, None)

                    data.memory.messages = data.sessions[-1].messages
                    session = data.sessions.pop()
                    await session.delete()
                    await data.save(event, raise_err=True)
                    return await matcher.finish("让我们继续聊天吧～")

            finally:
                data.timestamp = time.time()
                debug_log("会话上下文管理完成")

    async def _throw(self, e: BaseException):
        """处理异常：
        - 通知用户出错。
        - 记录日志并通知管理员。

        Args:
            e: 异常对象
        """
        if isinstance(e, CancelledError):
            if hasattr(self, "matcher"):
                await self.matcher.send("成功终止了对话。")
            return
        self._err = e
        if hasattr(self, "matcher"):
            await self.matcher.send("出错了稍后试试吧（错误已反馈）")
        logger.opt(exception=e, colors=True).exception("程序发生了未捕获的异常")

    def get_snapshot(self) -> ChatObjectMeta:
        """获取聊天对象的快照

        Returns:
            聊天对象元数据
        """
        return ChatObjectMeta.model_validate(self, from_attributes=True)


class SessionTemp(BaseModel):
    message_id: int
    timestamp: datetime = Field(default_factory=datetime.now)


@dataclass
class ChatManager:
    session_clear_group: dict[str, SessionTemp] = field(default_factory=dict)
    session_clear_user: dict[str, SessionTemp] = field(default_factory=dict)
    custom_menu: list[dict[str, str]] = field(default_factory=list)
    running_messages_poke: dict[str, Any] = field(default_factory=dict)
    running_chat_object: defaultdict[tuple[int, bool], list[ChatObject]] = field(
        default_factory=lambda: defaultdict(list)
    )
    running_chat_object_id2map: dict[str, ChatObjectMeta] = field(default_factory=dict)
    menu_msg = """SuggarChat 菜单:
/chat - 发送消息与AI对话
/show-abstract - 查看当前会话的摘要
/prompt <提示词内容> - 设置系统提示词，用于指导AI回复
/presets - 查看所有可用的预设列表
/set_preset <预设名> - 设置当前会话使用的预设
/debug - 切换调试模式，用于查看详细日志
/autochat <on|off> - 切换自动回复模式
/choose_prompt - 从预设提示词中选择一个
/sessions [list|clear|set|del|archive|help] - 管理当前所有会话
/del_memory - 删除AI的历史记忆
/enable - 在当前群组启用AI聊天功能
/disable - 在当前群组禁用AI聊天功能
/insights [global] - 查看今日AI用量统计
/test_preset [-d|--details] - 测试所有预设,--details查看详细结果
/mcp <stats [-d|--details];add <server_script>;del <server_script>;reload> - 管理MCP服务
/chatobj - 显示所有会话状态
/chatobj status - 显示所有会话状态
/chatobj terminate <ID前缀> - 终止指定会话
/chatobj kill <ID前缀> - 终止指定会话
/chatobj clear - 清除已完成的会话(仅保留最近10个会话)"""

    def clean_obj(self, k: tuple[int, bool], maxitems: int = 10):
        """
        清理指定键下的运行中的聊天对象，只保留前10个对象，超出的未完成部分会被删除

        Args:
            k (tuple[int, bool]): 键值，由实例ID和是否为群聊组成
            maxitems (int, optional): 最大对象数. Defaults to 10.
        """
        objs = self.running_chat_object[k]
        if len(objs) > maxitems:
            dropped_obj = objs[maxitems:]
            objs = [obj for obj in dropped_obj if not obj.is_done()] + objs[:maxitems]
            dropped_obj = [obj for obj in dropped_obj if obj.is_done()]
            for obj in dropped_obj:
                self.running_chat_object_id2map.pop(obj.stream_id, None)
            self.running_chat_object[k] = objs

    def get_obj_key(self, event: MessageEvent) -> tuple[int, bool]:
        """
        从消息事件中提取对象键值，用于标识用户或群组的聊天会话

        Args:
            event (MessageEvent): 消息事件

        Returns:
            tuple[int, bool]: 由实例ID和是否为群聊组成的键值
        """
        is_group: bool = hasattr(event, "group_id")
        ins_id: int = getattr(event, "group_id", event.user_id)
        return (ins_id, is_group)

    def get_all_objs(self) -> list[ChatObjectMeta]:
        """
        获取所有运行中的聊天对象元数据

        Returns:
            list[ChatObjectMeta]: 所有运行中的聊天对象元数据列表
        """
        return list(self.running_chat_object_id2map.values())

    def get_objs(self, event: MessageEvent) -> list[ChatObject]:
        """
        根据消息事件获取对应的聊天对象列表

        Args:
            event (MessageEvent): 消息事件

        Returns:
            list[ChatObject]: 聊天对象列表
        """
        key: tuple[int, bool] = self.get_obj_key(event)
        return self.running_chat_object[key]

    async def clean_chat_objects(self, maxitems: int = 10) -> None:
        """
        异步清理所有运行中的聊天对象，限制每个键对应的对象数量不超过10个
        """
        async with LOCK:
            for key in self.running_chat_object.keys():
                self.clean_obj(key, maxitems)

    async def add_chat_object(self, chat_object: ChatObject) -> None:
        """
        添加新的聊天对象到运行列表中

        Args:
            chat_object (ChatObject): 聊天对象实例
        """
        async with LOCK:
            meta: ChatObjectMeta = chat_object.get_snapshot()
            self.running_chat_object_id2map[chat_object.stream_id] = meta
            key: tuple[int, bool] = self.get_obj_key(meta.event)
            self.running_chat_object[key].insert(0, chat_object)
            self.clean_obj(key, ConfigManager().config.function.chat_object_keep_count)


chat_manager = ChatManager()
