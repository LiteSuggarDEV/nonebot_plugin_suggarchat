import asyncio
import contextlib
import random
import sys
import time
import traceback
from datetime import datetime

from nonebot import logger
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import (
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

from ..chatmanager import chat_manager
from ..config import config_manager
from ..event import ChatEvent, EventType
from ..exception import CancelException
from ..matcher import SuggarMatcher
from ..resources import (
    get_current_datetime_timestamp,
    get_friend_info,
    get_memory_data,
    hybrid_token_count,
    split_message_into_chats,
    synthesize_message,
    write_memory_data,
)
from ..utils import get_chat, send_to_admin


async def chat(event: MessageEvent, matcher: Matcher, bot: Bot):
    """处理聊天事件"""

    async def handle_group_message(
        event: GroupMessageEvent,
        matcher: Matcher,
        bot: Bot,
        group_data: dict,
        memory_length_limit: int,
        Date: str,
    ):
        if not config_manager.config.enable_group_chat:
            matcher.skip()

        if not group_data["enable"]:
            await matcher.send("聊天没有启用")
            return

        await manage_sessions(event, group_data, chat_manager.session_clear_group)

        group_id = event.group_id
        user_id = event.user_id
        user_name = (
            await bot.get_group_member_info(group_id=group_id, user_id=user_id)
        )["nickname"]
        content = await synthesize_message(event.get_message(), bot)

        if content.strip() == "":
            content = ""

        role = await get_user_role(bot, group_id, user_id)
        logger.debug(f"{Date}{user_name}（{user_id}）说:{content}")

        if event.reply:
            content = await handle_reply(event.reply, bot, group_id, content)

        group_data["memory"]["messages"].append(
            {
                "role": "user",
                "content": f"[{role}][{Date}][{user_name}（{user_id}）]说:{content if config_manager.config.parse_segments else event.message.extract_plain_text()}",
            }
        )

        await enforce_memory_limit(group_data, memory_length_limit)
        await enforce_token_limit(group_data, config_manager.group_train)

        send_messages = prepare_send_messages(group_data, config_manager.group_train)
        response = await process_chat(event, send_messages)

        group_data["memory"]["messages"].append(
            {"role": "assistant", "content": str(response)}
        )
        await send_response(event, response)

        write_memory_data(event, group_data)

    async def handle_private_message(
        event: PrivateMessageEvent,
        matcher: Matcher,
        bot: Bot,
        private_data: dict,
        memory_length_limit: int,
        Date: str,
    ):
        if not config_manager.config.enable_private_chat:
            matcher.skip()

        await manage_sessions(event, private_data, chat_manager.session_clear_user)

        content = await synthesize_message(event.get_message(), bot)

        if content.strip() == "":
            content = ""

        if event.reply:
            content = await handle_reply(event.reply, bot, None, content)

        private_data["memory"]["messages"].append(
            {
                "role": "user",
                "content": f"{Date}{await get_friend_info(event.user_id, bot=bot)}（{event.user_id}）： {str(content) if config_manager.config.parse_segments else event.message.extract_plain_text()}",
            }
        )

        await enforce_memory_limit(private_data, memory_length_limit)
        await enforce_token_limit(private_data, config_manager.private_train)

        send_messages = prepare_send_messages(
            private_data, config_manager.private_train
        )
        response = await process_chat(event, send_messages)

        private_data["memory"]["messages"].append(
            {"role": "assistant", "content": str(response)}
        )
        await send_response(event, response)

        write_memory_data(event, private_data)

    async def manage_sessions(
        event: GroupMessageEvent | PrivateMessageEvent,
        data: dict,
        session_clear_list: list,
    ):
        if data.get("sessions") is None:
            data["sessions"] = []
        if data.get("timestamp") is None:
            data["timestamp"] = time.time()

        if config_manager.config.session_control:
            for session in session_clear_list:
                if session["id"] == (
                    event.group_id
                    if isinstance(event, GroupMessageEvent)
                    else event.user_id
                ):
                    if not event.reply:
                        session_clear_list.remove(session)
                        return
                    break

            if (time.time() - data["timestamp"]) >= (
                config_manager.config.session_control_time * 60
            ):
                data["sessions"].append(
                    {"messages": data["memory"]["messages"], "time": time.time()}
                )
                while (
                    len(data["sessions"])
                    > config_manager.config.session_control_history
                ):
                    data["sessions"].remove(data["sessions"][0])
                data["memory"]["messages"] = []
                data["timestamp"] = time.time()
                write_memory_data(event, data)
                chated = await matcher.send(
                    f'如果想和我继续用刚刚的上下文聊天，快回复我✨"继续"✨吧！\n（超过{config_manager.config.session_control_time}分钟没理我我就会被系统抱走存档哦！）'
                )
                session_clear_list.append(
                    {
                        "id": (
                            event.group_id
                            if isinstance(event, GroupMessageEvent)
                            else event.user_id
                        ),
                        "message_id": chated["message_id"],
                        "timestamp": time.time(),
                    }
                )
                raise CancelException()
            elif event.reply:
                for session in session_clear_list:
                    if (
                        session["id"]
                        == (
                            event.group_id
                            if isinstance(event, GroupMessageEvent)
                            else event.user_id
                        )
                        and "继续" in event.reply.message.extract_plain_text()
                    ):
                        with contextlib.suppress(Exception):
                            if time.time() - session["timestamp"] < 100:
                                await bot.delete_msg(message_id=session["message_id"])
                        session_clear_list.remove(session)
                        data["memory"]["messages"] = data["sessions"][-1]["messages"]
                        data["sessions"].pop()
                        await matcher.send("让我们继续聊天吧～")
                        write_memory_data(event, data)
                        raise CancelException()

    async def handle_reply(
        reply: Reply, bot: Bot, group_id: int | None, content: str
    ) -> str:
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

    async def get_user_role(bot: Bot, group_id: int, user_id: int) -> str:
        role = (await bot.get_group_member_info(group_id=group_id, user_id=user_id))[
            "role"
        ]
        return {"admin": "群管理员", "owner": "群主", "member": "普通成员"}.get(
            role, "[获取身份失败]"
        )

    async def enforce_memory_limit(data: dict, memory_length_limit: int):
        while len(data["memory"]["messages"]) > memory_length_limit or (
            data["memory"]["messages"][0]["role"] != "user"
        ):
            del data["memory"]["messages"][0]

    async def enforce_token_limit(data: dict, train: dict):
        if config_manager.config.enable_tokens_limit:
            memory_l = [train.copy(), *data["memory"]["messages"].copy()]
            full_string = "".join(st["content"] for st in memory_l)
            tokens = hybrid_token_count(
                full_string, config_manager.config.tokens_count_mode
            )
            while tokens > config_manager.config.session_max_tokens:
                del data["memory"]["messages"][0]
                full_string = "".join(
                    st["content"]
                    for st in [train.copy(), *data["memory"]["messages"].copy()]
                )
                tokens = hybrid_token_count(
                    full_string, config_manager.config.tokens_count_mode
                )

    def prepare_send_messages(data: dict, train: dict) -> list:
        train["content"] += (
            f"\n以下是一些补充内容，如果与上面任何一条有冲突请忽略。\n{data.get('prompt', '无')}"
        )
        send_messages = data["memory"]["messages"].copy()
        send_messages.insert(0, train)
        return send_messages

    async def process_chat(event: MessageEvent, send_messages: list) -> str:
        if config_manager.config.matcher_function:
            _matcher = SuggarMatcher(event_type=EventType().before_chat())
            chat_event = ChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[""],
                user_id=event.user_id,
            )
            await _matcher.trigger_event(chat_event, _matcher)
            send_messages = chat_event.get_send_message()

        response = await get_chat(send_messages)

        if config_manager.config.matcher_function:
            _matcher = SuggarMatcher(event_type=EventType().chat())
            chat_event = ChatEvent(
                nbevent=event,
                send_message=send_messages,
                model_response=[response],
                user_id=event.user_id,
            )
            await _matcher.trigger_event(chat_event, _matcher)
            response = chat_event.model_response

        return response

    async def send_response(event: MessageEvent, response: str):
        if not config_manager.config.nature_chat_style:
            await matcher.send(
                MessageSegment.reply(event.message_id) + MessageSegment.text(response)
            )
        elif response_list := split_message_into_chats(response):
            for index, message in enumerate(response_list):
                if index == 0:
                    if isinstance(event, GroupMessageEvent):
                        await matcher.send(
                            MessageSegment.at(event.user_id)
                            + MessageSegment.text(message)
                        )
                    else:
                        await matcher.send(MessageSegment.text(message))
                else:
                    await matcher.send(MessageSegment.text(message))
                await asyncio.sleep(
                    random.randint(1, 3) + (len(message) // random.randint(80, 100))
                )

    async def handle_exception():
        await matcher.send("出错了稍后试试吧（错误已反馈）")

        exc_type, exc_value, _ = sys.exc_info()

        # 使用 logger.exception 自动附带 traceback
        logger.exception("程序发生了未捕获的异常")

        # 通知管理员
        await send_to_admin(f"出错了！{exc_value},\n{exc_type!s}")
        await send_to_admin(traceback.format_exc())

    # 函数进入运行点
    if not config_manager.config.enable:
        matcher.skip()

    memory_length_limit = config_manager.config.memory_lenth_limit
    Date = get_current_datetime_timestamp()

    if event.message.extract_plain_text().strip().startswith("/"):
        matcher.skip()

    if event.message.extract_plain_text().startswith("菜单"):
        await matcher.finish(chat_manager.menu_msg)

    try:
        if isinstance(event, GroupMessageEvent):
            group_data = get_memory_data(event)
            await handle_group_message(
                event, matcher, bot, group_data, memory_length_limit, Date
            )
        elif isinstance(event, PrivateMessageEvent):
            private_data = get_memory_data(event)
            await handle_private_message(
                event, matcher, bot, private_data, memory_length_limit, Date
            )
        else:
            matcher.skip()
    except NoneBotException as e:
        raise e
    except CancelException:
        return
    except Exception:
        await handle_exception()
