import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar, Literal

import nonebot_plugin_localstore as store
import tomli
import tomli_w
from amrita_core import ModelPreset as ModelPreset
from amrita_core import set_config
from amrita_core.config import (
    AmritaConfig as AmritaCoreConfig,
)
from amrita_core.config import (
    LLMConfig as CoreLLMConfig,
)
from nonebot import get_driver, logger
from nonebot_plugin_uniconf import EnvfulConfigManager, UniConfigManager
from pydantic import BaseModel, Field, model_validator
from typing_extensions import final, override

from .preset_store import PresetStore
from .prompt_store import Prompt as Prompt
from .prompt_store import Prompts, PromptStore
from .services import ModelConfigService, PresetService, PromptService

# 配置目录
CONFIG_DIR: Path = store.get_plugin_config_dir()
driver = get_driver()
nb_config = driver.config


@lru_cache(maxsize=8)
def _compile_pattern(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


class ToolsConfig(BaseModel):
    #  Chat 插件独有（Core 已覆盖的字段移到 core.builtin / core.function_config）
    enable_report: bool = Field(default=True, description="是否启用内容审查系统")
    report_exclude_system_prompt: bool = Field(
        default=False,
        description="是否排除系统提示词，默认情况下，内容审查会检查系统提示和上下文",
    )
    report_exclude_context: bool = Field(
        default=False,
        description="是否排除上下文，仅检查最后一条消息，默认情况下，内容审查会检查系统提示和上下文",
    )
    report_then_block: bool = Field(
        default=True, description="检测到违规内容后是否熔断会话"
    )
    report_invoke_level: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="内容审查的严格程度，可选值：low, medium, high",
    )
    require_tools: bool = Field(
        default=False, description="是否强制要求每次调用至少使用一个工具"
    )


class SessionConfig(BaseModel):
    session_control: bool = Field(default=False, description="是否启用会话超时自动清理")
    session_allow_continue: bool = Field(default=True, description="是否允许会话继续")
    session_control_time: int = Field(
        default=60, description="会话超时时间（单位：分钟）"
    )
    session_control_history: int = Field(
        default=10, description="会话历史记录最大保存条数"
    )
    session_long_running_notify_seconds: int = Field(
        default=180,
        description="私聊Agent超时提示阈值（单位：秒），超过此时间未返回则提示用户可终止任务。设为0禁用",
    )


class AutoReplyConfig(BaseModel):
    enable: bool = Field(default=False, description="是否启用自动回复系统")
    global_enable: bool = Field(
        default=False, description="是否全局启用自动回复（无视会话状态）"
    )
    probability: float = Field(default=1e-2, description="随机触发概率（0.01=1%）")
    keywords: list[str] = Field(default=["at"], description="触发自动回复的关键字列表")
    keywords_mode: Literal["starts_with", "contains"] = Field(
        default="starts_with", description="自动回复配置(starts_with/contains)"
    )


class FunctionConfig(BaseModel):
    message_type: Literal["xml", "legacy"] = Field(
        default="legacy",
        description=(
            "消息格式类型：\n"
            '  xml    — <msg role="群主" name="张三" uid="12345">\n{内容}\n</msg>（结构清晰但费tokens）\n'
            "  legacy — [群主][张三（12345）]说:内容（紧凑但LLM易误解析）"
        ),
    )
    chat_pending_mode: Literal["single", "queue", "single_with_report"] = Field(
        default="queue",
        description="聊天时，如果同一个Session并发调用但是上一条消息没有处理完时插件的行为。\n"
        + "single: 忽略这条消息；\n"
        + "queue: 等待上一条消息处理完再处理；\n"
        + "single_with_report: 忽略这条消息并提示用户正在等待。",
    )
    synthesize_forward_message: bool = Field(
        default=True, description="是否解析合并转发消息"
    )
    nature_chat_style: bool = Field(
        default=True, description="是否启用自然对话风格优化(自动分句)"
    )
    nature_chat_cut_pattern: str = Field(
        default=r'([。！？!?;；\n]+)[""\'\'"\s]*', description="分句功能的正则表达式"
    )
    poke_reply: bool = Field(default=True, description="是否响应戳一戳事件")
    enable_group_chat: bool = Field(default=True, description="是否启用群聊功能")
    enable_private_chat: bool = Field(default=True, description="是否启用私聊功能")
    allow_custom_prompt: bool = Field(
        default=True, description="是否允许用户自定义提示词"
    )
    use_user_nickname: bool = Field(
        default=False, description="在群聊中使用QQ昵称而非群名片"
    )
    chat_object_keep_count: int = Field(
        default=10, description="单会话聊天对象保存数量限制"
    )
    forward_threshold: int = Field(
        default=200,
        description="最终响应超过该字符数时改用合并转发发送（0=禁用）",
    )
    forward_min_chunk: int = Field(
        default=500,
        description="合并转发时每个分块的最小字符数，不满足则不分块",
    )

    @property
    def pattern(self) -> re.Pattern:
        """
        获取分句的正则表达式
        """
        return _compile_pattern(self.nature_chat_cut_pattern)


