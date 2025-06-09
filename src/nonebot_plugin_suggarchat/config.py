import copy
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import nonebot_plugin_localstore as store
import tomli
import tomli_w
from dotenv import load_dotenv
from nonebot import logger
from pydantic import BaseModel

__KERNEL_VERSION__ = "unknow"

# 保留为其他插件提供的引用

# 配置目录
CONFIG_DIR: Path = store.get_plugin_config_dir()
DATA_DIR: Path = store.get_plugin_data_dir()

# 加载Dotenv
load_dotenv()


def replace_env_vars(data: dict | list | str) -> dict | list | str:
    """递归替换环境变量占位符，但不修改原始数据"""
    data_copy = copy.deepcopy(data)  # 创建原始数据的深拷贝[4,5](@ref)
    if isinstance(data_copy, dict):
        for key, value in data_copy.items():
            data_copy[key] = replace_env_vars(value)
    elif isinstance(data_copy, list):
        for i in range(len(data_copy)):
            data_copy[i] = replace_env_vars(data_copy[i])
    elif isinstance(data_copy, str):
        pattern = r"\$\{(\w+)\}"

        def replacer(match):
            var_name = match.group(1)
            return os.getenv(var_name, "")  # 若未设置环境变量，返回空字符串

        data_copy = re.sub(pattern, replacer, data_copy)
    return data_copy


class ModelPreset(BaseModel, extra="allow"):
    model: str = ""
    name: str = "default"
    base_url: str = ""
    api_key: str = ""
    protocol: str = "__main__"
    thought_chain_model: bool = False
    multimodal: bool = False

    @classmethod
    def load(cls, path: Path):
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        return cls()  # 返回默认值

    def save(self, path: Path):
        with path.open("w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=4, ensure_ascii=False)

    def __getattr__(self, item) -> str:
        if item in self.__dict__:
            return self.__dict__[item]
        if self.__pydantic_extra__ and item in self.__pydantic_extra__:
            return self.__pydantic_extra__[item]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{item}'"
        )


class Config(BaseModel, extra="allow"):
    preset: str = ModelPreset().name
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    protocol: str = "__main__"
    thought_chain_model: bool = False
    multimodal: bool = False
    memory_lenth_limit: int = 50
    enable: bool = False
    fake_people: bool = False
    global_fake_people: bool = False
    probability: float = 1e-2
    keyword: str = "at"
    nature_chat_style: bool = True
    poke_reply: bool = True
    enable_group_chat: bool = True
    enable_private_chat: bool = True
    allow_custom_prompt: bool = True
    allow_send_to_admin: bool = False
    use_base_prompt: bool = True
    admin_group: int = 0
    admins: list[int] = []
    stream: bool = False
    max_tokens: int = 100
    tokens_count_mode: str = "bpe"
    session_max_tokens: int = 5000
    enable_tokens_limit: bool = True
    llm_timeout: int = 60
    say_after_self_msg_be_deleted: bool = False
    group_added_msg: str = "你好，我是Suggar，欢迎使用SuggarAI聊天机器人..."
    send_msg_after_be_invited: bool = False
    parse_segments: bool = True
    matcher_function: bool = True
    session_control: bool = False
    session_control_time: int = 60
    session_control_history: int = 10
    group_prompt_character: str = "default"
    private_prompt_character: str = "default"
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


    @classmethod
    def load_from_toml(cls, path: Path) -> "Config":
        """从 TOML 文件加载配置"""
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data: dict[str, Any] = tomli.load(f)
        # 自动更新配置文件
        current_config = cls().model_dump()
        updated_config = {**current_config, **data}
        config_instance = cls(**updated_config)
        config_instance.validate()  # 校验配置
        return config_instance

    def validate(self):
        """校验配置"""
        if self.max_tokens <= 0:
            raise ValueError("max_tokens必须大于零!")
        if self.llm_timeout <= 0:
            raise ValueError("LLM请求超时时间必须大于零！")
        if self.session_max_tokens <= 0:
            raise ValueError("上下文最大Tokens限制必须大于零！")
        if self.session_control:
            if self.session_control_history <= 0:
                raise ValueError("会话历史最大值不能为0！")
            if self.session_control_time <= 0:
                raise ValueError("会话生命周期时间不能小于零！")

    @classmethod
    def load_from_json(cls, path: Path) -> "Config":
        """从 JSON 文件加载配置"""
        with path.open("r", encoding="utf-8") as f:
            data: dict = json.load(f)
        return cls(**data)

    def save_to_toml(self, path: Path):
        """保存配置到 TOML 文件"""
        with path.open("wb") as f:
            tomli_w.dump(self.model_dump(), f)

    def __getattr__(self, item) -> str:
        if item in self.__dict__:
            return self.__dict__[item]
        if self.__pydantic_extra__ and item in self.__pydantic_extra__:
            return self.__pydantic_extra__[item]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{item}'"
        )


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
            with (path / f"{prompt.name}.txt").open("w", encoding="utf-8") as f:
                f.write(prompt.text)

    def save_private(self, path: Path):
        """保存私聊提示词"""
        for prompt in self.private:
            with (path / f"{prompt.name}.txt").open("w", encoding="utf-8") as f:
                f.write(prompt.text)


