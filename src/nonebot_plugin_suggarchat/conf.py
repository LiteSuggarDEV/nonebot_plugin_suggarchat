import os
from pathlib import Path

from nonebot.adapters.onebot.v11 import Bot


__KERNEL_VERSION__: str = "V1.15.7-Public"
# 获取当前工作目录
current_directory: str = os.getcwd()
config_dir: Path = Path(current_directory) / "config" / "nonebot_plugin_suggarchat"
data_dir: Path = Path(current_directory) / "data" / "nonebot_plugin_suggarchat"
group_memory = data_dir / "group"
private_memory = data_dir / "private"
main_config = config_dir / "config.json"
group_prompt = config_dir / "prompt_group.txt"
private_prompt = config_dir / "prompt_private.txt"
custom_models_dir = config_dir / "models"


def init(bot: Bot):
    global \
        config_dir, \
        data_dir, \
        main_config, \
        group_prompt, \
        private_prompt, \
        custom_models_dir
    config_dir = config_dir / bot.self_id
    data_dir = data_dir / bot.self_id
    os.makedirs(config_dir, exist_ok=True)
    group_memory = data_dir / "group"
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(group_memory, exist_ok=True)
    private_memory = data_dir / "private"
    os.makedirs(private_memory, exist_ok=True)
    main_config = config_dir / "config.json"
    group_prompt = config_dir / "prompt_group.txt"
    private_prompt = config_dir / "prompt_private.txt"
    custom_models_dir = config_dir / "models"


def get_private_memory_dir() -> Path:
    return private_memory


def get_group_memory_dir() -> Path:
    return group_memory


def get_config_dir() -> Path:
    return config_dir


def get_config_file_path() -> Path:
    return main_config


def get_current_directory() -> str:
    return current_directory


def get_custom_models_dir() -> Path:
    return custom_models_dir


def get_private_prompt_path() -> Path:
    return private_prompt


def get_group_prompt_path() -> Path:
    return group_prompt
