from nonebot.adapters import Message
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from ..config import config_manager


async def set_preset(
    event: MessageEvent, matcher: Matcher, args: Message = CommandArg()
):
    """处理设置预设的事件"""

    # 检查插件是否启用
    if not config_manager.config.enable:
        matcher.skip()

    # 检查用户是否为管理员
    if event.user_id not in config_manager.config.admins:
        await matcher.finish("只有管理员才能设置预设。")

    # 获取命令参数并去除多余空格
    arg = args.extract_plain_text().strip()

    # 如果参数不为空
    if arg != "":
        # 遍历所有模型
        for i in config_manager.get_models():
            if i.name == arg:
                # 设置预设并保存
                config_manager.config.preset = i.name
                config_manager.save_config()
                # 回复设置成功
                await matcher.finish(f"已设置预设为：{i.name}，模型：{i.model}")
        # 未找到匹配的预设
        await matcher.finish("未找到预设，请输入/presets查看预设列表。")
    else:
        # 参数为空时重置为默认预设
        config_manager.config.preset = "__main__"
        config_manager.save_config()
        # 回复重置成功
        await matcher.finish(
            f"已重置预设为：主配置文件，模型：{config_manager.config.model}"
        )