class PresetSwitch(BaseModel):
    backup_preset_list: list[str] = Field(
        default=[], description="主模型不可用时自动切换的备选模型预设列表"
    )


class AdminConfig(BaseModel):
    allow_send_to_admin: bool = Field(
        default=False, description="是否允许发送消息给管理员"
    )
    admin_group: int = Field(default=0, description="管理员群号（0=未设置）")


class ExtendConfig(BaseModel):
    say_after_self_msg_be_deleted: bool = Field(
        default=False, description="消息被撤回后是否自动回复"
    )
    group_added_msg: str = Field(
        default="你好，我是Amria，有关使用手册见https://bot.amritabot.com",
        description="入群欢迎消息",
    )
    send_msg_after_be_invited: bool = Field(
        default=False, description="被邀请入群后是否主动发言"
    )
    after_deleted_say_what: list[str] = Field(
        default=[
            "抱歉啦，不小心说错啦～",
            "嘿，发生什么事啦？我",
            "唔，我是不是说错了什么？",
            "纠错时间到，如果我说错了请告诉我！",
            "发生了什么？我刚刚没听清楚呢~",
            "我会记住的，绝对不再说错话啦~",
            "哦，看来我又犯错了，真是不好意思！",
            "哈哈，看来我得多读书了~",
            "哎呀，真是个小口误，别在意哦~",
            "哎呀，我也有尴尬的时候呢~",
            "希望我能继续为你提供帮助，不要太在意我的小错误哦！",
        ],
        description="消息被撤回后的随机回复列表",
    )


class UsageLimitConfig(BaseModel):
    enable_usage_limit: bool = Field(default=False, description="是否启用使用频率限制")
    group_daily_limit: int = Field(default=100, description="单个群组每日最大使用次数")
    user_daily_limit: int = Field(default=100, description="单个用户每日最大使用次数")
    group_daily_token_limit: int = Field(
        default=200000, description="单个群组每日最大token消耗量"
    )
    user_daily_token_limit: int = Field(
        default=100000, description="单个用户每日最大token消耗量"
    )
    total_daily_limit: int = Field(default=1500, description="总使用次数限制")
    total_daily_token_limit: int = Field(default=1000000, description="总使用token限制")
    global_insights_expire_days: int = Field(default=7, description="全局统计过期天数")
    limit_msg: list[str] = Field(
        default=["今日额度已达上限，请明天再试。"],
        description="达到使用限制时返回的消息",
    )


class LLM_Config(BaseModel):
    #  Chat 插件独有（Core 已覆盖的字段如 memory_length_limit 等已移至 core.llm）
    tools: ToolsConfig = Field(default=ToolsConfig(), description="工具调用子系统")
    stream: bool = Field(default=False, description="是否启用流式响应（逐字输出）")
    block_msg: list[str] = Field(
        default=["你好，这个问题我暂时无法处理，请稍后再试。"],
        description="触发安全熔断时随机返回的提示消息",
    )
    agent_strategy: Literal["react", "hybrid-react", "no-action"] = Field(
        default="react",
        description="代理策略：react(仅使用ReAct) / hybrid-react(使用混合ReAct) / no-action(跳过Agent运行)",
    )
    agent_workflow: Literal["react", "step-react"] = Field(
        default="react",
        description=(
            "推理工作流：react(普通ReAct循环，一轮工具调用内完成推理与执行) / "
            "step-react(Step驱动的ReAct循环：LLM先分解计划，框架逐Step走完，"
            "支持计划修订update_step、停滞检测、Step间压缩，需模型支持结构化输出)"
        ),
    )


