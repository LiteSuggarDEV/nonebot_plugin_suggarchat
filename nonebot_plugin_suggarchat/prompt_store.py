"""提示词存储"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiofiles
from nonebot import logger


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
            with (path / f"{prompt.name}.txt").open("w", encoding="u8") as f:
                f.write(prompt.text)

    def save_private(self, path: Path):
        """保存私聊提示词"""
        for prompt in self.private:
            with (path / f"{prompt.name}.txt").open("w", encoding="u8") as f:
                f.write(prompt.text)


class PromptStore:
    """提示词加载与匹配"""

    def __init__(self, private_dir: Path, group_dir: Path):
        self.private_dir = private_dir
        self.group_dir = group_dir
        self.prompts = Prompts()
        self._private_train: dict[str, Any] = {}
        self._group_train: dict[str, Any] = {}

    async def load(self, *, cache: bool = False, load_only: bool = False) -> Prompts:
        """加载提示词文件"""
        if cache and (self.prompts.group or self.prompts.private):
            return self.prompts
        self.prompts = Prompts()
        for file in self.private_dir.glob("*.txt"):
            async with aiofiles.open(file, encoding="utf-8") as f:
                text = await f.read()
            self.prompts.private.append(Prompt(text, file.stem))
        for file in self.group_dir.glob("*.txt"):
            async with aiofiles.open(file, encoding="utf-8") as f:
                text = await f.read()
            self.prompts.group.append(Prompt(text, file.stem))
        if not self.prompts.private:
            self.prompts.private.append(Prompt("", "default"))
        if not self.prompts.group:
            self.prompts.group.append(Prompt("", "default"))
        if not load_only:
            self.prompts.save_private(self.private_dir)
            self.prompts.save_group(self.group_dir)
        return self.prompts

    @staticmethod
    def _pick(prompts: list[Prompt], character: str, label: str) -> dict[str, Any]:
        for prompt in prompts:
            if prompt.name == character:
                return {"role": "system", "content": prompt.text}
        logger.warning(
            f"没有找到名称为 {character} 的{label}提示词，将使用default.txt!"
        )
        fallback = next((p for p in prompts if p.name == "default"), None)
        return {"role": "system", "content": fallback.text if fallback else ""}

    def apply(self, group_character: str, private_character: str) -> None:
        """按预设名匹配当前提示词"""
        self._group_train = self._pick(self.prompts.group, group_character, "群组")
        self._private_train = self._pick(
            self.prompts.private, private_character, "私聊"
        )

    @property
    def private_train(self) -> dict[str, str]:
        """获取私聊提示词"""
        return deepcopy(self._private_train)

    @property
    def group_train(self) -> dict[str, str]:
        """获取群聊提示词"""
        return deepcopy(self._group_train)
