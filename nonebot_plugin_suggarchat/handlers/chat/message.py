"""消息合成与格式化（从原 chat.py 抽出）。

职责：
- 用户输入转义 / legacy / XML 两种消息格式渲染
- 引用消息（Reply）展开为可读上下文
- 引用图片提取
- 用户角色获取
- 将事件消息合成为 ChatObject 输入（含多模态判定）
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from amrita_core import TextContent, debug_log
from amrita_core.types import Content, ImageContent, ImageUrl
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.event import MessageEvent, Reply

from ...config import config_manager
from ...utils.functions import synthesize_message
from ...utils.preset import resolve_preset


def escape_content(raw: str) -> str:
    """
    转义用户输入中可能与 legacy 消息格式冲突的字符。

    legacy 格式使用 [...] 标记用户身份、说: 标记发言，
    用户输入中出现相同字符时全角替换以避免 LLM 误解析。
    """
    return raw.replace("[", "\uff3b").replace("]", "\uff3d").replace("说:", "说：")


def escape_xml(raw: str) -> str:
    """
    转义用户输入中可能与 XML 消息格式冲突的字符。

    < > & 替换为 XML 实体，防止 injection。
    """
    return raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_msg_legacy(role: str, name: str, uid: str, content: str) -> str:
    """legacy 格式：方括号标记，紧凑风格"""
    safe_content = escape_content(content)
    safe_name = escape_content(name)
    if role:
        return f"[{role}][{safe_name}（{uid}）]说:{safe_content}"
    return f"[{safe_name}（{uid}）]说:{safe_content}"


def format_msg_xml(role: str, name: str, uid: str, content: str) -> str:
    """XML 格式：标签标记，结构清晰，天然支持多行"""
    safe_content = escape_xml(content)
    safe_name = escape_xml(name)
    attrs = f' role="{role}"' if role else ""
    return f'<msg{attrs} name="{safe_name}" uid="{uid}">\n{safe_content}\n</msg>'


async def handle_reply(
    reply: Reply, bot: Bot, group_id: int | None, content: str
) -> str:
    """处理引用消息：
    - 提取引用消息的内容和时间信息。
    - 格式化为可读的引用内容。

    Args:
        reply: 回复消息
        bot: Bot实例
        group_id: 群组ID（私聊为None）
        content: 原始内容

    Returns:
        格式化后的内容
    """
    if not reply.sender.user_id:
        return content
    dt_object = datetime.fromtimestamp(reply.time)
    weekday = dt_object.strftime("%A")
    formatted_time = dt_object.strftime("%Y-%m-%d %I:%M:%S %p")
    role = (
        f"{await get_user_role(bot, group_id, reply.sender.user_id)}"
        if group_id
        else ""
    )

    reply_content = await synthesize_message(reply.message, bot)
    safe_name = reply.sender.nickname or ""
    msg_type = config_manager.config.function.message_type

    if msg_type == "xml":
        safe_content = escape_xml(reply_content)
        safe_name = escape_xml(safe_name)
        # 用户消息内容也需要转义，因为 downstream format_msg_xml
        # 在检测到已有 <ref> 后会跳过二次转义
        safe_user_content = escape_xml(content)
        result = (
            f"{safe_user_content}\n"
            f'<ref name="{safe_name}" uid="{reply.sender.user_id}">\n'
            f"  <time>{formatted_time} {weekday}</time>\n"
            f"  <content>{safe_content}</content>\n"
            f"</ref>"
        )
    else:
        safe_content = escape_content(reply_content)
        safe_name = escape_content(safe_name)
        result = f"{content}\n<MESSAGE_REFERED>\n{formatted_time} {weekday} {role}{safe_name}（QQ:{reply.sender.user_id}）说：{safe_content}\n</MESSAGE_REFERED>"
    debug_log(f"处理引用消息完成: {result[:50]}..")
    return result


def get_reply_pics(event: MessageEvent) -> list[ImageContent]:
    """获取引用消息中的图片内容

    Returns:
        图片内容列表
    """
    if reply := event.reply:
        msg = reply.message
        images = [
            ImageContent(image_url=ImageUrl(url=url))
            for seg in msg
            if seg.type == "image" and (url := seg.data.get("url")) is not None
        ]
        debug_log(f"获取引用图片完成，共 {len(images)} 张")
        return images
    return []


async def get_user_role(bot: Bot, group_id: int, user_id: int) -> str:
    """获取用户在群聊中的身份（群主、管理员或普通成员）。

    Args:
        group_id: 群组ID
        user_id: 用户ID

    Returns:
        用户角色字符串
    """
    role_data = await bot.get_group_member_info(group_id=group_id, user_id=user_id)
    role = role_data["role"]
    role_str = {"admin": "群管理员", "owner": "群主", "member": "普通成员"}.get(
        role, "[获取身份失败]"
    )
    debug_log(f"获取用户角色完成: {role_str}")
    return role_str


async def synthesize_message_to_msg(
    event: MessageEvent,
    role: str,
    user_name: str,
    user_id: str,
    content: str,
) -> Sequence[Content] | str:
    """将消息转换为Message

    根据配置和多模态支持情况，将事件消息转换为适当的格式，
    支持文本和图片内容的组合。

    Args:
        event: 消息事件
        role: 用户角色
        date: 时间戳
        user_name: 用户名
        user_id: 用户ID
        content: 消息内容

    Returns:
        转换后的消息内容
    """
    presets = [
        await resolve_preset(preset)
        for preset in [
            config_manager.config.preset,
            *config_manager.config.preset_extension.backup_preset_list,
        ]
    ]
    is_multimodal: bool = any(p.config.multimodal for p in presets)

    if config_manager.config.parse_segments:
        if config_manager.config.function.message_type == "xml":
            # handle_reply 在 XML 模式下已对 content 做了 escape_xml，
            # 且 content 中可能包含 <ref> 标签（已转义好的引用内容），
            # 因此不能再次经过 format_msg_xml -> escape_xml 导致双重转义
            if "\n<ref" in content:
                safe_name = escape_xml(str(user_name))
                attrs = f' role="{role}"' if role else ""
                body = f'<msg{attrs} name="{safe_name}" uid="{user_id}">\n{content}\n</msg>'
            else:
                body = format_msg_xml(role, str(user_name), str(user_id), content)
        else:
            body = format_msg_legacy(role, str(user_name), str(user_id), content)
        text: Sequence[Content] | str = (
            [TextContent(text=body)]
            + [
                ImageContent(image_url=ImageUrl(url=seg.data["url"]))
                for seg in event.message
                if seg.type == "image" and seg.data.get("url")
            ]
            if is_multimodal
            else body
        )
    else:
        text = event.message.extract_plain_text()
    return text
