import asyncio
import random
import sys
import traceback

from amrita_core import UniResponse, UniResponseUsage, call_completion
from amrita_core.types import CONTENT_LIST_TYPE
from amrita_core.types import Message as CoreMessage
from amrita_sense.hook.event import BaseEvent
from amrita_sense.hook.matcher import MatcherFactory
from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.exception import NoneBotException
from nonebot.matcher import Matcher
from nonebot_plugin_amrita import CachedUserDataRepository
from nonebot_plugin_amrita.database import InsightsModel

from ..check_rule import FakeEvent
from ..config import config_manager
from ..utils.admin import send_to_admin
from ..utils.app import CachedGroupDataRepository as CGDR
from ..utils.functions import get_friend_name, split_message_into_chats
from ..utils.libchat import add_usage, get_tokens, usage_enough
from ..utils.lock import get_group_lock, get_private_lock
from ..utils.preset import resolve_preset
from ..utils.sql import get_uni_user_id


class PokeSendError(BaseException):
    """钩子抛出以静默拦截 poke 回复发送（不回复、不报错）"""


class PokeSendMessageEvent(BaseEvent[str]):
    """poke 回复发送前触发的事件（与 chat 的 SendMessageEvent 完全独立）

    content: 构建好的 MessageSegment，钩子可直接修改或替换
    """

    def __init__(
        self,
        content: Message,
        *,
        event: PokeNotifyEvent,
        matcher: Matcher,
        bot: Bot,
    ):
        self.content = content
        self.event = event
        self.matcher = matcher
        self.bot = bot

    def get_event_type(self) -> str:
        return "POKE_SEND_MESSAGE"

    @property
    def event_type(self) -> str:
        return "POKE_SEND_MESSAGE"


async def _trigger_poke_send(
    content: Message,
    *,
    event: PokeNotifyEvent,
    matcher: Matcher,
    bot: Bot,
) -> Message:
    """触发 poke 发送钩子，返回（可能被修改的）最终消息

    Raises:
        PokeSendError: 钩子拦截，静默不发送
    """
    ev = PokeSendMessageEvent(
        content,
        event=event,
        matcher=matcher,
        bot=bot,
    )
    await MatcherFactory.trigger_event(ev, exception_ignored=(PokeSendError,))
    return ev.content


async def poke_event(event: PokeNotifyEvent, bot: Bot, matcher: Matcher):
    """处理戳一戳事件"""
    if (
        not config_manager.config.enable
        or not config_manager.config.function.poke_reply
    ):
        matcher.skip()  # 如果功能未启用或未配置戳一戳回复，跳过处理

    if event.target_id != event.self_id:  # 如果目标不是机器人本身，直接返回
        return
    repo = CachedUserDataRepository()

    try:
        fake_event = FakeEvent(
            time=0,
            self_id=0,
            post_type="",
            user_id=event.user_id,
        )
        if not await usage_enough(event) or not await usage_enough(fake_event):
            return

        if event.group_id is not None:  # 判断是群聊还是私聊
            async with get_group_lock(event.group_id):
                await handle_group_poke(event, bot, matcher, repo)
        else:
            async with get_private_lock(event.user_id):
                await handle_private_poke(event, bot, matcher, repo)
    except NoneBotException:
        raise
    except Exception:
        await handle_poke_exception()  # 异常处理


async def handle_group_poke(
    event: PokeNotifyEvent,
    bot: Bot,
    matcher: Matcher,
    repo: CachedUserDataRepository,
):
    """处理群聊中的戳一戳事件"""
    assert event.group_id is not None
    group_config = await CGDR().get_group_config(event.group_id)
    if not group_config.enable:
        return
    if config_manager.config.usage_limit.enable_usage_limit:
        group_meta = await repo.get_metadata(get_uni_user_id(event))
        if (
            group_meta.called_count
            >= config_manager.config.usage_limit.group_daily_limit
            and config_manager.config.usage_limit.group_daily_limit != -1
        ):
            await matcher.finish()
    user_name = (
        await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
    )["nickname"]

    # 构造发送的消息
    send_messages: CONTENT_LIST_TYPE = [
        CoreMessage(role="system", content=f"{config_manager.group_train}"),
        CoreMessage(
            role="user",
            content=f"<戳一戳消息>{user_name} (QQ:{event.user_id}) 戳了戳你",
        ),
    ]
    response = await process_poke_event(event, send_messages, repo)
    message = (
        MessageSegment.at(user_id=event.user_id)
        + MessageSegment.text(" ")
        + MessageSegment.text(response)
    )

    # 触发独立钩子：允许修改或拦截（发送流程保持不变）
    message = await _trigger_poke_send(
        Message(message),
        event=event,
        matcher=matcher,
        bot=bot,
    )

    # 根据配置决定消息发送方式
    if not config_manager.config.function.nature_chat_style:
        await matcher.send(message)
    else:
        await send_split_messages(
            message.extract_plain_text(), event.user_id, matcher, is_group=True
        )


