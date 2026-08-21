"""/prompt 命令：自定义提示词与模板切换"""

from __future__ import annotations

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_amrita import CachedUserDataRepository

from ..config import config_manager
from ..utils.sql import get_uni_user_id


async def _show_extra(event: MessageEvent, matcher: Matcher) -> None:
    """展示当前自定义提示词"""
    data = await CachedUserDataRepository().get_memory(get_uni_user_id(event))
    await matcher.send(f"当前自定义提示词：\n{data.extra_prompt or '（无）'}")


async def _set_extra(event: MessageEvent, matcher: Matcher, text: str) -> None:
    """设置自定义提示词"""
    if len(text) >= 1000:
        await matcher.finish("prompt 过长，预期的参数不超过 1000 字。")
    data = await CachedUserDataRepository().get_memory(get_uni_user_id(event))
    data.extra_prompt = text
    await CachedUserDataRepository().update_memory_data(data)
    await matcher.send(f"✅ prompt 已设置为：\n{text}")


async def _clear_extra(event: MessageEvent, matcher: Matcher) -> None:
    """清空自定义提示词"""
    data = await CachedUserDataRepository().get_memory(get_uni_user_id(event))
    data.extra_prompt = ""
    await CachedUserDataRepository().update_memory_data(data)
    await matcher.send("✅ prompt 已清空。")


async def _show_template(matcher: Matcher) -> None:
    """展示当前提示词模板"""
    await matcher.send(
        f"群组模板：{config_manager.config.group_prompt_character}\n"
        f"私聊模板：{config_manager.config.private_prompt_character}"
    )


async def _template_list(matcher: Matcher, prompt_type: str) -> None:
    """列出群组或私聊的可用模板"""
    prompts = (
        (await config_manager.get_prompts()).group
        if prompt_type == "group"
        else (await config_manager.get_prompts()).private
    )
    current = (
        config_manager.config.group_prompt_character
        if prompt_type == "group"
        else config_manager.config.private_prompt_character
    )
    msg = f"{'群组' if prompt_type == 'group' else '私聊'}可用模板：\n"
    for i, p in enumerate(prompts):
        msg += f"{'⭐ ' if p.name == current else '   '}{i + 1}). {p.name}\n"
    await matcher.finish(msg)


async def _template_set(matcher: Matcher, prompt_type: str, name: str) -> None:
    """切换群组或私聊的提示词模板"""
    if not name:
        await matcher.finish("请指定模板名，如：/prompt template group default")
    prompts = (
        (await config_manager.get_prompts()).group
        if prompt_type == "group"
        else (await config_manager.get_prompts()).private
    )
    for p in prompts:
        if p.name == name:
            if prompt_type == "group":
                config_manager.ins_config.group_prompt_character = p.name
            else:
                config_manager.ins_config.private_prompt_character = p.name
            config_manager.load_prompt()
            await config_manager.save_config()
            await matcher.finish(
                f"✅ 已设置{'群组' if prompt_type == 'group' else '私聊'}模板为：{p.name}"
            )
    await matcher.finish(
        f"未找到模板 {name}，请输入 /prompt template {prompt_type} 查看。"
    )


async def prompt(
    bot: Bot, event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """/prompt 命令入口：set/clear/show/template"""
    if not config_manager.config.function.allow_custom_prompt:
        await matcher.finish("当前不允许自定义 prompt。")

    arg_list = args.extract_plain_text().strip().split()
    if not arg_list:
        await _show_extra(event, matcher)
        return

    match arg_list[0]:
        case "set" | "设置":
            text = args.extract_plain_text().strip()[len(arg_list[0]) :].strip()
            await _set_extra(event, matcher, text)
        case "clear" | "清空" | "reset":
            await _clear_extra(event, matcher)
        case "show" | "查看":
            await _show_extra(event, matcher)
        case "template" | "模板" | "tpl":
            if len(arg_list) < 2:
                await _show_template(matcher)
                return
            tpl_type = arg_list[1]
            if tpl_type in ("group", "群组", "g"):
                if len(arg_list) >= 3:
                    await _template_set(matcher, "group", arg_list[2])
                else:
                    await _template_list(matcher, "group")
            elif tpl_type in ("private", "私聊", "p"):
                if len(arg_list) >= 3:
                    await _template_set(matcher, "private", arg_list[2])
                else:
                    await _template_list(matcher, "private")
            else:
                await matcher.finish("模板类型必须是 group 或 private。")
        case _:
            await matcher.finish(
                "用法：\n"
                "/prompt — 查看当前自定义提示词\n"
                "/prompt set <文本> — 设置\n"
                "/prompt clear — 清空\n"
                "/prompt template [group|private] [名称] — 模板切换"
            )
