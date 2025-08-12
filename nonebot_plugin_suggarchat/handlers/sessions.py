import time
from copy import deepcopy
from datetime import datetime

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.exception import NoneBotException
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..check_rule import is_group_admin_if_is_in_group
from ..config import config_manager
from ..utils.memory import Memory, MemoryModel, get_memory_data


async def sessions(
    bot: Bot, event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """会话管理命令处理入口"""
    if not await is_group_admin_if_is_in_group(event, bot):
        await matcher.finish("你没有权限执行此命令。")

    async def display_sessions(data: MemoryModel) -> None:
        """显示历史会话列表"""
        if not data.sessions:
            await matcher.finish("没有历史会话")
        message_content = "历史会话\n"
        for index, msg in enumerate(data.sessions):
            if msg.messages:
                message_content += f"编号：{index}) ：{msg.messages[0].content[63:68]}... 时间：{datetime.fromtimestamp(msg.time).strftime('%Y-%m-%d %I:%M:%S %p')}\n"
        await matcher.finish(message_content)

    async def set_session(
        data: MemoryModel, arg_list: list[str], event: MessageEvent
    ) -> None:
        """将当前会话覆盖为指定编号的会话"""
        try:
            if len(arg_list) >= 2:
                data.memory.messages = deepcopy(
                    data.sessions[int(arg_list[1])].messages
                )
                data.timestamp = time.time()
                await data.save(event)
                await matcher.send("完成记忆覆盖。")
            else:
                await matcher.finish("请输入正确编号")
        except NoneBotException as e:
            raise e
        except Exception:
            await matcher.finish("覆盖记忆文件失败，这个对话可能损坏了。")

    async def delete_session(
        data: MemoryModel, arg_list: list[str], event: MessageEvent
    ) -> None:
        """删除指定编号的会话"""
        try:
            if len(arg_list) >= 2:
                data.sessions.remove(data.sessions[int(arg_list[1])])
                await data.save(event)
            else:
                await matcher.finish("请输入正确编号")
        except NoneBotException as e:
            raise e
        except Exception:
            await matcher.finish("删除指定编号会话失败。")

    async def archive_session(data: MemoryModel, event: MessageEvent) -> None:
        """归档当前会话"""
        try:
            if data.memory.messages:
                data.sessions.append(
                    Memory(messages=data.memory.messages, time=time.time())
                )
                data.memory.messages = []
                data.timestamp = time.time()
                await data.save(event)
                await matcher.finish("当前会话已归档。")
            else:
                await matcher.finish("当前对话为空！")
        except NoneBotException as e:
            raise e
        except Exception:
            await matcher.finish("归档当前会话失败。")

    async def clear_sessions(data: MemoryModel, event: MessageEvent) -> None:
        """清空所有会话"""
        try:
            data.sessions = []
            data.timestamp = time.time()
            await data.save(event)
            await matcher.finish("会话已清空。")
        except NoneBotException as e:
            raise e
        except Exception:
            await matcher.finish("清空当前会话失败。")

    # 检查是否启用了会话管理功能
    if not config_manager.config.session.session_control:
        matcher.skip()

    # 获取当前用户的会话数据
    data = await get_memory_data(event)

    # 解析用户输入的命令参数
    arg_list = args.extract_plain_text().strip().split()

    # 如果没有参数，显示历史会话
    if not arg_list:
        await display_sessions(data)

    # 根据命令执行对应操作
    match arg_list[0]:
        case "set":
            await set_session(data, arg_list, event)
        case "del":
            await delete_session(data, arg_list, event)
        case "archive":
            await archive_session(data, event)
        case "clear":
            await clear_sessions(data, event)
        case "help":
            await matcher.finish(
                "Sessions指令帮助：\nset：覆盖当前会话为指定编号的会话\ndel：删除指定编号的会话\narchive：归档当前会话\nclear：清空所有会话\n"
            )
        case _:
            await matcher.finish("未知命令，请输入/help查看帮助。")
