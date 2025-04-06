from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def presets(event: MessageEvent, matcher: Matcher):
    """处理模型预设查看的事件处理器"""
    # 检查功能是否已启用，未启用则跳过处理
    if not config_manager.config.enable:
        matcher.skip()

    # 检查用户是否为管理员，非管理员则发送消息并结束处理
    if event.user_id not in config_manager.config.admins:
        await matcher.finish("只有管理员才能查看模型预设。")

    # 构建消息字符串，包含当前模型预设信息
    msg = f"模型预设:\n当前：{'主配置文件' if config_manager.config.preset == '__main__' else config_manager.config.preset}\n主配置文件：{config_manager.config.model}"

    # 遍历模型列表，添加每个预设的名称和模型到消息字符串
    for i in config_manager.get_models():
        msg += f"\n预设名称：{i.name}，模型：{i.model}"

    # 发送消息给用户并结束处理
    await matcher.finish(msg)
