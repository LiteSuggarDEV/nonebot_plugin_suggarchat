"""上下文构建与统计工具

- build_train_dict(): 构建与 chat 主流程完全一致的 system prompt（含格式说明与 EXTRA 规则）
- estimate_tokens(): 全列表分词计算，口径对齐 Core MemoryLimiter._limit_tokens
"""

from __future__ import annotations

from amrita_core.libchat import text_generator
from amrita_core.tokenizer import hybrid_token_count
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot_plugin_amrita.memory import MemorySchema

from ..config import Config, config_manager


def _format_desc_xml() -> str:
    """XML 消息格式说明（与 chat 主流程一致）"""
    return (
        "你的工作环境是一个社交软件。**输入**的聊天记录使用 XML 标签标记：\n"
        '  <msg role="群主/管理员/普通成员/自己" name="昵称" uid="QQ号">\n'
        "  消息内容（多行）\n"
        "  </msg>\n"
        "引用消息使用 <ref name='...' uid='...'>...</ref> 包裹。\n"
        "你的**输出**必须是纯自然语言文本，**严禁**输出任何 XML 标签、属性或类似的结构化标记。\n"
        "正确示例：\n"
        "  输入：<msg role='普通成员' name='张三' uid='12345'>今天天气真好</msg>\n"
        "  输出：今天天气真好呢。\n"
        "错误示例（**禁止**）：\n"
        "  输入：<msg role='普通成员' name='张三' uid='12345'>今天天气真好</msg>\n"
        "  输出：<msg role='自己' name='爱丽丝' uid='67890'>是啊，阳光明媚。</msg>\n"
    )


def _format_desc_legacy() -> str:
    """legacy 消息格式说明（与 chat 主流程一致）"""
    return (
        "你的工作环境是一个社交软件。所有**输入**的聊天记录遵循以下格式：\n"
        "- 每条消息以 [身份] 开头，方括号内是消息发送者的身份标记（群主/管理员/普通成员/自己）\n"
        "- 身份后跟 [昵称（QQ号）] 再跟 说:内容\n"
        "  示例: [普通成员][张三（12345）]说:今天天气真好\n"
        "- 用户输入中已对特殊字符做了全角转义（［ ］ 说：），避免与格式标记混淆\n"
        "你的**输出**必须是纯自然语言文本，**严禁**使用上述方括号或“说:”格式，也不能添加任何身份、昵称或QQ号标记。\n"
        "正确示例：\n"
        "  输入：[普通成员][张三（12345）]说:今天天气真好\n"
        "  输出：今天天气真好呢。\n"
        "错误示例（**禁止**）：\n"
        "  输入：[普通成员][张三（12345）]说:今天天气真好\n"
        "  输出：[自己][爱丽丝（67890）]说:是啊，阳光明媚。\n"
    )


def build_train_dict(
    event: MessageEvent, memory: MemorySchema, config: Config
) -> dict[str, str]:
    """构建 system prompt（与 chat 主流程完全一致）

    Args:
        event: 消息事件
        memory: 用户记忆（用于 EXTRA 规则拼接）
        config: 插件配置

    Returns:
        {"role": "system", "content": train_content}
    """
    train = (
        config_manager.group_train
        if isinstance(event, GroupMessageEvent)
        else config_manager.private_train
    )
    format_desc = (
        _format_desc_xml()
        if config.function.message_type == "xml"
        else _format_desc_legacy()
    )
    train_content = (
        "<SCHEMA_EXTENSIONS>\n"
        + "你在纯文本环境工作，不允许使用MarkDown回复。"
        + f"<IO_REQUIREMENT>\n{format_desc}\n</IO_REQUIREMENT>"
        + "请以你自己的角色身份参与讨论，交流时不同话题尽量不使用相似句式回复。"
        + "`<EXTRA>`规则仅作为补充，如果与EXTRA规则上文有冲突，请遵循上文规则。"
        + "\n</SCHEMA_EXTENSION>\n"
        + (
            train["content"]
            .replace("{self_id}", str(event.self_id))
            .replace("{user_id}", str(event.user_id))
            .replace("{user_name}", str(event.sender.nickname))
        )
        + (
            f"<EXTRA>\n（此处是EXTRA规则，如果与上文有任何冲突，请忽略此EXTRA规则）\n{memory.extra_prompt}\n</EXTRA>"
            if config.function.allow_custom_prompt
            else ""
        )
    )
    return {"role": "system", "content": train_content}


def estimate_tokens(train: dict[str, str], memory: MemorySchema, config: Config) -> int:
    """按 MemoryLimiter 口径计算 train + 全部消息的总 token 数

    对齐 Core `MemoryLimiter._limit_tokens` 的 `get_token()`：
    - 全列表（system prompt + 全部消息）
    - text_generator(full_message=True) 生成文本
    - hybrid_token_count(tokens_count_mode, tokenizer_used)

    Args:
        train: system prompt
        memory: 用户记忆
        config: 插件配置

    Returns:
        总 token 数
    """
    messages = [train, *memory.memory_json.messages]
    return sum(
        hybrid_token_count(
            msg,
            config.core.llm.tokens_count_mode,
            tokenizer_type=config.core.function_config.tokenizer_used,
        )
        for msg in text_generator(messages, full_message=True)
    )
