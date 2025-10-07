import re
from functools import lru_cache
from typing import Literal

import jieba

jieba.initialize()


@lru_cache(maxsize=2048)
def hybrid_token_count(
    text: str,
    mode: Literal["word", "bpe", "char"] = "word",
    truncate_mode: Literal["head", "tail", "middle"] = "head",
) -> int:
    """
    计算中英文混合文本的 Token 数量，支持词、子词、字符模式

    Args:
        text: 输入文本
        mode: 分词模式 ['char'(字符级), 'word'(词语级), 'bpe'(混合模式)]，默认bpe
        truncate_mode: 截断模式 ['head'(头部截断), 'tail'(尾部截断), 'middle'(中间截断)]，默认head

    Returns:
        int: token数量
    """
    return Tokenizer(mode=mode, truncate_mode=truncate_mode).count_tokens(text=text)


class Tokenizer:
    """通用文本分词器"""

    def __init__(
        self,
        max_tokens: int = 2048,
        mode: Literal["word", "bpe", "char"] = "bpe",
        truncate_mode: Literal["head", "tail", "middle"] = "head",
    ):
        """
        初始化分词器

        :param max_tokens: 最大token限制，默认2048（仅在Word模式下生效）
        :param mode: 分词模式 ['char'(字符级), 'word'(词语级), 'bpe'(混合模式)]，默认bpe
        :param truncate_mode: 截断模式 ['head'(头部截断), 'tail'(尾部截断), 'middle'(中间截断)]，默认head
        """
        self.max_tokens = max_tokens
        self.mode = mode
        self.truncate_mode = truncate_mode
        self._word_pattern = re.compile(r"\w+|[^\w\s]")  # 匹配单词或标点符号

    def tokenize(self, text: str) -> list[str]:
        """执行分词操作，返回token列表

        Args:
            text: 输入文本

        Returns:
            List[str]: token列表
        """
        if self.mode == "char":
            return list(text)

        # 中英文混合分词策略
        tokens = []
        for chunk in re.findall(self._word_pattern, text):
            if chunk.strip() == "":
                continue

            if self._is_english(chunk):
                tokens.extend(chunk.split())
            else:
                tokens.extend(jieba.lcut(chunk))

        return tokens[: self.max_tokens] if self.mode == "word" else tokens

    def truncate(self, tokens: list[str]) -> list[str]:
        """执行token截断操作

        Args:
            tokens: token列表

        Returns:
            List[str]: 截断后的token列表
        """
        if len(tokens) <= self.max_tokens:
            return tokens

        if self.truncate_mode == "head":
            return tokens[-self.max_tokens :]
        elif self.truncate_mode == "tail":
            return tokens[: self.max_tokens]
        else:  # middle模式保留首尾
            head_len = self.max_tokens // 2
            tail_len = self.max_tokens - head_len
            return tokens[:head_len] + tokens[-tail_len:]

    def count_tokens(self, text: str) -> int:
        """统计文本token数量

        Args:
            text: 输入文本

        Returns:
            int: token数量
        """
        return len(self.tokenize(text))

    def _is_english(self, text: str) -> bool:
        """判断是否为英文文本

        Args:
            text: 输入文本

        Returns:
            bool: 是否为英文
        """
        return all(ord(c) < 128 for c in text)
