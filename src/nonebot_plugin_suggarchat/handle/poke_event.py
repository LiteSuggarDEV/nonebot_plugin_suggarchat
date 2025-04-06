import asyncio
import random
import sys
import traceback

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager
from ..config import config_manager
from ..event import EventType, PokeEvent
from ..matcher import SuggarMatcher
from ..resources import (
    get_friend_info,
    get_memory_data,
    split_message_into_chats,
)
from ..utils import get_chat, send_to_admin


async def poke_event(event: PokeNotifyEvent, bot: Bot, matcher: Matcher):
    """处理戳一戳事件"""

    async def handle_group_poke(event: PokeNotifyEvent, bot: Bot):
        """处理群聊中的戳一戳事件"""
        Group_Data = get_memory_data(event)
        if not Group_Data["enable"]:
            return

        user_name = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["nickname"]

        send_messages = [
            {"role": "system", "content": f"{config_manager.group_train}"},
            {
                "role": "user",
                "content": f"\\（戳一戳消息\\){user_name} (QQ:{event.user_id}) 戳了戳你",
            },
        ]

        response = await process_poke_event(event, send_messages)
        message = (
            MessageSegment.at(user_id=event.user_id)
            + MessageSegment.text(" ")
            + MessageSegment.text(response)
        )

        if not config_manager.config.nature_chat_style:
            await matcher.send(message)
        else:
            await send_split_messages(response, event.user_id)

    async def handle_private_poke(event: PokeNotifyEvent, bot: Bot):
        """处理私聊中的戳一戳事件"""
        name = get_friend_info(event.user_id, bot)
        send_messages = [
            {"role": "system", "content": f"{config_manager.private_train}"},
            {
                "role": "user",
                "content": f" \\（戳一戳消息\\) {name}(QQ:{event.user_id}) 戳了戳你",
            },
        ]

        response = await process_poke_event(event, send_messages)
        if not config_manager.config.nature_chat_style:
            await matcher.send(MessageSegment.text(response))
        else:
            await send_split_messages(response, event.user_id)

    async def process_poke_event(event: PokeNotifyEvent, send_messages: list) -> str:
        """处理戳一戳事件的核心逻辑"""
        if config_manager.config.matcher_function:
            _matcher = SuggarMatcher(event_type=EventType().before_poke())
            poke_event = PokeEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[""],
                user_id=event.user_id,
            )
            await _matcher.trigger_event(poke_event, _matcher)
            send_messages = poke_event.get_send_message()

        response = await get_chat(send_messages)

        if config_manager.config.matcher_function:
            _matcher = SuggarMatcher(event_type=EventType().poke())
            poke_event = PokeEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[response],
                user_id=event.user_id,
            )
            await _matcher.trigger_event(poke_event, _matcher)
            response = poke_event.model_response

        if chat_manager.debug:
            await send_to_admin(f"POKEMSG {send_messages}")

        return response

    async def send_split_messages(response: str, user_id: int):
        """发送分段消息"""
        if response_list := split_message_into_chats(response):
            first_message = (
                MessageSegment.at(user_id) + MessageSegment.text(" ") + response_list[0]
            )
            await matcher.send(first_message)

            for message in response_list[1:]:
                await matcher.send(message)
                await asyncio.sleep(
                    random.randint(1, 3) + len(message) // random.randint(80, 100)
                )

    async def handle_poke_exception():
        """处理戳一戳事件中的异常"""
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error(
            f"Exception type: {exc_type.__name__}"
            if exc_type
            else "Exception type: None"
        )
        logger.error(f"Exception message: {exc_value!s}")

        await send_to_admin(f"出错了！{exc_value},\n{exc_type!s}")
        await send_to_admin(f"{traceback.format_exc()}")

        logger.error(
            f"Detailed exception info:\n{''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))}"
        )

    # 函数进入运行点
    if not config_manager.config.enable or not config_manager.config.poke_reply:
        matcher.skip()
        return

    if event.target_id != event.self_id:
        return

    try:
        if event.group_id is not None:
            await handle_group_poke(event, bot)
        else:
            await handle_private_poke(event, bot)
    except Exception:
        await handle_poke_exception()
