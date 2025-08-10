from typing import Any

from nonebot.adapters import Message
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager


async def choose_prompt(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """处理选择提示词命令"""

    async def display_current_prompts() -> None:
        """显示当前群组和私聊的提示词设置"""
        msg = (
            f"当前群组的提示词预设：{config_manager.config.group_prompt_character}\n"
            f"当前私聊的提示词预设：{config_manager.config.private_prompt_character}"
        )
        await matcher.finish(msg)

    async def handle_group_prompt(arg_list: list[str]) -> None:
        """处理群组提示词设置"""
        if len(arg_list) >= 2:
            for i in (await config_manager.get_prompts()).group:
                if i.name == arg_list[1]:
                    config_manager.ins_config.group_prompt_character = i.name
                    await config_manager.load_prompt()
                    await config_manager.save_config()
                    await matcher.finish(f"已设置群组提示词为：{i.name}")
            await matcher.finish("未找到预设，请输入/choose_prompt group查看预设列表")
        else:
            await list_available_prompts(
                (await config_manager.get_prompts()).group, "group"
            )

    async def handle_private_prompt(arg_list: list[str]) -> None:
        """处理私聊提示词设置"""
        if len(arg_list) >= 2:
            for i in (await config_manager.get_prompts()).private:
                if i.name == arg_list[1]:
                    config_manager.ins_config.private_prompt_character = i.name
                    await config_manager.load_prompt()
                    await config_manager.save_config()
                    await matcher.finish(f"已设置私聊提示词为：{i.name}")
            await matcher.finish("未找到预设，请输入/choose_prompt private查看预设列表")
        else:
            await list_available_prompts(
                (await config_manager.get_prompts()).private, "private"
            )

    async def list_available_prompts(prompts: list[Any], prompt_type: str) -> None:
        """列出可用的提示词预设"""
        msg = "可选的预设名称：\n"
        for index, i in enumerate(prompts):
            # 标记当前使用的提示词
            current_marker = (
                " (当前）>"
                if (
                    prompt_type == "group"
                    and i.name == config_manager.config.group_prompt_character
                )
                or (
                    prompt_type == "private"
                    and i.name == config_manager.config.private_prompt_character
                )
                else ""
            )
            msg += f"{current_marker}{index + 1}). {i.name}\n"
        await matcher.finish(msg)

    # 解析命令参数
    arg_list = args.extract_plain_text().strip().split()

    if not arg_list:
        # 如果没有参数，显示当前提示词设置
        await display_current_prompts()
        return

    # 根据参数处理群组或私聊提示词
    if arg_list[0] == "group":
        await handle_group_prompt(arg_list)
    elif arg_list[0] == "private":
        await handle_private_prompt(arg_list)
