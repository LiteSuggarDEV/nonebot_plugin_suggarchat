from nonebot.adapters import Message
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import ConfigManager


async def set_preset(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """处理设置预设的事件"""

    # 检查插件是否启用
    if not ConfigManager().ins_config.enable:
        matcher.skip()

    # 获取命令参数并去除多余空格
    arg = args.extract_plain_text().strip()

    # 如果参数不为空
    if arg != "":
        # 遍历所有模型
        for model in await ConfigManager().get_all_presets():
            if model.name == arg:
                # 设置预设并保存
                ConfigManager().ins_config.preset = model.name
                await ConfigManager().save_config()
                # 回复设置成功
                await matcher.finish(f"已设置预设为：{model.name}，模型：{model.model}")
        # 未找到匹配的预设
        await matcher.finish("未找到预设，请输入/presets查看预设列表。")
    else:
        # 参数为空时重置为默认预设
        ConfigManager().ins_config.preset = "default"
        await ConfigManager().save_config()
        # 回复重置成功
        await matcher.finish(
            f"已重置预设为：默认预设，模型：{(await ConfigManager().get_preset(ConfigManager().ins_config.preset)).model}。"
        )