@dataclass
class ConfigManager:
    config_dir: Path = CONFIG_DIR
    data_dir: Path = DATA_DIR
    bot_config_dir: Path | None = None
    bot_data_dir: Path | None = None
    group_memory: Path = data_dir / "group"
    private_memory: Path = data_dir / "private"
    json_config: Path = config_dir / "config.json"  # 兼容旧版本
    toml_config: Path = config_dir / "config.toml"
    group_prompt: Path = config_dir / "prompt_group.txt"  # 兼容旧版本
    private_prompt: Path = config_dir / "prompt_private.txt"  # 兼容旧版本
    private_prompts: Path = config_dir / "private_prompts"
    group_prompts: Path = config_dir / "group_prompts"
    custom_models_dir: Path = config_dir / "models"
    _private_train: dict = field(default_factory=dict)
    _group_train: dict = field(default_factory=dict)
    # config: Config = field(default_factory=Config)
    ins_config: Config = field(default_factory=Config)
    models: list[tuple[ModelPreset, str]] = field(default_factory=list)
    prompts: Prompts = field(default_factory=Prompts)

    @property
    def config(self) -> Config:
        conf_data: dict[str, Any] = self.ins_config.model_dump()
        result = replace_env_vars(conf_data)
        if not isinstance(result, dict):
            raise TypeError("Expected replace_env_vars to return a dict")
        return Config(**result)

    def load(self, bot_id: str):
        """_初始化配置目录_

        Args:
            bot_id (str): _Bot的qq号_
        """
        self.bot_config_dir = self.config_dir / bot_id
        self.bot_data_dir = self.data_dir / bot_id
        os.makedirs(self.bot_config_dir, exist_ok=True)
        os.makedirs(self.bot_data_dir, exist_ok=True)

        self.group_memory = self.bot_data_dir / "group"
        self.private_memory = self.bot_data_dir / "private"
        os.makedirs(self.group_memory, exist_ok=True)
        os.makedirs(self.private_memory, exist_ok=True)

        self.json_config = self.bot_config_dir / "config.json"
        self.toml_config = self.bot_config_dir / "config.toml"
        self.group_prompt = self.bot_config_dir / "prompt_group.txt"
        self.private_prompt = self.bot_config_dir / "prompt_private.txt"
        self.private_prompts = self.bot_config_dir / "private_prompts"
        self.group_prompts = self.bot_config_dir / "group_prompts"
        os.makedirs(self.private_prompts, exist_ok=True)
        os.makedirs(self.group_prompts, exist_ok=True)
        self.custom_models_dir = self.bot_config_dir / "models"
        os.makedirs(self.custom_models_dir, exist_ok=True)

        prompt_private_temp: str = ""
        prompt_group_temp: str = ""

        # 处理配置文件转换
        if self.json_config.exists():
            with self.json_config.open("r", encoding="utf-8") as f:
                data: dict = json.load(f)

            # 判断是否有抛弃的字段需要转移
            if "private_train" in data:
                prompt_old = data["private_train"]["content"]
                if not (self.private_prompts / "default.txt").is_file():
                    with (self.private_prompts / "default.txt").open(
                        "w", encoding="utf-8"
                    ) as f:
                        f.write(prompt_old)
                del data["private_train"]
            if "group_train" in data:
                prompt_old = data["group_train"]["content"]
                if not (self.group_prompts / "default.txt").is_file():
                    with (self.group_prompts / "default.txt").open(
                        "w", encoding="utf-8"
                    ) as f:
                        f.write(prompt_old)
                del data["group_train"]

            Config(**data).save_to_toml(self.toml_config)
            os.rename(self.json_config, self.json_config.with_suffix(".old"))
            self.ins_config = Config.load_from_toml(self.toml_config)

        elif self.toml_config.exists():
            self.ins_config = Config.load_from_toml(self.toml_config)

        else:
            self.ins_config = Config()
            self.ins_config.save_to_toml(self.toml_config)

        def config_fix(config: Config) -> Config:
            data = config.model_dump()
            if "open_ai_base_url" in data:
                data["base_url"] = data["open_ai_base_url"]
                del data["open_ai_base_url"]
            if "open_ai_api_key" in data:
                data["api_key"] = data["open_ai_api_key"]
                del data["open_ai_api_key"]
            if config.preset == "__main__":
                data["preset"] = "default"
            return Config(**data)

        self.ins_config = config_fix(self.ins_config)
        self.ins_config.save_to_toml(self.toml_config)

        # private_train
        if self.private_prompt.is_file():
            with self.private_prompt.open("r", encoding="utf-8") as f:
                prompt_private_temp = f.read()
            os.rename(self.private_prompt, self.private_prompt.with_suffix(".old"))
        if not (self.private_prompts / "default.txt").is_file():
            with (self.private_prompts / "default.txt").open(
                "w", encoding="utf-8"
            ) as f:
                f.write(prompt_private_temp)

        # group_train
        if self.group_prompt.is_file():
            with self.group_prompt.open("r", encoding="utf-8") as f:
                prompt_group_temp = f.read()
            os.rename(self.group_prompt, self.group_prompt.with_suffix(".old"))
        if not (self.group_prompts / "default.txt").is_file():
            with (self.group_prompts / "default.txt").open("w", encoding="utf-8") as f:
                f.write(prompt_group_temp)

        self.get_models(cache=False)
        self.get_prompts(cache=False)
        self.load_prompt()

    def get_models(self, cache: bool = False) -> list[ModelPreset]:
        """获取模型列表"""
        if cache and self.models:
            return [model[0] for model in self.models]
        self.models.clear()  # 清空模型列表

        for file in self.custom_models_dir.glob("*.json"):
            model_data = ModelPreset.load(file).model_dump()
            preset_data = replace_env_vars(model_data)
            if not isinstance(preset_data, dict):
                raise TypeError("Expected replace_env_vars to return a dict")
            model_preset = ModelPreset(**preset_data)
            self.models.append((model_preset, file.stem))

        return [model[0] for model in self.models]

    def get_preset(
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
            p_dict = self.config.model_dump()
            for k, v in self.ins_config.model_dump().items():
                if k in p_dict:
                    p_dict[k] = v

            return ModelPreset(**p_dict)
        for model in self.get_models():
            if model.name == preset:
                return model
        if fix:
            logger.error(f"预设 {self.ins_config.preset} 未找到，重置为主配置")
            self.ins_config.preset = "default"
            self.save_config()
        return self.get_preset("default", fix, cache)

    def get_prompts(self, cache: bool = False) -> Prompts:
        """获取提示词"""
        if cache and self.prompts:
            return self.prompts
        self.prompts = Prompts()
        for file in self.private_prompts.glob("*.txt"):
            with file.open("r", encoding="utf-8") as f:
                prompt = f.read()
            self.prompts.private.append(Prompt(prompt, file.stem))
        for file in self.group_prompts.glob("*.txt"):
            with file.open("r", encoding="utf-8") as f:
                prompt = f.read()
            self.prompts.group.append(Prompt(prompt, file.stem))
        if not self.prompts.private:
            self.prompts.private.append(Prompt("", "default"))
        if not self.prompts.group:
            self.prompts.group.append(Prompt("", "default"))

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

    def load_prompt(self):
        """加载提示词，匹配预设"""
        for prompt in self.prompts.group:
            if prompt.name == self.ins_config.group_prompt_character:
                self._group_train = {"role": "system", "content": prompt.text}
                break
        else:
            raise ValueError(
                f"没有找到名称为 {self.ins_config.group_prompt_character} 的群组提示词"
            )
        for prompt in self.prompts.private:
            if prompt.name == self.ins_config.private_prompt_character:
                self._private_train = {"role": "system", "content": prompt.text}
                break
        else:
            raise ValueError(
                f"没有找到名称为 {self.ins_config.private_prompt_character} 的私聊提示词"
            )

    def reload_config(self):
        """重加载配置"""
        if self.bot_config_dir:
            self.load(self.bot_config_dir.name)
        else:
            raise RuntimeWarning("未初始化 Bot 配置")

    def save_config(self):
        """保存配置"""
        if self.ins_config:
            self.ins_config.save_to_toml(self.toml_config)

    def set_config(self, key: str, value: str):
        """
        设置配置

        :param key: 配置项的名称
        :param value: 配置项的值

        :raises KeyError: 如果配置项不存在，则抛出异常
        """
        if hasattr(self.ins_config, key):
            setattr(self.ins_config, key, value)
            self.save_config()
        else:
            raise KeyError(f"配置项 {key} 不存在")

    def register_config(self, key: str, default_value=None):
        """
        注册配置项

        :param key: 配置项的名称

        """
        if default_value is None:
            default_value = "null"
        if not hasattr(self.ins_config, key):
            setattr(self.ins_config, key, default_value)
        self.save_config()

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
        for model in self.models:
            if not hasattr(model[0], key):
                setattr(model[0], key, default_value)
            model[0].save(self.custom_models_dir / f"{model[1]}.json")


config_manager = ConfigManager()
