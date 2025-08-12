import asyncio
import random
import sys
import traceback

from nonebot import logger
from nonebot.adapters.onebot.v11 import Bot, MessageSegment
from nonebot.adapters.onebot.v11.event import PokeNotifyEvent
from nonebot.matcher import Matcher

from ..chatmanager import chat_manager
from ..config import config_manager
from ..event import BeforePokeEvent, PokeEvent  # 自定义事件类型
from ..matcher import MatcherManager  # 自定义匹配器
from ..utils.admin import send_to_admin
from ..utils.functions import (
    get_friend_name,
    split_message_into_chats,
)
from ..utils.libchat import get_chat, usage_enough
from ..utils.lock import get_group_lock, get_private_lock
from ..utils.memory import get_memory_data


async def poke_event(event: PokeNotifyEvent, bot: Bot, matcher: Matcher):
    """处理戳一戳事件"""

    async def handle_group_poke(event: PokeNotifyEvent, bot: Bot):
        """处理群聊中的戳一戳事件"""
        Group_Data = await get_memory_data(event=event)  # 获取群聊相关数据
        event_data = event.model_dump(exclude={"group_id"})
        event_data["group_id"] = None
        u_event = PokeNotifyEvent.model_validate(event_data)
        u_data = await get_memory_data(event=u_event)
        if config_manager.config.usage_limit.enable_usage_limit:
            if (
                data.usage >= config_manager.config.usage_limit.group_daily_limit
                and config_manager.config.usage_limit.group_daily_limit != -1
            ):
                await matcher.finish()
            elif (
                u_data.usage >= config_manager.config.usage_limit.user_daily_limit
                and config_manager.config.usage_limit.user_daily_limit != -1
            ):
                await matcher.finish()
        if not Group_Data["enable"]:  # 如果群聊功能未启用，直接返回
            return
        if not event.group_id:  # 如果群组ID不存在，直接返回
            return

        # 获取用户昵称
        user_name = (
            await bot.get_group_member_info(
                group_id=event.group_id, user_id=event.user_id
            )
        )["nickname"]

        # 构造发送的消息
        send_messages = [
            {"role": "system", "content": f"{config_manager.group_train}"},
            {
                "role": "user",
                "content": f"\\（戳一戳消息\\){user_name} (QQ:{event.user_id}) 戳了戳你",
            },
        ]

        # 处理戳一戳事件并获取回复
        response = await process_poke_event(event, send_messages)
        message = (
            MessageSegment.at(user_id=event.user_id)
            + MessageSegment.text(" ")
            + MessageSegment.text(response)
        )

        # 根据配置决定消息发送方式
        if not config_manager.config.function.nature_chat_style:
            await matcher.send(message)
        else:
            await send_split_messages(response, event.user_id)

    async def handle_private_poke(event: PokeNotifyEvent, bot: Bot):
        """处理私聊中的戳一戳事件"""
        if (
            data.usage >= config_manager.config.usage_limit.user_daily_limit
            and config_manager.config.usage_limit.enable_usage_limit
            and config_manager.config.usage_limit.user_daily_limit != -1
        ):
            await matcher.finish()

        name = await get_friend_name(event.user_id, bot)  # 获取好友信息
        send_messages = [
            {"role": "system", "content": f"{config_manager.private_train}"},
            {
                "role": "user",
                "content": f" \\（戳一戳消息\\) {name}(QQ:{event.user_id}) 戳了戳你",
            },
        ]

        # 处理戳一戳事件并获取回复
        response = await process_poke_event(event, send_messages)
        if not config_manager.config.function.nature_chat_style:
            await matcher.send(MessageSegment.text(response))
        else:
            await send_split_messages(response, event.user_id)

    async def process_poke_event(event: PokeNotifyEvent, send_messages: list) -> str:
        """处理戳一戳事件的核心逻辑"""
        if config_manager.config.matcher_function:
            # 触发自定义事件前置处理

            poke_event = BeforePokeEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[""],
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(poke_event, event, bot)
            send_messages = poke_event.get_send_message()

        # 获取聊天模型的回复
        response = await get_chat(send_messages)
        data.usage += 1  # 增加使用次数
        await data.save(event)  # 保存数据

        if config_manager.config.matcher_function:
            # 触发自定义事件后置处理
            poke_event = PokeEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[response],
                user_id=event.user_id,
            )
            await MatcherManager.trigger_event(poke_event, event, bot)
            response = poke_event.model_response

        # 如果开启调试模式，发送调试信息给管理员
        if chat_manager.debug:
            await send_to_admin(f"POKEMSG {send_messages}")

        return response

    async def send_split_messages(response: str, user_id: int):
        """发送分段消息"""
        if response_list := split_message_into_chats(response):  # 将消息分段
            first_message = (
                MessageSegment.at(user_id) + MessageSegment.text(" ") + response_list[0]
            )
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

    # 主逻辑入口
    if (
        not config_manager.config.enable
        or not config_manager.config.function.poke_reply
    ):
        matcher.skip()  # 如果功能未启用或未配置戳一戳回复，跳过处理

    if event.target_id != event.self_id:  # 如果目标不是机器人本身，直接返回
        return
    data = await get_memory_data(event)  # 获取用户或群组相关数据
    try:
        if not await usage_enough(event):  # 检查用户或群组使用次数是否超出限制
            return
        if event.group_id is not None:  # 判断是群聊还是私聊
            async with get_group_lock(event.group_id):
                await handle_group_poke(event, bot)
        else:
            async with get_private_lock(event.user_id):
                await handle_private_poke(event, bot)
    except Exception:
        await handle_poke_exception()  # 异常处理
