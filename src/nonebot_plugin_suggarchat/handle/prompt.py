from nonebot.adapters import Bot, Message
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager
from ..resources import get_memory_data, write_memory_data
from ..utils import is_member


async def prompt(
    bot: Bot, event: GroupMessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """处理prompt命令的异步函数。此函数根据不同的条件和用户输入来管理prompt的设置和查询"""
    # 检查是否启用prompt功能，未启用则跳过处理
    if not config_manager.config.enable:
        matcher.skip()
    # 检查是否允许自定义prompt，不允许则结束处理
    if not config_manager.config.allow_custom_prompt:
        await matcher.finish("当前不允许自定义prompt。")

    # 检查用户是否为群成员且非管理员，是则结束处理
    if (
        await is_member(event, bot)
        and event.user_id not in config_manager.config.admins
    ):
        await matcher.finish("群成员不能设置matcher.")

    data = get_memory_data(event)
    arg = args.extract_plain_text().strip()

    # 检查输入长度是否过长，过长则提示用户并返回
    if len(arg) >= 1000:
        await matcher.send("prompt过长，预期的参数不超过1000字。")
        return

    # 检查输入是否为空，为空则提示用户如何使用命令
    if arg.strip() == "":
        await matcher.send(
            "请输入prompt或参数（--(show) 展示当前提示词，--(clear) 清空当前prompt，--(set) [文字]则设置提示词，e.g.:/prompt --(show)）,/prompt --(set) [text]。）"
        )
        return

    # 根据用户输入的不同命令进行相应的处理
    if arg.startswith("--(show)"):
        await matcher.send(f"Prompt:\n{data.get('prompt', '未设置prompt')}")
        return
    elif arg.startswith("--(clear)"):
        data["prompt"] = ""
        await matcher.send("prompt已清空。")
    elif arg.startswith("--(set)"):
        arg = arg.replace("--(set)", "").strip()
        data["prompt"] = arg
        await matcher.send(f"prompt已设置为：\n{arg}")
    else:
        await matcher.send(
            "请输入prompt或参数（--(show) 展示当前提示词，--(clear) 清空当前prompt，--(set) [文字]则设置提示词，e.g.:/prompt --(show)）,/prompt --(set) [text]。"
        )
        return

    # 更新记忆数据
    write_memory_data(event, data)
