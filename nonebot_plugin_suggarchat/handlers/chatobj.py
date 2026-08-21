import contextlib
from datetime import datetime

from amrita_core.chatmanager import ChatObject
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from pytz import timezone, utc

from ..runtime import bot_chat_manager, pending_chatobj, try_get_amrita_ctx
from ..utils.send import send_forward_msg
from ..utils.sql import get_uni_user_id


def get_chat_objects_status(event: MessageEvent) -> dict[str, list[ChatObject]]:
    """获取所有ChatObject的状态分类。

    通过隐式锁队列追踪 pending（等待锁）状态。
    """
    running_objects: list[ChatObject] = []
    pending_objects: list[ChatObject] = []
    done_objects: list[ChatObject] = []
    error_objects: list[ChatObject] = []

    uni_id = get_uni_user_id(event)
    all_objects = bot_chat_manager.get_objs(uni_id)

    # pending：仍在 waiting_tasks 且未完成的 ChatObject
    pending_task_ids: set[int] = {
        id(t)
        for t in pending_chatobj.get(uni_id, [])
        if (not t.is_running() and not t.is_done())
    }
    remaining: list[ChatObject] = []
    for obj in all_objects:
        if id(obj) in pending_task_ids:
            pending_objects.append(obj)
        else:
            remaining.append(obj)

    for obj in remaining:
        if obj.get_exception():
            error_objects.append(obj)
        elif obj.is_done():
            done_objects.append(obj)
        else:
            running_objects.append(obj)

    return {
        "running": running_objects,
        "pending": pending_objects,
        "done": done_objects,
        "error": error_objects,
    }


def format_chat_object_info(obj: ChatObject) -> str:
    """格式化单个ChatObject的信息。

    通过 try_get_amrita_ctx 读取 event 上下文。
    """
    ctx = try_get_amrita_ctx(obj)
    if ctx is None:
        return f"\n🆔 ID: {obj.stream_id[:8]}...\n> 无上下文信息\n"
    event = ctx["event"]
    user_id = event.user_id
    instance_id = get_uni_user_id(event)

    # 检查是否在隐式锁队列中 pending
    in_pending = id(obj) in {
        id(t)
        for t in pending_chatobj.get(instance_id, [])
        if (not t.is_running() and not t.is_done())
    }

    if in_pending:
        status = "⏳ Pending"
    elif obj.get_exception():
        status = f"❌ Error ({type(obj.get_exception()).__name__})"
    elif obj.is_done():
        status = "✅ Done"
    elif obj.is_running():
        status = "🟢 Running"
    else:
        status = "❓ Unknown"

    time_diff = (datetime.now(tz=utc) - obj.last_call).total_seconds()
    time_cost: float = (obj.end_at - obj.time).total_seconds() if obj.end_at else 0

    info = (
        f"\n🆔 ID: {obj.stream_id[:8]}...\n"
        + f"💬 类型: {'👥 群聊' if getattr(event, 'group_id', None) is not None else '👤 私聊'}\n"
        + f"👤 用户ID: {user_id}\n"
        + f"🔢 会话ID: {instance_id}\n"
        + f">Status: {status}\n"
        + f"⏱️ 最后活动: {time_diff:.0f}s前\n"
        + f"🕐 时间: {obj.time.astimezone(timezone('Asia/Shanghai')).strftime('%H:%M:%S')}(UTC+8:00)\n"
        + (f"🕐 消耗时间：{time_cost:.0f}s" if time_cost else "")
    )

    return info


async def send_status_report(
    bot: Bot, event: MessageEvent, status_dict: dict[str, list[ChatObject]]
) -> None:
    """发送状态报告"""
    report_parts = ["📋【会话运行状态】"]

    status_names = {
        "running": "🟢 运行中 (Running)",
        "pending": "⏳ 等待中 (Pending)",
        "done": "✅ 已完成 (Done)",
        "error": "❌ 错误 (Error)",
    }

    for status_type, objects in status_dict.items():
        s_part = f"\n🔸--- {status_names[status_type]} ({len(objects)}) ---"
        if objects:
            s_part += "\n".join([format_chat_object_info(obj) for obj in objects])
        else:
            s_part += " 无"
        report_parts.append(s_part)
    await send_forward_msg(
        bot,
        event,
        "Amrita-ChatOBJ",
        uin=str(event.self_id),
        msgs=[MessageSegment.text(i) for i in report_parts],
    )


