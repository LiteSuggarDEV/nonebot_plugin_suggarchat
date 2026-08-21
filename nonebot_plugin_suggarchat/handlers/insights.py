import re
from collections.abc import Sequence

from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot_plugin_amrita import CachedUserDataRepository
from nonebot_plugin_amrita.database import InsightsModel, UserDataExecutor, UserMetadata

from ..check_rule import is_bot_admin
from ..config import config_manager
from ..utils.sql import get_uni_user_id, get_user_metadata_or_none

_TOP_RE = re.compile(r"^top(\d+)$", re.IGNORECASE)
_TOP_MAX = 50  # 排名数量上限，防止刷屏


def _format_user_entry(i: int, user: UserMetadata, label: str) -> str:
    """格式化排名条目"""
    user_id = user.user_id.split("_", 1)[1] if "_" in user.user_id else user.user_id
    total_tokens = user.tokens_input + user.tokens_output
    return f"{i}. {label}{user_id}: {user.called_count}次, {total_tokens}tokens\n"


def _parse_inspect(arg: str) -> tuple[str, str] | None:
    """解析 /insights inspect [group|user] <id>，非法输入返回 None"""
    parts = arg.split()
    if len(parts) == 2:
        kind, target = "user", parts[1]
    elif len(parts) == 3 and parts[1] in ("group", "user"):
        kind, target = parts[1], parts[2]
    else:
        return None
    if not target.isdigit():
        return None
    return kind, target


async def insights(event: MessageEvent, matcher: Matcher, args: Message = CommandArg()):
    msg = "未知参数。"
    config = config_manager.config
    if not (arg := args.extract_plain_text().strip()):
        data = await CachedUserDataRepository().get_metadata(f"user_{event.user_id}")
        user_limit = config.usage_limit.user_daily_limit
        user_token_limit = config.usage_limit.user_daily_token_limit
        group_limit = config.usage_limit.group_daily_limit
        group_token_limit = config.usage_limit.group_daily_token_limit
        enable_limit = config.usage_limit.enable_usage_limit
        is_bypass = await is_bot_admin(event)

        msg = (
            f"您今日的使用次数为：{data.called_count}/{user_limit if (user_limit != -1 and enable_limit and not is_bypass) else '♾'}次"
            + f"\n您今日的token使用量为：{data.tokens_input + data.tokens_output}/{user_token_limit if (user_token_limit != -1 and enable_limit and not is_bypass) else '♾'}tokens"
            + f"\n（输入：{data.tokens_input},输出：{data.tokens_output}）"
        )
        if isinstance(event, GroupMessageEvent):
            data = await CachedUserDataRepository().get_metadata(get_uni_user_id(event))
            msg = (
                f"群组使用次数为：{data.called_count}/{group_limit if (group_limit != -1 and enable_limit) else '♾'}次"
                + f"\n群组使用token为：{data.tokens_input + data.tokens_output}/{group_token_limit if (group_token_limit != -1 and enable_limit) else '♾'}tokens"
                + f"\n（输入：{data.tokens_input},输出：{data.tokens_output}）"
                + f"\n\n{msg}"
            )
    elif arg == "global":
        total_token_limit = config.usage_limit.total_daily_token_limit
        total_limit = config.usage_limit.total_daily_limit
        if not await is_bot_admin(event):
            await matcher.finish("你没有权限查看全局数据")
        data = await InsightsModel.get()
        msg = (
            f"\n今日全局数据：\n输入token使用量：{data.token_input}"
            + f"\n输出token使用量：{data.token_output}token"
            + f"\n总使用次数：{data.usage_count}/{total_limit}"
            + f"\n总使用token为：{data.token_input + data.token_output}/{total_token_limit}tokens"
            + "\n(您的限制：♾)"
        )
    elif arg.startswith("inspect"):
        if not await is_bot_admin(event):
            await matcher.finish("你没有权限查看其他用户/群组数据")
        parsed = _parse_inspect(arg)
        if parsed is None:
            msg = "用法：/insights inspect [group|user] <id>"
        else:
            kind, target = parsed
            uni_id = f"{kind}_{target}"
            data = await get_user_metadata_or_none(uni_id)
            if data is None:
                msg = f"未找到{kind} {target} 的使用数据。"
            else:
                label = "群组" if kind == "group" else "用户"
                total_tokens = data.tokens_input + data.tokens_output
                total_history = data.total_input_token + data.total_output_token
                msg = (
                    f"\n📊 {label} {target} 使用情况："
                    f"\n今日调用次数：{data.called_count}次"
                    f"\n今日token：{data.tokens_input}输入 / {data.tokens_output}输出（共{total_tokens}）"
                    f"\n历史累计：{data.total_called_count}次，{total_history} tokens"
                )
    elif match := _TOP_RE.match(arg):
        if not await is_bot_admin(event):
            await matcher.finish("你没有权限查看排名数据")

        # 获取 topN 数据（群/私聊各取前 N，最多 2N 条）
        n = min(int(match.group(1)), _TOP_MAX)
        top_users: Sequence[UserMetadata] = await UserDataExecutor.get_top_users(
            limit=n * 2
        )

        if not top_users:
            msg = "暂无使用数据。"
        else:
            # 按 group/private 分类
            group_users: Sequence[UserMetadata] = [
                u for u in top_users if u.user_id.startswith("group_")
            ]
            private_users: Sequence[UserMetadata] = [
                u for u in top_users if not u.user_id.startswith("group_")
            ]

            msg = f"今日使用量Top{n}：\n"

            if group_users:
                msg += "\n📢 群组排名：\n"
                for i, user in enumerate(group_users[:n], 1):
                    msg += _format_user_entry(i, user, "群")

            if private_users:
                msg += "\n💬 私聊排名：\n"
                for i, user in enumerate(private_users[:n], 1):
                    msg += _format_user_entry(i, user, "用户")

    if isinstance(event, GroupMessageEvent):
        content = MessageSegment.at(event.user_id) + MessageSegment.text(f"\n{msg}")
    else:
        # 私聊不支持 at 段（协议约束），仅发送文本
        content = MessageSegment.text(f"\n{msg}")
    await matcher.finish(content)
