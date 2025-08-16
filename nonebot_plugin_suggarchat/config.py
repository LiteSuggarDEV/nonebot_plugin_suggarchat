import asyncio
import copy
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import aiofiles
import nonebot_plugin_localstore as store
import tomli
import tomli_w
from nonebot import get_driver, logger
from pydantic import BaseModel
from watchfiles import awatch

__kernel_version__ = "unknow"

# 保留为其他插件提供的引用

# 配置目录
CONFIG_DIR: Path = store.get_plugin_config_dir()
driver = get_driver()
nb_config = driver.config


def replace_env_vars(
    data: dict[str, Any] | list[Any] | str | Any,
) -> dict[str, Any] | list[Any] | str | Any:
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


class ExtraModelPreset(BaseModel, extra="allow"):
    def __getattr__(self, item: str) -> str:
        if item in self.__dict__:
            return self.__dict__[item]
        if self.__pydantic_extra__ and item in self.__pydantic_extra__:
            return self.__pydantic_extra__[item]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{item}'"
        )


class ModelPreset(BaseModel):
    model: str = ""
    name: str = "default"
    base_url: str = ""
    api_key: str = ""
    protocol: str = "__main__"
    thought_chain_model: bool = False
    multimodal: bool = False
    extra: ExtraModelPreset = ExtraModelPreset()

    @classmethod
    def load(cls, path: Path):
        if path.exists():
            with path.open(
                "r",
            ) as f:
                data = json.load(f)
            return cls.model_validate(data)
        return cls()  # 返回默认值

    def save(self, path: Path):
        with path.open("w", encoding="u8") as f:
            json.dump(self.model_dump(), f, indent=4, ensure_ascii=False)


class ToolsConfig(BaseModel):
    enable_tools: bool = True
    enable_report: bool = True
    report_then_block: bool = True
    require_tools: bool = False


class SessionConfig(BaseModel):
    session_control: bool = False
    session_control_time: int = 60
    session_control_history: int = 10
    session_max_tokens: int = 5000


class AutoReplyConfig(BaseModel):
    enable: bool = False
    global_enable: bool = False
    probability: float = 1e-2
    keywords: list[str] = ["at"]


class FunctionConfig(BaseModel):
    synthesize_forward_message: bool = True
    nature_chat_style: bool = True
    poke_reply: bool = True
    enable_group_chat: bool = True
    enable_private_chat: bool = True
    allow_custom_prompt: bool = True
    use_user_nickname: bool = False  # 使用用户昵称而不是群内昵称（仅群内）


class PresetSwitch(BaseModel):
    backup_preset_list: list[str] = []


class CookieModel(BaseModel):
    cookie: str = ""
    enable_cookie: bool = False
    block_msg: list[str] = [
        "喵呜～这个问题有点超出Suggar的理解范围啦(歪头)",
        "（耳朵耷拉）这个...Suggar暂时回答不了呢＞﹏＜",
        "喵？这个话题好像不太适合讨论呢～",
        "（玩手指）突然有点不知道该怎么回答喵...",
        "唔...这个方向Suggar还没学会呢(脸红)",
        "喵～我们聊点别的开心事好不好？",
        "（眨眨眼）这个话题好像被魔法封印了喵！",
        "啊啦～Suggar的知识库这里刚好是空白页呢",
        "（竖起尾巴）检测到未知领域警报喵！",
        "喵呜...这个问题让Suggar的CPU过热啦(＞﹏＜)",
        "（躲到主人身后）这个...好难回答喵...",
        "叮！话题转换卡生效～我们聊点别的喵？",
        "（猫耳抖动）信号接收不良喵...换个频道好吗？",
        "Suggar的喵星语翻译器好像故障了...",
        "（转圈圈）这个问题转晕Suggar啦～",
        "喵？刚才风太大没听清...主人再说点别的？",
        "（翻书状）Suggar的百科全书缺了这一页喵...",
        "啊呀～这个话题被猫毛盖住了看不见喵！",
        "（举起爪子投降）这个领域Suggar认输喵～",
        "检测到话题黑洞...紧急逃离喵！(＞人＜)",
        "（尾巴打结）这个问题好复杂喵...解不开啦",
        "喵呜～Suggar的小脑袋暂时处理不了这个呢",
        "（捂耳朵）不听不听～换话题喵！",
        "这个...Suggar的猫娘执照没覆盖这个领域喵",
        "叮咚！您的话题已进入Suggar的认知盲区～",
        "（装傻）喵？Suggar突然失忆了...",
        "警报！话题超出Suggar的可爱范围～",
        "（数爪子）1、2、3...啊数错了！换个话题喵？",
        "这个方向...Suggar的导航仪失灵了喵(´･_･`)",
        "喵～话题防火墙启动！我们聊点安全的？",
        "（转笔状）这个问题...考试不考喵！跳过～",
        "啊啦～Suggar的答案库正在升级中...",
        "（做鬼脸）略略略～不回答这个喵！",
        "检测到超纲内容...启动保护模式喵！",
        "（抱头蹲防）问题太难了喵！投降～",
        "喵呜...这个秘密要等Suggar升级才能解锁",
        "（举白旗）这个话题Suggar放弃思考～",
        "叮！触发Suggar的防宕机保护机制喵",
        "（装睡）Zzz...突然好困喵...",
        "喵？Suggar的思维天线接收不良...",
        "（画圈圈）这个问题在Suggar的知识圈外...",
        "啊呀～话题偏离主轨道喵！紧急修正～",
        "（翻跟头）问题太难度把Suggar绊倒了喵！",
        "这个...需要猫娘高级权限才能解锁喵～",
        "（擦汗）Suggar的处理器过载了...",
        "喵呜～问题太深奥会卡住Suggar的猫脑",
        "（变魔术状）看！话题消失魔术成功喵～",
    ]


