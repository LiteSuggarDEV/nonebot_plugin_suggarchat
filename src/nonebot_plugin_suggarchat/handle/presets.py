from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.matcher import Matcher

from ..config import config_manager


async def presets(event: MessageEvent, matcher: Matcher):
    """处理查看模型预设的事件"""

    # 检查用户是否为管理员，非管理员则提示并结束
    if event.user_id not in config_manager.config.admins:
        await matcher.finish("只有管理员才能查看模型预设。")

    # 构建包含当前模型预设信息的消息
    msg = f"模型预设:\n当前：主配置文件：{config_manager.config.preset}"

    # 遍历模型列表，添加每个预设的名称和模型信息
    for i in config_manager.get_models():
        msg += f"\n预设名称：{i.name}，模型：{i.model}"

    # 发送消息并结束处理
    await matcher.finish(msg)
