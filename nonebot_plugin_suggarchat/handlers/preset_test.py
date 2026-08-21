"""预设测试命令"""
from __future__ import annotations

import asyncio
import json

from aiologic import Lock
from amrita_core import PresetReport
from amrita_core.preset import MultiPresetManager
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager
from ..utils.send import send_forward_msg

TEST_LOCK = Lock()


async def _test_preset(
    event: MessageEvent, matcher: Matcher, bot: Bot, name: str, detailed: bool
) -> None:
    """测试指定模型（不指定则测试全部）"""
    pm = MultiPresetManager()
    if name:
        try:
            presets = [await config_manager.get_preset(name)]
        except Exception:
            await matcher.finish(f"未找到模型 {name}，请输入 /presets 查看可用模型。")
    else:
        presets = await config_manager.get_all_presets(True)
    if TEST_LOCK.locked():
        await matcher.finish("当前仍然有1个测试任务正在执行，请稍后再试。")
    async with TEST_LOCK:
        await matcher.send(f"开始测试（共计{len(presets)}个）...")
        results: list[PresetReport] = await asyncio.gather(
            *[pm.test_single_preset(preset) for preset in presets]
        )
    ok = len([r for r in results if r.status])
    if detailed:
        # summary 只出现一次，各预设仅展示自身细节
        summary = (
            f"测试结果：\n"
            f"测试完成，共测试{len(results)}个预设，成功{ok}个，失败{len(results) - ok}个。\n"
        )
        detail_msgs = [
            MessageSegment.text(
                f"预设：{result.preset_name}\n"
                f"测试输入：{json.dumps(result.test_input[0].model_dump(), ensure_ascii=False)} | "
                f"{json.dumps(result.test_input[1].model_dump(), ensure_ascii=False)}\n"
                f"测试输出：{json.dumps(result.test_output.model_dump(), ensure_ascii=False) if result.test_output else None}\n"
                f"输入token消耗：{result.token_prompt}\n"
                f"输出token消耗：{result.token_completion}\n"
                f"时间消耗：{result.time_used:.4f}s\n"
                f"测试成功：{result.status}\n"
            )
            for result in results
        ]
        await send_forward_msg(
            bot,
            event,
            "Amrita-测试结果",
            str(event.self_id),
            [MessageSegment.text(summary), *detail_msgs],
        )
    else:
        msg = (
            f"测试完成，共测试{len(results)}个预设，成功{ok}个，失败{len(results) - ok}个。\n"
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


async def t_preset(
    event: MessageEvent, matcher: Matcher, bot: Bot, args: Message = CommandArg()
):
    """测试预设命令入口：/test_preset [名称] [-d]"""
    arg_list = args.extract_plain_text().strip().split()
    name = (
        arg_list[0]
        if arg_list and arg_list[0] not in ("-d", "--detail", "--details")
        else ""
    )
    detailed = any(a in ("-d", "--detail", "--details") for a in arg_list)
    await _test_preset(event, matcher, bot, name, detailed)