class ExtraConfig(BaseModel, extra="allow"):
    def __getattr__(self, item: str) -> str:
        if item in self.__dict__:
            return self.__dict__[item]
        if self.__pydantic_extra__ and item in self.__pydantic_extra__:
            return self.__pydantic_extra__[item]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{item}'"
        )


class ExtendConfig(BaseModel):
    say_after_self_msg_be_deleted: bool = False
    group_added_msg: str = "你好，我是Suggar，欢迎使用SuggarAI聊天机器人..."
    send_msg_after_be_invited: bool = False
    after_deleted_say_what: list[str] = [
        "Suggar说错什么话了吗～下次我会注意的呢～",
        "抱歉啦，不小心说错啦～",
        "嘿，发生什么事啦？我",
        "唔，我是不是说错了什么？",
        "纠错时间到，如果我说错了请告诉我！",
        "发生了什么？我刚刚没听清楚呢~",
        "我会记住的，绝对不再说错话啦~",
        "哦，看来我又犯错了，真是不好意思！",
        "哈哈，看来我得多读书了~",
        "哎呀，真是个小口误，别在意哦~",
        "Suggar苯苯的，偶尔说错话很正常嘛！",
        "哎呀，我也有尴尬的时候呢~",
        "希望我能继续为你提供帮助，不要太在意我的小错误哦！",
    ]


class AdminConfig(BaseModel):
    allow_send_to_admin: bool = False
    admin_group: int = 0
    admins: list[int] = []


class UsageLimitConfig(BaseModel):
    enable_usage_limit: bool = False
    group_daily_limit: int = 100  # 每个群每天的使用次数限制(-1为不限制)
    user_daily_limit: int = 100  # 每个用户每天的使用次数限制(-1为不限制)
    total_daily_limit: int = 1500  # 总使用次数限制(-1为不限制)


class LLM_Config(BaseModel):
    tools: ToolsConfig = ToolsConfig()
    stream: bool = False
    memory_lenth_limit: int = 50
    use_base_prompt: bool = True
    max_tokens: int = 100
    tokens_count_mode: Literal["word", "bpe", "char"] = "bpe"
    enable_tokens_limit: bool = True
    llm_timeout: int = 60
    auto_retry: bool = True
    max_retries: int = 3


class Config(BaseModel):
    preset_extension: PresetSwitch = PresetSwitch()
    default_preset: ModelPreset = ModelPreset()
    session: SessionConfig = SessionConfig()
    cookies: CookieModel = CookieModel()
    autoreply: AutoReplyConfig = AutoReplyConfig()
    function: FunctionConfig = FunctionConfig()
    extended: ExtendConfig = ExtendConfig()
    admin: AdminConfig = AdminConfig()
    llm_config: LLM_Config = LLM_Config()
    extra: ExtraConfig = ExtraConfig()
    usage_limit: UsageLimitConfig = UsageLimitConfig()
    enable: bool = False
    parse_segments: bool = True
    matcher_function: bool = True
    preset: str = "default"
    group_prompt_character: str = "default"
    private_prompt_character: str = "default"

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
    def load_from_json(cls, path: Path) -> "Config":
        """从 JSON 文件加载配置"""
        with path.open(
            "r",
        ) as f:
            data: dict[str, Any] = json.load(f)
        return cls.model_validate(data)

    def save_to_toml(self, path: Path):
        """保存配置到 TOML 文件"""
        with path.open("wb") as f:
            tomli_w.dump(self.model_dump(), f)


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