class Config(BaseModel):
    #  直接嵌入 Core 配置
    core: AmritaCoreConfig = Field(
        default_factory=AmritaCoreConfig,
        description="Amrita Core 原生配置（与 chat 插件共享）。写入时自动同步到 Core 全局单例。",
    )

    #  Chat 插件独有字段
    preset_extension: PresetSwitch = Field(
        default=PresetSwitch(), description="预设模型扩展配置"
    )
    default_preset: ModelPreset = Field(
        default=ModelPreset(), description="默认预设配置"
    )
    session: SessionConfig = Field(default=SessionConfig(), description="会话管理配置")
    autoreply: AutoReplyConfig = Field(
        default=AutoReplyConfig(), description="自动回复设置"
    )
    function: FunctionConfig = Field(
        default=FunctionConfig(), description="功能开关配置"
    )
    admin: AdminConfig = Field(default=AdminConfig(), description="管理员配置")
    extended: ExtendConfig = Field(default=ExtendConfig(), description="扩展行为设置")
    llm: LLM_Config = Field(default=LLM_Config(), description="LLM核心功能配置")
    extra: dict[str, Any] = Field(default={}, description="扩展预留区")
    usage_limit: UsageLimitConfig = Field(
        default=UsageLimitConfig(), description="使用限额配置"
    )
    enable: bool = Field(default=False, description="是否启用 Amrita的聊天能力")
    parse_segments: bool = Field(
        default=True, description="是否解析特殊消息段（如@提及/合并转发等）"
    )
    preset: str = Field(default="default", description="默认使用的模型预设配置名称")
    group_prompt_character: str = Field(
        default="default", description="群聊场景使用的提示词模板名称"
    )
    private_prompt_character: str = Field(
        default="default", description="私聊场景使用的提示词模板名称"
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_old_config(cls, data: Any) -> Any:
        """
        迁移旧版 flat 配置到 core 嵌入结构。

        旧 TOML 格式 (无 core 键):
            { "llm": { "memory_length_limit": ..., ... },
              "cookies": { "cookie": ..., "enable_cookie": ... },
              "llm.tools": { "tool_calling_mode": ..., ... } }

        新 TOML 格式 (有 core 键则跳过):
            { "core": { "llm": {...}, "cookie": {...}, "builtin": {...}, "function_config": {...} },
              "llm": { "block_msg": ..., "agent_strategy": ..., "stream": ..., "tools": {<chat-only>} },
              ... }
        """
        if not isinstance(data, dict):
            return data
        if "core" in data:
            return data  # 已迁移

        core_data: dict[str, Any] = {}

        # cookies -> core.cookie
        if "cookies" in data:
            cookies = data.pop("cookies")
            if isinstance(cookies, dict):
                core_data["cookie"] = {
                    k: v
                    for k, v in {
                        "enable_cookie": cookies.get("enable_cookie", False),
                        "cookie": cookies.get("cookie", ""),
                    }.items()
                    if v is not None
                }

        # llm.* -> core.llm (CoreLLMConfig fields)
        if "llm" in data and isinstance(data["llm"], dict):
            llm = data["llm"]
            core_llm: dict[str, Any] = {}
            for field_name in CoreLLMConfig.model_fields:
                if field_name in llm:
                    val = llm.pop(field_name)
                    if val is not None:
                        core_llm[field_name] = val
            if core_llm:
                core_data["llm"] = core_llm

            # llm.tools.* -> core.builtin & core.function_config
            if "tools" in llm and isinstance(llm["tools"], dict):
                tools = llm["tools"]
                tools.pop("use_minimal_context", None)
                tools.pop("agent_tool_call_limit", None)

                builtin = {
                    "tool_calling_mode": tools.pop("tool_calling_mode", "agent"),
                    "agent_tool_call_notice": tools.pop(
                        "agent_tool_call_notice", "hide"
                    ),
                    "agent_thought_mode": tools.pop("agent_thought_mode", "chat"),
                    "agent_reasoning_hide": tools.pop("agent_reasoning_hide", False),
                }
                core_data["builtin"] = {
                    k: v for k, v in builtin.items() if v is not None
                }

                func_cfg = {
                    "use_minimal_context": tools.pop("use_minimal_context", True),
                    "agent_tool_call_limit": tools.pop("agent_tool_call_limit", 10),
                    "agent_middle_message": tools.pop("agent_middle_message", True),
                    "agent_mcp_client_enable": tools.pop(
                        "agent_mcp_client_enable", False
                    ),
                    "agent_mcp_server_scripts": tools.pop(
                        "agent_mcp_server_scripts", []
                    ),
                }
                core_data["function_config"] = {
                    k: v for k, v in func_cfg.items() if v is not None
                }

        if core_data:
            data["core"] = core_data
        return data

    @classmethod
    def load_from_toml(cls, path: Path) -> "Config":
        """从 TOML 文件加载配置"""
        if not path.exists():
            return cls()
        with open(str(path), encoding="u8") as f:
            data: dict[str, Any] = tomli.loads(f.read())
        return cls.model_validate(data)

    def validate_value(self):
        """校验配置"""
        if self.core.llm.max_tokens <= 0:
            raise ValueError("max_tokens必须大于零!")
        if self.core.llm.llm_timeout <= 0:
            raise ValueError("LLM请求超时时间必须大于零！")
        if self.core.llm.session_tokens_windows <= 0:
            raise ValueError("上下文最大Tokens限制必须大于零！")
        if self.session.session_control:
            if self.session.session_control_history <= 0:
                raise ValueError("会话历史最大值不能为0！")
            if self.session.session_control_time <= 0:
                raise ValueError("会话生命周期时间不能小于零！")

    @classmethod
    def load_from_json(cls, path: Path) -> "Config":
        """从 JSON 文件加载配置"""
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return cls.model_validate(data)

    def save_to_toml(self, path: Path):
        """保存配置到 TOML 文件"""
        with path.open("w", encoding="utf-8") as f:
            f.write(tomli_w.dumps(self.model_dump(exclude_none=True)))

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """覆盖 model_dump，默认排除 None 值以兼容 TOML 序列化。"""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)


