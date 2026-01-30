# mcp_client.py
import json
import random
from asyncio import Lock
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from copy import deepcopy
from typing import Any, overload

from fastmcp import Client
from fastmcp.client.client import CallToolResult
from fastmcp.client.transports import ClientTransportT
from mcp.types import TextContent
from nonebot import logger
from typing_extensions import Self
from zipp import Path

from .manager import ToolsManager
from .models import (
    FunctionDefinitionSchema,
    FunctionParametersSchema,
    MCPToolSchema,
    ToolData,
    ToolFunctionSchema,
    cast_mcp_properties_to_openai,
)

MCP_SERVER_SCRIPT_TYPE = ClientTransportT


class NOT_GIVEN:
    pass


class MCPClient:
    """可复用的MCP Client"""

    mcp_client: Client | None = None
    server_script: MCP_SERVER_SCRIPT_TYPE

    def __init__(
        self,
        server_script: MCP_SERVER_SCRIPT_TYPE,
        # headers: dict | None = None,
    ):
        self.mcp_client = None
        self.server_script: MCP_SERVER_SCRIPT_TYPE = server_script
        self.tools: list[MCPToolSchema] = []
        self.openai_tools: list[ToolFunctionSchema] = []

    async def __aenter__(self) -> Self:
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close()

    async def simple_call(self, tool_name: str, data: dict[str, Any]) -> str:
        """调用 MCP 工具
        Args:
            tool_name (str): 工具名称
            data (dict[str, Any]): 工具参数
        """

        try:
            if self.mcp_client is None:
                await self._connect()
            assert self.mcp_client is not None
            response: CallToolResult = await self.mcp_client.call_tool(tool_name, data)
            ct: list[TextContent] = [
                i for i in response.content if isinstance(i, TextContent)
            ]
            return "".join([f"{i.text}\n\n" for i in ct])
        except Exception as e:
            logger.opt(exception=e, colors=True).error(
                f"Failed to call tool:{tool_name}, because {e}."
            )
            return json.dumps({"success": False, "error": str(e)})
        finally:
            await self._close()

    async def _connect(self, update_tools: bool = False):
        """连接到 MCP Server
        Args:
            update_tools (bool, optional): 是否更新工具列表。 Defaults to False.
        """
        if self.mcp_client is not None:
            raise RuntimeError("MCP Server 已经连接了！")

        server_script = self.server_script
        self.mcp_client = Client(server_script)
        await self.mcp_client.__aenter__()
        logger.info(f"✅ 成功连接到 MCP Server@{server_script}")
        if not self.tools or update_tools:
            self.tools = [
                MCPToolSchema.model_validate(i.model_dump())
                for i in await self.mcp_client.list_tools()
            ]
            logger.info(f"🛠️  可用工具: {[tool.name for tool in self.tools]}")
            self._cast_tool_to_openai()

    def _format_tools_for_openai(self):
        """将 MCP 工具格式转换为 OpenAI 工具格式"""
        openai_tools: list[ToolFunctionSchema] = [
            ToolFunctionSchema(
                strict=True,
                type="function",
                function=FunctionDefinitionSchema(
                    name=tool.name,
                    description=tool.description or f"运行名为：{tool.name}的工具",
                    parameters=FunctionParametersSchema(
                        type="object",
                        required=tool.inputSchema.required,
                        properties=cast_mcp_properties_to_openai(
                            property=tool.inputSchema.properties
                        ),
                    ),
                ),
            )
            for tool in self.tools
        ]
        return openai_tools

    def _cast_tool_to_openai(self) -> None:
        self.openai_tools = self._format_tools_for_openai()

    def get_tools(self) -> list[ToolFunctionSchema]:
        """获取 MCP 工具列表"""
        return self.openai_tools

    def get_original_tools(self) -> list[MCPToolSchema]:
        """获取原始的 MCP 工具列表"""
        return self.tools

    async def _close(self):
        """关闭连接"""
        if self.mcp_client:
            await self.mcp_client.__aexit__(None, None, None)
            self.mcp_client = None