@dataclass
class ConfigManager:
    config_dir: Path = CONFIG_DIR
    _initialized = False

    toml_config: Path = config_dir / "config.toml"

    private_prompts: Path = config_dir / "private_prompts"
    group_prompts: Path = config_dir / "group_prompts"
    custom_models_dir: Path = config_dir / "models"
    _private_train: dict[str, Any] = field(default_factory=dict)
    _group_train: dict[str, Any] = field(default_factory=dict)
    ins_config: Config = field(default_factory=Config)
    models: list[tuple[ModelPreset, str]] = field(default_factory=list)
    prompts: Prompts = field(default_factory=Prompts)

    @property
    def config(self) -> Config:
        conf_data: dict[str, Any] = self.ins_config.model_dump()
        result = replace_env_vars(conf_data)
        if not isinstance(result, dict):
            raise TypeError("Expected replace_env_vars to return a dict")
        return Config.model_validate(result)

    async def load(self):
        """_初始化配置目录_"""
        logger.info("正在初始化存储目录...")
        logger.debug(f"配置目录: {self.config_dir}")
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.private_prompts, exist_ok=True)
        os.makedirs(self.group_prompts, exist_ok=True)
        os.makedirs(self.custom_models_dir, exist_ok=True)

        if self.toml_config.exists():
            self.ins_config = Config.load_from_toml(self.toml_config)

        else:
            self.ins_config = Config()
            self.ins_config.save_to_toml(self.toml_config)

        self.ins_config.save_to_toml(self.toml_config)
        self.validate_presets()
        await self.get_all_presets(cache=False)
        await self.get_prompts(cache=False)
        await self.load_prompt()

    def init_watch(self):
        if not self._initialized:
            self._tasks = []
            self._tasks.append(asyncio.create_task(self._watch_config_dir()))
            self._initialized = True

    async def _watch_config_dir(self):
        async for changes in awatch(self.config_dir):
            if any(path == str(self.toml_config) for _, path in changes):
                logger.info("检测到配置文件更改，正在重新加载配置...")
                try:
                    await self.reload_config()
                except Exception as e:
                    logger.opt(exception=e, colors=True).warning("配置文件重载失败")
            elif any(
                (
                    path.startswith(str(self.group_prompts))
                    or path.startswith(str(self.private_prompts))
                )
                and path.endswith(".txt")
                for _, path in changes
            ):
                logger.info("检测到提示词文件更改，正在重新加载提示词...")
                await self.get_prompts(cache=False, load_only=True)
                await self.load_prompt()
                logger.info("完成。")
            elif any(
                path.startswith(str(self.custom_models_dir)) and path.endswith(".json")
                for _, path in changes
            ):
                logger.info("检测到模型预设文件更改，正在重新加载模型预设...")
                await self.get_all_presets(cache=False)
                logger.info("完成。")

    def validate_presets(self):
        def validate_preset(path: Path):
            try:
                model_data = ModelPreset.load(path)
                model_data.save(path)
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
            return config_manager.config.default_preset
        for model in await self.get_all_presets(cache=cache):
            if model.name == preset:
                return model
        if fix:
            config_manager.ins_config.preset = "default"
            await config_manager.save_config()
        return await self.get_preset("default", fix, cache)

    async def get_prompts(
        self, cache: bool = False, load_only: bool = False
    ) -> Prompts:
        """获取提示词"""
        if cache and self.prompts:
            return self.prompts
        self.prompts = Prompts()
        for file in self.private_prompts.glob("*.txt"):
            async with aiofiles.open(str(file)) as f:
                prompt = await f.read()
            self.prompts.private.append(Prompt(prompt, file.stem))
        for file in self.group_prompts.glob("*.txt"):
            async with aiofiles.open(str(file)) as f:
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
                self._group_train = {"role": "system", "content": prompt.text}
                break
        else:
            self._group_train = {
                "role": "system",
                "content": next(
                    i for i in self.prompts.group if i.name == "default"
                ).text,
            }
            logger.warning(
                f"没有找到名称为 {self.ins_config.group_prompt_character} 的群组提示词，将使用default.txt!"
            )

        for prompt in self.prompts.private:
            if prompt.name == self.ins_config.private_prompt_character:
                self._private_train = {"role": "system", "content": prompt.text}
                break
        else:
            logger.warning(
                f"没有找到名称为 {self.ins_config.private_prompt_character} 的私聊提示词，将使用default.txt！"
            )
            self._private_train = {
                "role": "system",
                "content": next(
                    i for i in self.prompts.private if i.name == "default"
                ).text,
            }

    async def reload(self):
        """重加载所有内容"""

        await self.load()

    async def reload_config(self):
        self.ins_config = Config.load_from_toml(self.toml_config)
        logger.info("重载配置文件")

    async def save_config(self):
        """保存配置"""
        if self.ins_config:
            self.ins_config.save_to_toml(self.toml_config)

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
        if not hasattr(self.ins_config.extra, key):
            setattr(self.ins_config.extra, key, default_value)
            logger.warning(self.ins_config.extra.model_dump_json())
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
        if not hasattr(self.ins_config.default_preset.extra, key):
            setattr(self.ins_config.default_preset.extra, key, default_value)
            self.ins_config.save_to_toml(self.toml_config)
        for model, name in self.models:
            if not hasattr(model.extra, key):
                setattr(model.extra, key, default_value)
            model.save(self.custom_models_dir / f"{name}.json")


config_manager = ConfigManager()
