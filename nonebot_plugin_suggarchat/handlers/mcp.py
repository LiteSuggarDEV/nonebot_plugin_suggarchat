from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from nonebot_plugin_suggarchat.builtin_hook import ChatException
from nonebot_plugin_suggarchat.config import ConfigManager

from ..send import send_forward_msg
from ..utils.llm_tools.mcp_client import ClientManager


async def mcp_command(
    bot: Bot, matcher: Matcher, event: MessageEvent, arg: Message = CommandArg()
):
    arg_list = arg.extract_plain_text().strip().split(maxsplit=1)
    match len(arg_list):
        case 0:
            await matcher.finish(
                "❌ 缺少参数！\n可用：stats [-d|--details];add <server_script>;del <server_script>;reload"
            )
        case 1 | 2:
            if arg_list[0] == "stats":
                return await mcp_status(bot, matcher, event, arg_list[1:])
            elif arg_list[0] == "reload":
                return await reload(matcher)
            elif len(arg_list) == 2:
                if arg_list[0] in ("add", "添加"):
                    return await add_mcp_server(matcher, bot, event, arg_list[1])
                elif arg_list[0] in ("del", "删除"):
                    return await del_mcp_server(matcher, arg_list[1])

    await matcher.finish("参数数量或类型错误，请检查命令格式。")


async def mcp_status(bot: Bot, matcher: Matcher, event: MessageEvent, arg: list[str]):
    arg_text = arg[0] if arg else ""
    tools_count = len(ClientManager().name_to_clients)
    mcp_server_counts = len(ClientManager().clients)
    tools_mapping_count = len(ClientManager().tools_remapping)
    std_txt = f"MCP状态统计\nMCP Servers: {mcp_server_counts}\nMCP Tools: {tools_count}\nMCP Tools(Mapped): {tools_mapping_count}"
    if arg_text in ("-d", "--detail", "--details"):
        if not isinstance(event, PrivateMessageEvent):
            await matcher.finish("-d只允许在私聊执行来避免安全问题")
        detailed_info = [
            MessageSegment.text(std_txt),
            *[
                MessageSegment.text(
                    f"Server@{client.server_script!s} Tools: \n".join(
                        [
                            f" - {tool.function.name}:{tool.function.description}\n"
                            for tool in client.openai_tools
                        ]
                    )
                )
                for client in ClientManager().clients
            ],
        ]

        await send_forward_msg(
            bot, event, "Amrita-MCP", str(event.self_id), detailed_info
        )
    else:
        await matcher.finish(std_txt)


async def add_mcp_server(
    matcher: Matcher, bot: Bot, event: MessageEvent, mcp_server: str
):
    if not ConfigManager().config.llm_config.tools.agent_mcp_client_enable:
        return
    config = ConfigManager().ins_config
    if not mcp_server:
        await matcher.finish("请输入MCP Server脚本路径")
    if mcp_server in config.llm_config.tools.agent_mcp_server_scripts:
        await matcher.finish("MCP Server脚本已存在")
    try:
        await ClientManager().initialize_this(mcp_server)
        config.llm_config.tools.agent_mcp_server_scripts.append(mcp_server)
        await ConfigManager().save_config()
        await matcher.send("添加成功")
    except Exception as e:
        if isinstance(e, ChatException):
            raise
        await matcher.send(f"添加失败: {e}")
        logger.opt(exception=e, colors=True).exception(e)


async def del_mcp_server(matcher: Matcher, mcp_server: str):
    if not ConfigManager().config.llm_config.tools.agent_mcp_client_enable:
        return
    config = ConfigManager().ins_config
    if not mcp_server:
        await matcher.finish("请输入要删除的MCP Server")
    if mcp_server not in config.llm_config.tools.agent_mcp_server_scripts:
        await matcher.finish("MCP Server不存在")
    try:
        await ClientManager().unregister_client(mcp_server)
        config.llm_config.tools.agent_mcp_server_scripts.remove(mcp_server)
        await ConfigManager().save_config()
        await matcher.send("删除成功")
    except Exception as e:
        logger.opt(exception=e, colors=True).exception(e)
        await matcher.finish("删除失败")


async def reload(matcher: Matcher):
    if not ConfigManager().config.llm_config.tools.agent_mcp_client_enable:
        return
    try:
        await ClientManager().reinitalize_all()
        await matcher.send("重载成功")
    except Exception as e:
        logger.opt(exception=e, colors=True).exception(e)
        await matcher.send("重载失败")
