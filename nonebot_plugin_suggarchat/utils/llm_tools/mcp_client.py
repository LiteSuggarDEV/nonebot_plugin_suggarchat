# mcp_client.py
import random
from asyncio import Lock
from copy import deepcopy
from typing import Any, overload

from fastmcp import Client
from fastmcp.client.transports import ClientTransportT
from nonebot import logger
from typing_extensions import Self
from zipp import Path

from .manager import ToolsManager
from .models import (
    FunctionDefinitionSchema,
    FunctionParametersSchema,
    ToolData,
    ToolFunctionSchema,
)

MCP_SERVER_SCRIPT_TYPE = ClientTransportT


class NOT_GIVEN:
    pass


class MCPClient:
    """可复用的MCP Client"""

    def __init__(
        self,
        server_script: MCP_SERVER_SCRIPT_TYPE,
        # headers: dict | None = None,
    ):
        self.mcp_client = None
        self.server_script = server_script
        self.tools = []
        self.openai_tools = []

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close()

    async def simple_call(self, tool_name: str, data: dict[str, Any]):
        """调用 MCP 工具
        Args:
            tool_name (str): 工具名称
            data (dict[str, Any]): 工具参数
        """
        if self.mcp_client is None:
            raise RuntimeError("MCP Server 未连接！")
        return await self.mcp_client.call_tool(tool_name, data)

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
        if self.tools is None or update_tools:
            tools = await self.mcp_client.list_tools()
            self.tools = tools
            logger.info(f"🛠️  可用工具: {[tool.name for tool in tools]}")

    def _format_tools_for_openai(self):
        """将 MCP 工具格式转换为 OpenAI 工具格式"""
        openai_tools = [
            ToolFunctionSchema(
                strict=True,
                type="function",
                function=FunctionDefinitionSchema(
                    name=tool.name,
                    description=tool.description or f"运行名为：{tool.name}的工具",
                    parameters=FunctionParametersSchema(
                        type="object",
                        required=tool.inputSchema.get("required", []),
                        properties=tool.inputSchema.get("properties", {}),
                    ),
                ),
            )
            for tool in self.tools
        ]
        return openai_tools

    def _cast_tool_to_openai(self):
        self.openai_tools = self._format_tools_for_openai()

    def get_tools(self):
        """获取 MCP 工具列表，并转换为 OpenAI 工具列表"""
        return self._format_tools_for_openai()

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

    @staticmethod
    def _tools_wrapper(tool_name: str):
        async def tools_runner(data: dict[str, Any]) -> str:
            client = await ClientManager().get_client_by_tool_name(tool_name)
            return (await client.simple_call(tool_name, data)).data

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
        client = self.get_client_by_script(server_script)
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
                            f"{client}@{client.server_script} has a tool named {tool.function.name}, which is already registered"
                        )
                    name_to_clients_tmp[tool.function.name] = client
                    if ToolsManager().has_tool(tool.function.name):
                        remapped_name = (
                            f"referred_{random.randint(1, 100)}_{tool.function.name}"
                        )
                        logger.warning(
                            f"⚠️  工具已存在：{tool.function.name}，它将被重映射到：{remapped_name}"
                        )
                        tools_remapping_tmp[tool.function.name] = remapped_name
                        reversed_remappings_tmp[remapped_name] = tool.function.name
                        tool.function.name = remapped_name

                        ToolsManager().register_tool(
                            ToolData(
                                data=tool, func=self._tools_wrapper(tool.function.name)
                            )
                        )

        except Exception as e:
            if fail_then_raise:
                raise
            logger.error(f"❌ 连接到 MCP Server@{client.server_script} 失败：{e}")
        else:
            logger.info(f"✅ 加载到 MCP Server@{client.server_script} 成功")
            self.tools_remapping.update(tools_remapping_tmp)
            self.reversed_remappings.update(reversed_remappings_tmp)
            self.name_to_clients.update(name_to_clients_tmp)
            if isinstance(client.server_script, str | Path):
                server_script = str(client.server_script)
                self.script_to_clients[server_script] = client

    async def initialize_all(self):
        """连接所有 MCP Server"""
        async with self._lock:
            for client in self.clients:
                await self._load_this(client, False)
            self._is_initialized = True

    async def unregister_client(self, script_name: str | Path):
        """注销一个 MCP Server"""
        async with self._lock:
            script_name = str(script_name)
            if script_name in self.script_to_clients:
                client = self.script_to_clients.pop(script_name)
                for tool in client.openai_tools:
                    name = tool.function.name
                    ToolsManager().remove_tool(name)
                    ClientManager.name_to_clients.pop(name, None)
                    if remap := ClientManager.tools_remapping.pop(name, None):
                        ClientManager.reversed_remappings.pop(remap, None)
                for client in self.clients:
                    if client.server_script == script_name:
                        self.clients.remove(client)
                        break
