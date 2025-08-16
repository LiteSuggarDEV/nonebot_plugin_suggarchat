from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager
from ..utils.memory import get_memory_data


async def prompt(
    bot: Bot, event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """处理 prompt 命令的异步函数，根据用户输入管理 prompt 的设置和查询"""

    if not config_manager.config.function.allow_custom_prompt:
        await matcher.finish("当前不允许自定义 prompt。")

    # 获取当前事件的记忆数据
    data = await get_memory_data(event)
    arg = args.extract_plain_text().strip()

    # 检查输入长度是否过长，超过限制则提示用户
    if len(arg) >= 1000:
        await matcher.send("prompt 过长，预期的参数不超过 1000 字。")
        return

    # 检查输入是否为空，为空则提示用户如何使用命令
    if arg.strip() == "":
        await matcher.send(
            "请输入 prompt 或参数（--(show) 展示当前提示词，--(clear) 清空当前 prompt，--(set) [文字] 设置提示词，"
            "例如：/prompt --(show)，/prompt --(set) [text]）。"
        )
        return

    # 根据用户输入的命令执行相应操作
    if arg.startswith("--(show)"):
        await matcher.send(f"Prompt:\n{data.prompt}")
        return
    elif arg.startswith("--(clear)"):
        data.prompt = ""
        await matcher.send("prompt 已清空。")
    elif arg.startswith("--(set)"):
        arg = arg.replace("--(set)", "").strip()
        data.prompt = arg
        await matcher.send(f"prompt 已设置为：\n{arg}")
    else:
        await matcher.send(
            "请输入 prompt 或参数（--(show) 展示当前提示词，--(clear) 清空当前 prompt，--(set) [文字] 设置提示词，"
            "例如：/prompt --(show)，/prompt --(set) [text]）。"
        )
        return

    # 更新记忆数据
    await data.save(event)
