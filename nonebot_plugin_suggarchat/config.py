from __future__ import annotations

import copy
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypeVar

import aiofiles
import nonebot_plugin_localstore as store
import tomli
import tomli_w
from nonebot import get_driver, logger
from nonebot_plugin_uniconf import EnvfulConfigManager, UniConfigManager
from pydantic import BaseModel, Field

__kernel_version__ = "unknown"

# 保留为其他插件提供的引用

# 配置目录
CONFIG_DIR: Path = store.get_plugin_config_dir()
driver = get_driver()
nb_config = driver.config
STRDICT = dict[str, Any]

T = TypeVar("T", STRDICT, list[str | STRDICT], str)

# 缓存的正则表达式
_re_hash: int = 0
_cached_pattern: re.Pattern[str] | None = None


def replace_env_vars(
    data: T,
) -> T:
    """递归替换环境变量占位符，但不修改原始数据"""
    data_copy = copy.deepcopy(data)  # 创建原始数据的深拷贝[4,5](@ref)
    if isinstance(data_copy, dict):
        for key, value in data_copy.items():
            data_copy[key] = replace_env_vars(value)
    elif isinstance(data_copy, list):
        for i in range(len(data_copy)):
            data_copy[i] = replace_env_vars(data_copy[i])
    elif isinstance(data_copy, str):
        patterns = (
            r"\$\{(\w+)\}",
            r"\{\{(\w+)\}\}",
        )  # 支持两种格式的占位符，分别为 ${} 和 {{}}

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return os.getenv(var_name, "")  # 若未设置环境变量，返回空字符串

        for pattern in patterns:
            if re.search(pattern, data_copy):
                # 如果匹配到占位符，则进行替换
                data_copy = re.sub(pattern, replacer, data_copy)
                break  # 替换后跳出循环，避免重复替换
    return data_copy


class ModelPreset(BaseModel):
    model: str = Field(default="", description="使用的AI模型名称（如gpt-3.5-turbo）")
    name: str = Field(default="default", description="当前预设的标识名称")
    base_url: str = Field(
        default="", description="API服务的基础地址（为空则使用OpenAI默认地址）"
    )
    api_key: str = Field(default="", description="访问API所需的密钥")
    protocol: str = Field(default="__main__", description="协议适配器类型")
    thought_chain_model: bool = Field(
        default=False, description="是否启用思维链模型优化（增强复杂问题处理）"
    )
    multimodal: bool = Field(
        default=False, description="是否支持多模态输入（如图片识别）"
    )
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path):
        if path.exists():
            with path.open(
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)
            return cls.model_validate(data)
        return cls()  # 返回默认值

    def save(self, path: Path):
        with path.open("w", encoding="u8") as f:
            json.dump(self.model_dump(), f, indent=4, ensure_ascii=False)


class ToolsConfig(BaseModel):
    enable_tools: bool = Field(
        default=True,
        description="是否启用外部工具调用功能（关闭此选项不影响内容审查系统）",
    )
    use_minimal_context: bool = Field(
        default=True,
        description="是否使用最小上下文，即使用系统prompt+用户最后一条消息（关闭此选项将使用消息列表的所有上下文，在Agent工作流执行中可能会消耗大量Tokens，启用此选项可能会有效降低Tokens使用量）",
    )
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
    agent_mode_enable: bool = Field(
        default=False, description="启用智能体模式（实验体验）"
    )
    agent_tool_call_limit: int = Field(
        default=10, description="智能体模式下的工具调用限制"
    )
    agent_tool_call_notice: Literal["hide", "notify"] = Field(
        default="hide",
        description="智能体模式下的工具调用情况提示方式，hide为隐藏，notify为通知",
    )
    agent_thought_mode: Literal[
        "reasoning", "chat", "reasoning-required", "reasoning-optional"
    ] = Field(
        default="chat",
        description="智能体模式下的思考模式，reasoning模式会先执行思考过程，然后执行任务；"
        "reasoning-required要求每次Tool Calling都执行任务分析；"
        "reasoning-optional不要求reasoning，但是允许reasoning；"
        "chat模式会直接执行任务",
    )
    agent_reasoning_hide: bool = Field(
        default=False, description="是否隐藏智能体模式下的思考过程"
    )
    agent_middle_message: bool = Field(
        default=True, description="是否在智能体模式下允许Agent向用户发送中间消息"
    )
    agent_mcp_client_enable: bool = Field(
        default=False, description="是否启用MCP客户端"
    )
    agent_mcp_server_scripts: list[str] = Field(
        default=[], description="MCP服务端脚本列表"
    )


