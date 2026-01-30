import asyncio
import json
from asyncio import Lock

from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..check_rule import is_bot_admin
from ..config import ConfigManager
from ..send import send_forward_msg
from ..utils.libchat import PresetReport, test_presets

TEST_LOCK = Lock()


async def t_preset(
    event: MessageEvent, matcher: Matcher, bot: Bot, args: Message = CommandArg()
):
    if not await is_bot_admin(event):
        await matcher.finish("仅允许Bot管理员使用此命令。")
    if TEST_LOCK.locked():
        await matcher.finish("当前仍然有1个测试任务正在执行，请稍后再试。")
    async with TEST_LOCK:
        presets = await ConfigManager().get_all_presets(True)
        await matcher.send(
            MessageSegment.text(f"开始测试所有(共计{len(presets)}个)预设...")
        )
        results: list[PresetReport] = []
        arg_list = args.extract_plain_text().strip().split()
        async for result in test_presets():
            results.append(result)
            await asyncio.sleep(0)
        if "--detail" in arg_list or "-d" in arg_list:
            msg = [
                MessageSegment.text(
                    f"测试结果：\n"
                    f"测试完成，共测试{len(results)}个预设，成功{len([result for result in results if result.status])}个，失败{len([result for result in results if not result.status])}个。"
                )
            ] + [
                MessageSegment.text(
                    f"预设：{result.preset_name}\n"
                    f"测试输入：{json.dumps(result.test_input[0].model_dump(), ensure_ascii=False), json.dumps(result.test_input[1].model_dump(), ensure_ascii=False)}\n"
                    f"测试输出：{json.dumps(result.test_output.model_dump(), ensure_ascii=False) if result.test_output else None}\n"
                    f"输入token消耗：{result.token_prompt}\n"
                    f"输出token消耗：{result.token_completion}\n"
                    f"时间消耗：{result.time_used:.4f}s\n"
                    f"测试成功：{result.status}\n"
                )
                for result in results
            ]
            await send_forward_msg(
                bot, event, "Amrita-测试结果", str(event.self_id), msg
            )
        else:
            msg = MessageSegment.text(
                f"测试完成，共测试{len(results)}个预设，成功{len([result for result in results if result.status])}个，失败{len([result for result in results if not result.status])}个。\n"
                + "".join(
                    [
                        (
                            f"预设：{result.preset_name}"
                            f"  时间消耗：{result.time_used:.4f}s"
                            f"  测试成功：{result.status}"
                        )
                        for result in results
                    ]
                )
            )
            await matcher.send(msg)