async def handle_private_poke(
    event: PokeNotifyEvent,
    bot: Bot,
    matcher: Matcher,
    repo: CachedUserDataRepository,
):
    """处理私聊中的戳一戳事件"""
    # 检查使用限制
    if (
        config_manager.config.usage_limit.enable_usage_limit
        and config_manager.config.usage_limit.user_daily_limit != -1
    ):
        user_meta = await repo.get_metadata(get_uni_user_id(event))
        if user_meta.called_count >= config_manager.config.usage_limit.user_daily_limit:
            await matcher.finish()

    name = await get_friend_name(event.user_id, bot)  # 获取好友信息
    send_messages: CONTENT_LIST_TYPE = [
        CoreMessage(role="system", content=f"{config_manager.group_train}"),
        CoreMessage(
            role="user",
            content=f"\\（戳一戳消息\\){name} (QQ:{event.user_id}) 戳了戳你",
        ),
    ]

    # 处理戳一戳事件并获取回复
    response = await process_poke_event(event, send_messages, repo)
    message = MessageSegment.text(response)

    message = await _trigger_poke_send(
        Message(message),
        event=event,
        matcher=matcher,
        bot=bot,
    )

    if not config_manager.config.function.nature_chat_style:
        await matcher.send(message)
    else:
        await send_split_messages(
            message.extract_plain_text(), event.user_id, matcher, is_group=False
        )


async def process_poke_event(
    event: PokeNotifyEvent,
    send_messages: CONTENT_LIST_TYPE,
    repo: CachedUserDataRepository,
) -> str:
    """处理戳一戳事件的核心逻辑"""
    # 直接调用completion API来处理消息
    response: UniResponse | None = None
    async for response_item in call_completion(
        messages=send_messages,
        config=config_manager.config.core,
        preset=await resolve_preset(),
    ):
        if isinstance(response_item, UniResponse):
            response = response_item

    if response is None:
        return "(发生了错误)"

    # 记录token使用情况
    tokens = get_tokens(send_messages, response)
    assert tokens is not None, "tokens is None"
    input_tokens = tokens.prompt_tokens if hasattr(tokens, "prompt_tokens") else 0
    output_tokens = (
        tokens.completion_tokens if hasattr(tokens, "completion_tokens") else 0
    )
    usage = UniResponseUsage(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )

    insights = await InsightsModel.get()
    add_usage(insights, usage)

    user_meta = await repo.get_metadata(get_uni_user_id(event))
    add_usage(user_meta, usage)
    await repo.update_metadata(user_meta)

    # 保存insights
    await insights.save()
    return response.content


async def send_split_messages(
    response: str, user_id: int, matcher: Matcher, *, is_group: bool = True
):
    """发送分段消息

    私聊不支持 at 段（协议约束），is_group=False 时剥离 at。
    """
    if response_list := split_message_into_chats(response):  # 将消息分段
        if is_group:
            first_message = (
                MessageSegment.at(user_id) + MessageSegment.text(" ") + response_list[0]
            )
        else:
            first_message = MessageSegment.text(response_list[0])
        await matcher.send(first_message)

        # 逐条发送分段消息
        for message in response_list[1:]:
            await matcher.send(message)
            await asyncio.sleep(
                random.randint(1, 3) + len(message) // random.randint(80, 100)
            )


async def handle_poke_exception():
    """处理戳一戳事件中的异常"""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    logger.exception("发生了异常")
    logger.error(f"Exception message: {exc_value!s}")

    # 将异常信息发送给管理员
    await send_to_admin(f"出错了！{exc_value},\n{exc_type!s}")
    await send_to_admin(f"{traceback.format_exc()}")

    logger.error(
        f"Detailed exception info:\n{''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}"
    )