class SessionConfig(BaseModel):
    session_control: bool = Field(default=False, description="是否启用会话超时自动清理")
    session_control_time: int = Field(
        default=60, description="会话超时时间（单位：分钟）"
    )
    session_control_history: int = Field(
        default=10, description="会话历史记录最大保存条数"
    )
    session_max_tokens: int = Field(
        default=5000, description="单次会话上下文最大token容量"
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

    @property
    def pattern(self) -> re.Pattern:
        """
        获取分句的正则表达式
        """
        global _cached_pattern, _re_hash
        pattern_hash = hash(self.nature_chat_cut_pattern)
        if pattern_hash != _re_hash or _cached_pattern is None:
            _cached_pattern = re.compile(self.nature_chat_cut_pattern)
            _re_hash = pattern_hash
        return _cached_pattern


class PresetSwitch(BaseModel):
    backup_preset_list: list[str] = Field(
        default=[], description="主模型不可用时自动切换的备选模型预设列表"
    )
    multi_modal_preset_list: list[str] = Field(
        default=[], description="多模态场景预设调用顺序"
    )


class CookieModel(BaseModel):
    cookie: str = Field(default="", description="用于安全检测的Cookie字符串")
    enable_cookie: bool = Field(default=False, description="是否启用Cookie泄露检测机制")

    @property
    def block_msg(self) -> list[str]:
        return ConfigManager().config.llm_config.block_msg

    @block_msg.setter
    def block_msg(self, value: list[str]):
        ConfigManager().config.llm_config.block_msg = value


class ExtendConfig(BaseModel):
    say_after_self_msg_be_deleted: bool = Field(
        default=False, description="消息被撤回后是否自动回复"
    )
    group_added_msg: str = Field(
        default="你好，我是Suggar，欢迎使用SuggarAI聊天机器人...",
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


class AdminConfig(BaseModel):
    allow_send_to_admin: bool = False
    admin_group: int = 0
    admins: list[int] = []


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


class LLM_Config(BaseModel):
    tools: ToolsConfig = Field(default=ToolsConfig(), description="工具调用配置")
    stream: bool = Field(default=False, description="是否启用流式响应（逐字输出）")
    memory_lenth_limit: int = Field(default=50, description="记忆上下文的最大消息数量")
    max_tokens: int = Field(default=100, description="单次回复生成的最大token数")
    tokens_count_mode: Literal["word", "bpe", "char"] = Field(
        default="bpe", description="Token计算模式：bpe(子词)/word(词语)/char(字符)"
    )
    enable_tokens_limit: bool = Field(
        default=True, description="是否启用上下文长度限制"
    )
    llm_timeout: int = Field(default=60, description="API请求超时时间（秒）")
    auto_retry: bool = Field(default=True, description="请求失败时自动重试")
    max_retries: int = Field(default=3, description="最大重试次数")
    enable_memory_abstract: bool = Field(
        default=True,
        description="是否启用上下文记忆摘要(将删除上下文替换为一个摘要插入到system instruction中)",
    )
    memory_abstract_proportion: float = Field(
        default=15e-2, description="上下文摘要比例(0.15=15%)"
    )
    block_msg: list[str] = Field(
        default=["你好，这个问题我暂时无法处理，请稍后再试。"],
        description="触发安全熔断时随机返回的提示消息",
    )


class Config(BaseModel):
    admin: AdminConfig = AdminConfig()
    preset_extension: PresetSwitch = Field(
        default=PresetSwitch(), description="预设模型扩展配置"
    )
    default_preset: ModelPreset = Field(
        default=ModelPreset(), description="默认预设配置"
    )
    session: SessionConfig = Field(default=SessionConfig(), description="会话管理配置")
    cookies: CookieModel = Field(
        default=CookieModel(), description="电子水印检测功能配置"
    )
    autoreply: AutoReplyConfig = Field(
        default=AutoReplyConfig(), description="自动回复设置"
    )
    function: FunctionConfig = Field(
        default=FunctionConfig(), description="功能开关配置"
    )
    extended: ExtendConfig = Field(default=ExtendConfig(), description="扩展行为设置")
    llm_config: LLM_Config = Field(default=LLM_Config(), description="大语言模型配置")
    extra: dict[str, Any] = Field(default={}, description="扩展预留区")
    usage_limit: UsageLimitConfig = Field(
        default=UsageLimitConfig(), description="使用限额配置"
    )
    enable: bool = Field(default=False, description="是否启用 SuggarChat 主功能")
    parse_segments: bool = Field(
        default=True, description="是否解析特殊消息段（如@提及/合并转发等）"
    )
    matcher_function: bool = Field(
        default=True, description="是否启用 SuggarMatcher 高级匹配功能"
    )
    preset: str = Field(default="default", description="默认使用的模型预设配置名称")
    group_prompt_character: str = Field(
        default="default", description="群聊场景使用的提示词模板名称"
    )
    private_prompt_character: str = Field(
        default="default", description="私聊场景使用的提示词模板名称"
    )

    @classmethod
    def load_from_toml(cls, path: Path) -> Config:
        """从 TOML 文件加载配置"""
        if not path.exists():
            return cls()
        with open(str(path), encoding="u8") as f:
            data: dict[str, Any] = tomli.loads(f.read())
        return cls.model_validate(data)

    def validate_value(self):
        """校验配置"""
        if self.llm_config.max_tokens <= 0:
            raise ValueError("max_tokens必须大于零!")
        if self.llm_config.llm_timeout <= 0:
            raise ValueError("LLM请求超时时间必须大于零！")
        if self.session.session_max_tokens <= 0:
            raise ValueError("上下文最大Tokens限制必须大于零！")
        if self.session.session_control:
            if self.session.session_control_history <= 0:
                raise ValueError("会话历史最大值不能为0！")
            if self.session.session_control_time <= 0:
                raise ValueError("会话生命周期时间不能小于零！")

    @classmethod
    def load_from_json(cls, path: Path) -> Config:
        """从 JSON 文件加载配置"""
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return cls.model_validate(data)

    def save_to_toml(self, path: Path):
        """保存配置到 TOML 文件"""
        with path.open("w", encoding="utf-8") as f:
            f.write(tomli_w.dumps(self.model_dump()))


@dataclass
class Prompt:
    text: str = ""
    name: str = "default"


@dataclass
class Prompts:
    group: list[Prompt] = field(default_factory=list)
    private: list[Prompt] = field(default_factory=list)

    def save_group(self, path: Path):
        """保存群组提示词"""
        for prompt in self.group:
            with (path / f"{prompt.name}.txt").open(
                "w",
                encoding="u8",
            ) as f:
                f.write(prompt.text)

    def save_private(self, path: Path):
        """保存私聊提示词"""
        for prompt in self.private:
            with (path / f"{prompt.name}.txt").open(
                "w",
                encoding="u8",
            ) as f:
                f.write(prompt.text)


class ConfigManager(EnvfulConfigManager[Config]):
    config_class = Config
    _owner_name: str = store._try_get_caller_plugin().name
    config_dir = CONFIG_DIR

    @classmethod
    def __init_classvars__(cls):
        config_dir = cls.config_dir
        cls.private_prompts = config_dir / "private_prompts"
        cls.group_prompts = config_dir / "group_prompts"
        cls.custom_models_dir = config_dir / "models"
        cls._private_train = {}
        cls._group_train = {}
        cls._model_name2file = {}
        cls.models = []
        cls.prompts = Prompts()

    async def load(self):
        """_初始化配置目录_"""

        async def prompt_callback():
            logger.info("正在重载插件提示词文件...")
            await self.get_prompts(False, True)
            await self.load_prompt()
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
        if self._task:
            await self._task
        self.__class__.ins_config = await UniConfigManager().get_config(
            self._owner_name
        )

        await UniConfigManager().add_directory("models", lambda *_: models_callback())
        self.validate_presets()
        ps = await self.get_all_presets(cache=False)
        logger.info(f"加载了{len(ps)}个模型")
        p = await self.get_prompts(cache=False)
        logger.info(f"加载了{len(p.group) + len(p.private)}个提示词")
        await self.load_prompt()
        await UniConfigManager().add_directory(
            "group_prompts",
            lambda *_: prompt_callback(),
            lambda change: (change[1].startswith(str(self.group_prompts)))
            and change[1].endswith(".txt"),
        )
        await UniConfigManager().add_directory(
            "private_prompts",
            lambda *_: prompt_callback(),
            lambda change: change[1].startswith(str(self.private_prompts))
            and change[1].endswith(".txt"),
        )

    def validate_presets(self):
        def validate_preset(path: Path):
            try:
                model_data = ModelPreset.load(path)
                model_data.save(path)
                self._model_name2file[model_data.name] = path
            except Exception as e:
                logger.opt(colors=True).error(
                    f"Failed to validate preset '{file!s}' because '{e!s}'"
                )

        for file in self.custom_models_dir.glob("*.json"):
            validate_preset(file)

    async def get_all_presets(self, cache: bool = False) -> list[ModelPreset]:
        """获取模型列表"""
        if cache and self.models:
            return [model for model, _ in self.models]
        self.models.clear()  # 清空模型列表

        for file in self.custom_models_dir.glob("*.json"):
            model_data = ModelPreset.load(file).model_dump()
            preset_data = replace_env_vars(model_data)
            if not isinstance(preset_data, dict):
                raise TypeError("Expected replace_env_vars to return a dict")
            model_preset = ModelPreset.model_validate(preset_data)
            self._model_name2file[model_preset.name] = file
            self.models.append((model_preset, file.stem))

        return [model for model, _ in self.models]

    async def get_preset(
        self, preset: str, fix: bool = False, cache: bool = False
    ) -> ModelPreset:
        """_获取预设配置_

        Args:
            preset (str): _预设的字符串名称_
            fix (bool, optional): _是否修正不存在的预设_. Defaults to False.
            cache (bool, optional): _是否使用缓存_. Defaults to False.

        Returns:
            ModelPreset: _模型预设对象_
        """
        if preset == "default":
            return self.config.default_preset
        for model in await self.get_all_presets(cache=cache):
            if model.name == preset:
                return model
        if fix:
            self.ins_config.preset = "default"
            await self.save_config()
        return await self.get_preset("default", fix, cache)

    async def get_prompts(
        self, cache: bool = False, load_only: bool = False
    ) -> Prompts:
        """获取提示词"""
        if cache and self.prompts:
            return self.prompts
        self.prompts = Prompts()
        for file in self.private_prompts.glob("*.txt"):
            async with aiofiles.open(file, encoding="utf-8") as f:
                prompt = await f.read()
            self.prompts.private.append(Prompt(prompt, file.stem))
        for file in self.group_prompts.glob("*.txt"):
            async with aiofiles.open(file, encoding="utf-8") as f:
                prompt = await f.read()
            self.prompts.group.append(Prompt(prompt, file.stem))
        if not self.prompts.private:
            self.prompts.private.append(Prompt("", "default"))
        if not self.prompts.group:
            self.prompts.group.append(Prompt("", "default"))

        if not load_only:
            self.prompts.save_private(self.private_prompts)
            self.prompts.save_group(self.group_prompts)

        return self.prompts

    @property
    def private_train(self) -> dict[str, str]:
        """获取私聊提示词"""
        return deepcopy(self._private_train)

    @property
    def group_train(self) -> dict[str, str]:
        """获取群聊提示词"""
        return deepcopy(self._group_train)

    async def load_prompt(self):
        """加载提示词，匹配预设"""
        for prompt in self.prompts.group:
            if prompt.name == self.ins_config.group_prompt_character:
                self.__class__._group_train = {"role": "system", "content": prompt.text}
                break
        else:
            self.__class__._group_train = {
                "role": "system",
                "content": next(
                    i for i in self.prompts.group if i.name == "default"
                ).text,
            }
            logger.warning(
                f"没有找到名称为 {self.ins_config.group_prompt_character} 的群组提示词，将使用default.txt!"
            )

        for prompt in self.prompts.private:
            if prompt.name == self.__class__.ins_config.private_prompt_character:
                self.__class__._private_train = {
                    "role": "system",
                    "content": prompt.text,
                }
                break
        else:
            logger.warning(
                f"没有找到名称为 {self.__class__.ins_config.private_prompt_character} 的私聊提示词，将使用default.txt！"
            )
            self.__class__._private_train = {
                "role": "system",
                "content": next(
                    i for i in self.prompts.private if i.name == "default"
                ).text,
            }

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

    def reg_config(self, key: str, default_value=None):
        """
        注册配置项

        :param key: 配置项的名称

        """
        return self.register_config(key, default_value)

    def reg_model_config(self, key: str, default_value=None):
        """
        注册模型配置项

        :param key: 配置项的名称

        """
        if default_value is None:
            default_value = "null"
        if key not in self.ins_config.default_preset.extra:
            self.ins_config.default_preset.extra.setdefault(key, default_value)
        for model, name in self.models:
            model.extra.setdefault(key, default_value)
            model.save(self.custom_models_dir / f"{name}.json")
