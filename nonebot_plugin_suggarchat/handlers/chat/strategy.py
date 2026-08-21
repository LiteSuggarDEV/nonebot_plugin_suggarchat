"""Agent 策略选择与 workflow 装配（从原 chat.py 抽出）"""

from __future__ import annotations

from typing import TYPE_CHECKING

from amrita_core.agent.strategy import AgentStrategy
from amrita_core.builtins.agent import (
    HybridReActAgentStrategy,
    NoActionAgentStrategy,
    ReActAgentStrategy,
)
from amrita_core.chatmanager import _step_workflow_rendered

if TYPE_CHECKING:
    from amrita_core.chatmanager.chat_object import NodeComposeRendered

__all__ = ["build_workflow", "select_agent_strategy"]


def select_agent_strategy(name: str) -> type[AgentStrategy]:
    """根据配置选择 Agent 执行策略类

    Args:
        name: 策略名（react / hybrid-react / no-action）

    Returns:
        对应策略类

    Raises:
        ValueError: 未知策略名
    """
    match name:
        case "react":
            return ReActAgentStrategy
        case "hybrid-react":
            return HybridReActAgentStrategy
        case "no-action":
            return NoActionAgentStrategy
        case _:
            raise ValueError(f"Invalid agent strategy: {name}")


def build_workflow(agent_workflow: str) -> NodeComposeRendered | None:
    """装配 workflow：仅 step-react 模式使用预编译工作流

    Args:
        agent_workflow: 配置的工作流名

    Returns:
        预编译渲染的工作流，非 step-react 时返回 None
    """
    return _step_workflow_rendered if agent_workflow == "step-react" else None
