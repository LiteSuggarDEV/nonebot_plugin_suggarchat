import typing

from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment


async def send_forward_msg(
    bot: Bot, event: Event, name: str, uin: str, msgs: typing.Iterable[MessageSegment]
):
    def to_json(msg: MessageSegment) -> dict:
        return {"type": "node", "data": {"name": name, "uin": uin, "content": msg}}

    messages = [to_json(msg) for msg in msgs]
    if (gid := getattr(event, "group_id", None)) is not None:
        await bot.send_group_forward_msg(group_id=gid, messages=messages)
    else:
        await bot.send_private_forward_msg(
            user_id=int(event.get_user_id()), messages=messages
        )