async def terminate_chat_object(stream_id: str, event: MessageEvent) -> bool:
    """终止指定的ChatObject"""
    all_objects = bot_chat_manager.get_objs(get_uni_user_id(event))
    for obj in all_objects:
        if obj.stream_id.startswith(stream_id):  # 支持ID前缀匹配
            if obj.is_running():
                with contextlib.suppress(Exception):
                    obj.terminate()
                return True
            break

    return False


async def chatobj_manage(
    event: MessageEvent, matcher: Matcher, bot: Bot, args: Message = CommandArg()
):
    """处理chatobj命令"""
    plain_args = args.extract_plain_text().strip().lower()

    if plain_args in ["", "status", "show"]:
        # 显示所有ChatObject的状态
        status_dict = get_chat_objects_status(event)
        await send_status_report(bot, event, status_dict)

    elif plain_args in ("kill", "terminate"):
        # 仅输入 "kill" 或 "terminate"，没有指定ID，尝试杀死最后一个活动的会话
        all_objects = bot_chat_manager.get_objs(get_uni_user_id(event))
        active_objects = [obj for obj in all_objects if obj.is_running()]
        active_objects.sort(key=lambda obj: obj.last_call, reverse=True)

        if active_objects:
            last_active_obj = active_objects[0]
            with contextlib.suppress(Exception):
                last_active_obj.terminate()
            await matcher.finish(
                f"✅ 已尝试终止最后一个活动的会话 (ID: {last_active_obj.stream_id[:8]}...)"
            )
        else:
            await matcher.finish("❌ 没有找到任何活动的会话")

    elif plain_args.startswith("terminate ") or plain_args.startswith("kill "):
        # 终止指定的ChatObject
        stream_id_prefix = plain_args.split(" ", 1)[1] if " " in plain_args else ""
        if len(stream_id_prefix) < 4:  # 至少需要4位前缀
            await matcher.finish("⚠️ 请输入至少4位的ID前缀来终止会话")
        elif stream_id_prefix == "all":
            for obj in bot_chat_manager.get_objs(get_uni_user_id(event)):
                with contextlib.suppress(Exception):
                    obj.terminate()
            await matcher.finish("⚠️ 已终止所有匹配的会话")

        success = await terminate_chat_object(stream_id_prefix, event)
        if success:
            await matcher.finish(f"✅ 已尝试终止ID为 '{stream_id_prefix}' 的会话")
        else:
            await matcher.finish(
                f"❌ 未找到匹配ID前缀为 '{stream_id_prefix}' 的运行中会话"
            )

    elif plain_args in ("clear", "clean"):
        bot_chat_manager.clean_obj(get_uni_user_id(event), maxitems=0)
        await matcher.finish("🧹 已清除已完成的会话")

    elif plain_args == "help":
        help_text = (
            "ℹ️ ChatObject管理命令:\n"
            "🔸 /chatobj - 显示所有会话状态\n"
            "🔸 /chatobj status - 显示所有会话状态\n"
            "🔸 /chatobj terminate <ID前缀|all> - 终止指定会话(或者所有)\n"
            "🔸 /chatobj kill <ID前缀|all> - 终止指定会话(或者所有)\n"
            "🔸 /chatobj kill - 终止最后一个活动的会话\n"
            "🔸 /chatobj clear - 清除已完成的会话\n"
            "🔸 /chatobj help - 显示此帮助"
        )
        await matcher.finish(help_text)

    else:
        await matcher.finish("⚠️ 无效的命令参数，使用 '/chatobj help' 查看帮助")