class ClientManager:
    clients: list[MCPClient]
    script_to_clients: dict[str, MCPClient]
    name_to_clients: dict[str, MCPClient]  # 根据FunctionName映射到MCPClient
    tools_remapping: dict[
        str, str
    ]  # 针对于SuggarChat重复工具的重映射(原始名称->重映射名称)
    reversed_remappings: dict[str, str]  # 逆向映射(重映射名称->原始名称)
    _instance = None
    _lock: Lock
    _is_initialized = False  # ToolsMapping是否已经就绪

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls.clients = []
            cls.name_to_clients = {}
            cls.tools_remapping = {}
            cls.reversed_remappings = {}
            cls.script_to_clients = {}
            cls._lock = Lock()
        return cls._instance

    def get_client_by_script(self, server_script: MCP_SERVER_SCRIPT_TYPE) -> MCPClient:
        """获取 MCP Client（不操作存储的MCP Server）
        Args:
            server_script (str, optional): MCP Server 脚本路径（或URI）。
        """
        return MCPClient(server_script)

    async def get_client_by_tool_name(self, tool_name: str) -> MCPClient:
        """根据工具名称获取 MCP Client
        Args:
            tool_name (str): 工具名称
        """
        async with self._lock:
            name = self.tools_remapping.get(tool_name) or tool_name
            if name in self.name_to_clients:
                return self.name_to_clients[name]
            raise RuntimeError(
                f"未找到工具：{tool_name}{f'（由`{name}`重映射）' if name != tool_name else ''}"
            )

    def _tools_wrapper(
        self, tool_name: str
    ) -> Callable[[dict[str, Any]], Awaitable[str]]:
        async def tools_runner(data: dict[str, Any]) -> str:
            client: MCPClient = await self.get_client_by_tool_name(tool_name)
            return await client.simple_call(tool_name, data)

        return tools_runner

    @overload
    def register_only(self, *, client: MCPClient) -> Self:
        """仅注册MCP Server，不进行初始化"""
        ...

    @overload
    def register_only(self, *, server_script: MCP_SERVER_SCRIPT_TYPE) -> Self:
        """仅注册MCP Server，不进行初始化"""
        ...

    def register_only(
        self,
        *,
        server_script: MCP_SERVER_SCRIPT_TYPE | None = None,
        client: MCPClient | None = None,
    ) -> Self:
        """仅注册MCP Server，不进行初始化"""
        if client is not None:
            self.clients.append(client)
        elif server_script is not None:
            client = MCPClient(server_script)
            self.clients.append(client)
        else:
            raise ValueError("请提供MCP Server脚本或MCP Client")
        return self

    @staticmethod
    async def update_tools(client: MCPClient):
        tools = client.get_tools()
        async with ClientManager._lock:
            for tool in tools:
                name = tool.function.name
                ToolsManager().remove_tool(name)
                ClientManager.name_to_clients.pop(name, None)
                if remap := ClientManager.tools_remapping.pop(name, None):
                    ClientManager.reversed_remappings.pop(remap, None)
        await ClientManager()._load_this(client)

    async def initialize_this(self, server_script: MCP_SERVER_SCRIPT_TYPE) -> Self:
        """注册并初始化单个MCP Server"""
        client: MCPClient = self.get_client_by_script(server_script)
        async with self._lock:
            try:
                await self._load_this(client)
            except Exception as e:
                logger.error(f"❌ 初始化 MCP Server@{server_script} 失败：{e}")
                raise
            else:
                self.clients.append(client)
        return self

    async def _load_this(self, client: MCPClient, fail_then_raise=True):
        try:
            tools_remapping_tmp = {}
            reversed_remappings_tmp = {}
            name_to_clients_tmp = {}
            async with client as c:
                tools = deepcopy(c.get_tools())
                for tool in tools:
                    if (
                        tool.function.name in self.tools_remapping
                        or tool.function.name in self.name_to_clients
                    ):
                        logger.warning(
                            f"{client}@{client.server_script} has a tool named {tool.function.name}, which is already registered, the old tool will be replaced."
                        )
                    name_to_clients_tmp[tool.function.name] = client
                    origin_name = tool.function.name
                    if ToolsManager().has_tool(tool.function.name):
                        remapped_name = (
                            f"referred_{random.randint(1, 100)}_{tool.function.name}"
                        )
                        logger.warning(
                            f"⚠️  工具已存在：{tool.function.name}，它将被重映射到：{remapped_name}"
                        )
                        tools_remapping_tmp[origin_name] = remapped_name
                        reversed_remappings_tmp[remapped_name] = origin_name
                        tool.function.name = remapped_name

                    ToolsManager().register_tool(
                        ToolData(
                            data=tool,
                            func=self._tools_wrapper(origin_name),
                            on_call="show",
                        )
                    )

        except Exception as e:
            if fail_then_raise:
                raise
            logger.opt(exception=e, colors=True).error(
                f"❌ 连接到 MCP Server@{client.server_script} 失败：{e}"
            )
        else:
            logger.info(f"✅ 加载到 MCP Server@{client.server_script} 成功")
            self.tools_remapping.update(tools_remapping_tmp)
            self.reversed_remappings.update(reversed_remappings_tmp)
            self.name_to_clients.update(name_to_clients_tmp)
            if isinstance(client.server_script, str | Path):
                server_script = str(client.server_script)
                self.script_to_clients[server_script] = client

    async def reinitalize_all(self):
        async with self._lock:
            for client in deepcopy(self.clients):
                await self.unregister_client(client.server_script, False)
                await self._load_this(client, fail_then_raise=False)

    async def initialize_all(self, lock: bool = True):
        """连接所有 MCP Server"""
        async with self._lock if lock else nullcontext():
            for client in self.clients:
                await self._load_this(client, False)
            self._is_initialized = True

    async def unregister_client(self, script_name: str | Path, lock: bool = True):
        """注销一个 MCP Server"""
        tools_manager = ToolsManager()
        async with self._lock if lock else nullcontext():
            script_name = str(script_name)
            if script_name in self.script_to_clients:
                client = self.script_to_clients.pop(script_name)
                for tool in client.openai_tools:
                    name = tool.function.name
                    tools_manager.remove_tool(name)
                    self.name_to_clients.pop(name, None)
                    if remap := self.tools_remapping.pop(name, None):
                        tools_manager.remove_tool(remap)
                        self.reversed_remappings.pop(remap, None)
                for idx, client in enumerate(self.clients):
                    if client.server_script == script_name:
                        self.clients.pop(idx)
                        break
