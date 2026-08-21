"""提示词模板选择命令"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager
from ..prompt_store import Prompt, Prompts


async def _display_current(matcher: Matcher) -> None:
    """显示当前群组和私聊的提示词设置"""
    await matcher.finish(
        f"当前群组的提示词预设：{config_manager.config.group_prompt_character}\n"
        f"当前私聊的提示词预设：{config_manager.config.private_prompt_character}"
    )


async def _list_prompts(
    matcher: Matcher, prompt_type: str, prompts: list[Prompt]
) -> None:
    """列出可用的提示词预设"""
    current = (
        config_manager.config.group_prompt_character
        if prompt_type == "group"
        else config_manager.config.private_prompt_character
    )
    msg = f"{'群组' if prompt_type == 'group' else '私聊'}可用模板：\n"
    for index, p in enumerate(prompts):
        marker = "⭐ " if p.name == current else "   "
        msg += f"{marker}{index + 1}). {p.name}\n"
    await matcher.finish(msg)


async def _set_prompt(
    matcher: Matcher, prompt_type: str, prompts: list[Prompt], name: str
) -> None:
    """设置群组或私聊的提示词模板"""
    for p in prompts:
        if p.name == name:
            if prompt_type == "group":
                config_manager.ins_config.group_prompt_character = p.name
            else:
                config_manager.ins_config.private_prompt_character = p.name
            config_manager.load_prompt()
            await config_manager.save_config()
            label = "群组" if prompt_type == "group" else "私聊"
            await matcher.finish(f"已设置{label}提示词为：{p.name}")
    label = "群组" if prompt_type == "group" else "私聊"
    await matcher.finish(f"未找到预设，请输入/choose_prompt {prompt_type}查看预设列表")


async def choose_prompt(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """切换提示词模板：/choose_prompt [group|private] [名称]"""
    prompts: Prompts = await config_manager.get_prompts()
    arg_list = args.extract_plain_text().strip().split()

    if not arg_list:
        await _display_current(matcher)
        return

    if arg_list[0] == "group":
        if len(arg_list) >= 2:
            await _set_prompt(matcher, "group", prompts.group, arg_list[1])
        else:
            await _list_prompts(matcher, "group", prompts.group)
    elif arg_list[0] == "private":
        if len(arg_list) >= 2:
            await _set_prompt(matcher, "private", prompts.private, arg_list[1])
        else:
            await _list_prompts(matcher, "private", prompts.private)
    else:
        await matcher.finish("用法：/choose_prompt [group|private] [名称]")