@final
class ConfigManager(EnvfulConfigManager[Config]):
    config_dir: Path = CONFIG_DIR
    private_prompts: Path = config_dir / "private_prompts"
    group_prompts: Path = config_dir / "group_prompts"
    custom_models_dir: Path = config_dir / "models"
    prompt_store: ClassVar[PromptStore] = PromptStore(private_prompts, group_prompts)
    preset_store: ClassVar[PresetStore] = PresetStore(custom_models_dir)
    config: Config
    _owner_name = store._try_get_caller_plugin().name
    __lateinit__ = True

    def __init__(self) -> None:
        # 领域服务（阶段 3）：配置读写与业务语义解耦。
        # 服务构造只依赖惰性回调，配置加载前后均可安全初始化。
        self.presets = PresetService(
            self.preset_store,
            get_config=lambda: self.config,
            get_ins_config=lambda: self.ins_config,
            save_config=lambda: self.save_config(),
        )
        self.prompts = PromptService(
            self.prompt_store,
            get_ins_config=lambda: self.ins_config,
        )
        self.models = ModelConfigService(
            self.preset_store,
            get_ins_config=lambda: self.ins_config,
        )

    @override
    def _update_cache(self, value: Config | None = None):
        super()._update_cache(value)
        set_config(self.config.core)

    async def __apost_init__(self):
        await self.load()

    async def load(self):
        """_初始化配置目录_"""

        async def prompt_callback():
            logger.info("正在重载插件提示词文件...")
            await self.get_prompts(False, True)
            self.load_prompt()
            logger.success("提示词文件已重载")

        async def models_callback():
            logger.info("正在重载模型目录...")
            await self.get_all_presets(False)
            logger.success("完成")

        logger.info("正在初始化存储目录...")
        logger.debug(f"配置目录: {self.config_dir}")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.private_prompts, exist_ok=True)
        os.makedirs(self.group_prompts, exist_ok=True)
        os.makedirs(self.custom_models_dir, exist_ok=True)

        await UniConfigManager().add_directory(
            "models",
            lambda *_: models_callback(),
            owner_name=self._owner_name,
        )
        self.validate_presets()
        ps = await self.get_all_presets(cache=False)
        logger.info(f"加载了{len(ps)}个模型 (包含默认)")
        p = await self.get_prompts(cache=False)
        logger.info(f"加载了{len(p.group) + len(p.private)}个提示词")
        self.load_prompt()
        await UniConfigManager().add_directory(
            "group_prompts",
            lambda *_: prompt_callback(),
            lambda change: (
                (change[1].startswith(str(self.group_prompts)))
                and change[1].endswith(".txt")
            ),
            owner_name=self._owner_name,
        )
        await UniConfigManager().add_directory(
            "private_prompts",
            lambda *_: prompt_callback(),
            lambda change: (
                change[1].startswith(str(self.private_prompts))
                and change[1].endswith(".txt")
            ),
            owner_name=self._owner_name,
        )

    async def get_prompts(
        self, cache: bool = False, load_only: bool = False
    ) -> Prompts:
        """获取提示词（委托 PromptService）"""
        return await self.prompts.get_prompts(cache=cache, load_only=load_only)

    def load_prompt(self):
        """加载提示词，匹配预设（委托 PromptService，纯内存操作）"""
        self.prompts.load_prompt()

    @property
    def private_train(self) -> dict[str, str]:
        """获取私聊提示词（委托 PromptService）"""
        return self.prompts.private_train

    @property
    def group_train(self) -> dict[str, str]:
        """获取群聊提示词（委托 PromptService）"""
        return self.prompts.group_train

    def validate_presets(self):
        """校验所有预设文件（委托 PresetService）"""
        self.presets.validate()

    async def get_all_presets(self, cache: bool = True) -> list[ModelPreset]:
        """获取模型列表（委托 PresetService，默认走缓存）"""
        return await self.presets.get_all_presets(cache=cache)

    async def get_preset(
        self, preset: str, fix: bool = False, cache: bool = True
    ) -> ModelPreset:
        """获取预设配置（委托 PresetService，默认走缓存）

        Args:
            preset (str): _预设的字符串名称_
            fix (bool, optional): _是否修正不存在的预设_. Defaults to False.
            cache (bool, optional): _是否使用缓存_. Defaults to True.

        Returns:
            ModelPreset: _模型预设对象_
        """
        return await self.presets.get_preset(preset, fix=fix, cache=cache)

    def get_preset_path(self, name: str) -> Path:
        """预设名对应的文件路径（委托 PresetService）"""
        return self.presets.get_preset_path(name)

    def forget_preset(self, name: str) -> None:
        """移除预设名到路径的记录（委托 PresetService）"""
        self.presets.forget_preset(name)

    async def save_config(self):
        """保存配置"""
        await UniConfigManager().save_config(self._owner_name)

    async def set_config(self, key: str, value: str):
        """
        设置配置

        :param key: 配置项的名称
        :param value: 配置项的值

        :raises KeyError: 如果配置项不存在，则抛出异常
        """
        if hasattr(self.ins_config, key):
            setattr(self.ins_config, key, value)
            await self.save_config()
        else:
            raise KeyError(f"配置项 {key} 不存在")

    async def register_config(self, key: str, default_value=None):
        """
        注册配置项

        :param key: 配置项的名称

        """
        if default_value is None:
            default_value = "null"
        self.ins_config.extra.setdefault(key, default_value)
        await self.save_config()

    async def reg_config(self, key: str, default_value=None):
        """
        注册配置项

        :param key: 配置项的名称

        """
        return await self.register_config(key, default_value)

    def reg_model_config(self, key: str, default_value=None):
        """
        注册模型配置项（委托 ModelConfigService）

        :param key: 配置项的名称

        """
        self.models.reg_model_config(key, default_value)


config_manager = ConfigManager()
