import copy
from datetime import datetime as datetime
import json
import os
from pathlib import Path
import re

import chardet
import jieba
import nonebot
from nonebot.adapters.onebot.v11 import (
    Bot,
    Event,
    GroupMessageEvent,
    Message,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from nonebot.log import logger
import pytz

from .conf import (
    get_config_dir,
    get_config_file_path,
    get_custom_models_dir,
    get_group_memory_dir,
    get_group_prompt_path,
    get_private_memory_dir,
    get_private_prompt_path,
)


__base_group_prompt__ = """你在纯文本环境工作，不允许使用MarkDown回复，我会提供聊天记录，你可以从这里面获取一些关键信息，比如时间与用户身份（e.g.: [管理员/群主/自己/群员][YYYY-MM-DD weekday hh:mm:ss AM/PM][昵称（QQ号）]说:<内容>），但是请不要以这个格式回复。对于消息上报我给你的有几个类型，除了文本还有,\\（戳一戳消息）\\：就是QQ的戳一戳消息是戳一戳了你，而不是我，请参与讨论。交流时不同话题尽量不使用相似句式回复，用户与你交谈的信息在<内容>。"""
__base_private_prompt__ = """你在纯文本环境工作，不允许使用MarkDown回复，我会提供聊天记录，你可以从这里面获取一些关键信息，比如时间与用户身份（e.g.: [日期 时间]昵称（QQ：123456）说：消息 ），但是请不要以这个格式回复。对于消息上报我给你的有几个类型，除了文本还有,\\（戳一戳消息）\\：就是QQ的戳一戳消息，是戳一戳了你，而不是我，请参与讨论。交流时不同话题尽量不使用相似句式回复，现在你在聊群内工作！，用户与你交谈的信息在<内容>"""
__default_model_conf__: dict[str, Any] = {
    "model": "auto",
    "name": "",
    "base_url": "",
    "api_key": "",
    # "tokens_count_mode": "bpe",  # 上下文tokens 计算模式，可选 'word'(词，较大误差), 'bpe'(子词，最精准), 'char'(字符，不推荐)
    # "session_max_tokens": 5000,  # 上下文长度限制，单位为tokens（可能有+-15%左右误差）
    # "enable_tokens_limit": True,  # 是否启用上下文长度限制，如果启用，则上下文长度将不会超过session_max_tokens
    "protocol": "__main__",
}
__default_config__ = {
    "preset": "__main__",
    "memory_lenth_limit": 50,
    "enable": False,
    "fake_people": False,  # 是否启用无人触发自动回复
    "probability": 1e-2,  # 无人触发自动回复概率
    "keyword": "at",  # 触发bot对话关键词,at为to_me,其他为startwith
    "nature_chat_style": True,  # 是否启用更加自然的对话风格(使用Jieba分词+回复输出)
    "poke_reply": True,
    "enable_group_chat": True,
    "enable_private_chat": True,
    "allow_custom_prompt": True,
    "allow_send_to_admin": False,
    "use_base_prompt": True,
    "admin_group": 0,
    "admins": [],
    "open_ai_base_url": "",
    "open_ai_api_key": "",
    "stream": False,
    "max_tokens": 100,  # LLM生成的最大tokens数量，单位为tokens。
    "tokens_count_mode": "bpe",  # 上下文tokens 计算模式，可选 'word'(词，较大误差), 'bpe'(子词，最精准), 'char'(字符，不推荐)
    "session_max_tokens": 5000,  # 上下文长度限制，单位为tokens（可能有+-15%左右误差）
    "enable_tokens_limit": True,  # 是否启用上下文长度限制，如果启用，则上下文长度将不会超过session_max_tokens
    "model": "auto",
    "llm_timeout": 60,  # LLM的请求超时时间，单位为秒。
    "say_after_self_msg_be_deleted": False,
    "group_added_msg": "你好，我是Suggar，欢迎使用Suggar的AI聊天机器人，你可以向我提问任何问题，我会尽力回答你的问题，如果你需要帮助，你可以向我发送“帮助”",
    "send_msg_after_be_invited": False,
    "after_deleted_say_what": [
        "Suggar说错什么话了吗～下次我会注意的呢～",
        "抱歉啦，不小心说错啦～",
        "嘿，发生什么事啦？我",
        "唔，我是不是说错了什么？",
        "纠错时间到，如果我说错了请告诉我！",
        "发生了什么？我刚刚没听清楚呢~",
        "我能帮你做点什么吗？不小心说错话了让我变得不那么尴尬~",
        "我会记住的，绝对不再说错话啦~",
        "哦，看来我又犯错了，真是不好意思！",
        "哈哈，看来我得多读书了~",
        "哎呀，真是个小口误，别在意哦~",
        "Suggar苯苯的，偶尔说错话很正常嘛！",
        "哎呀，我也有尴尬的时候呢~",
        "希望我能继续为你提供帮助，不要太在意我的小错误哦！",
    ],
    "parse_segments": True,
    "protocol": "__main__",
    "matcher_function": True,  # 启用matcher,当这一项启用,SuggaeMatcher将会运行。
    # 启用会话控制机制（根据设定的会话时间差自动裁切上下文，如果和上一次聊天时间超过预设时间间隔，就裁切上下文，并询问用户是否继续上一次对话。）
    "session_control": False,
    "session_control_time": 60,  # 预设的射时间间隔，单位分钟，默认60min
    "session_control_history": 10,  # 储存的会话历史长度最多几条，默认10条
}


def format_datetime_timestamp(time: int) -> str:
    now = datetime.fromtimestamp(time)

    # 格式化日期、星期和时间
    formatted_date = now.strftime("%Y-%m-%d")
    formatted_weekday = now.strftime("%A")
    formatted_time = now.strftime("%I:%M:%S %p")

    # 组合格式化的字符串
    formatted_datetime = f"[{formatted_date} {formatted_weekday} {formatted_time}]"

    return formatted_datetime


def hybrid_token_count(text: str, mode: str = "word") -> int:
    """
    混合中英文的 Token 计算方法（支持词、子词、字符模式）

    :param text: 输入文本
    :param mode: 统计模式，可选 'word'(词), 'bpe'(子词), 'char'(字符)
    :return: Token 数量
    """
    # 分离中英文部分（中文按结巴分词，英文按空格/标点分割）
    chinese_parts = re.findall(r"[\u4e00-\u9fff]+", text)
    non_chinese_parts = re.split(r"([\u4e00-\u9fff]+)", text)

    tokens = []

    # 处理中文部分（精准分词）
    for part in chinese_parts:
        tokens.extend(list(jieba.cut(part, cut_all=False)))  # 精准模式

    # 处理非中文部分（按空格和标点分割）
    for part in non_chinese_parts:
        if not part.strip() or part in chinese_parts:
            continue
        # 按正则匹配英文单词、数字、标点
        if mode == "word":
            tokens.extend(re.findall(r"\b\w+\b|\S", part))
        elif mode == "char":
            tokens.extend(list(part))
        elif mode == "bpe":
            # 简易BPE处理（示例：按2-gram拆分）
            tokens.extend([part[i : i + 2] for i in range(0, len(part), 2)])
        else:
            raise ValueError("Invalid tokens-counting mode")
    return len(tokens)


def split_message_into_chats(text):
    sentence_delimiters = re.compile(
        r'(?<=[a-zA-Z])\.|([。！？!?~]+)[”"’\']*',  # 关键修改：仅匹配字母后的英文句号
        re.UNICODE,
    )

    sentences = []
    start = 0
    for match in sentence_delimiters.finditer(text):
        end = match.end()
        sentence = text[start:end].strip()
        if sentence:
            sentences.append(sentence)
        start = end

    if start < len(text):
        remaining = text[start:].strip()
        if remaining:
            sentences.append(remaining)

    return sentences


def convert_to_utf8(file_path) -> bool:
    file_path = str(file_path)
    # 检测文件编码

    with open(file_path, "rb") as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result["encoding"]
    if encoding is None:
        try:
            with open(file_path) as f:
                contents = f.read()
                if contents.strip() == "":
                    return True
        except Exception:
            logger.warning(f"无法读取文件{file_path}")
            return False
        logger.warning(f"无法检测到编码{file_path}")
        return False

    # 读取原文件并写入UTF-8编码的文件
    with open(file_path, encoding=encoding) as file:
        content = file.read()

    # 以UTF-8编码重新写入文件
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)
    return True


def get_models() -> list:
    models = []
    custom_models_dir = get_custom_models_dir()
    if not Path(custom_models_dir).exists() or not Path(custom_models_dir).is_dir():
        Path.mkdir(custom_models_dir)
    for file in Path(custom_models_dir).glob("*.json"):
        convert_to_utf8(file)
        with open(file, encoding="utf-8") as f:
            model = json.load(f)
            model = update_dict(__default_model_conf__, model)
            models.append(model)
    return models


def update_dict(default: dict, to_update: dict) -> dict:
    """
    递归地更新默认字典，将to_update中的键值对更新到默认字典中
    参数:
    default: dict - 默认字典
    to_update: dict - 要更新的字典
    无返回值
    """
    for key, value in default.items():
        if key not in to_update:
            to_update[key] = value
    return to_update


async def synthesize_message(message: Message, bot: Bot | None = None) -> str:
    content = ""
    for segment in message:
        if segment.type == "text":
            content = content + segment.data["text"]

        elif segment.type == "at":
            content += f"\\（at: @{segment.data.get('name')}(QQ:{segment.data['qq']}))"
        elif segment.type == "forward":
            if bot is None:
                bot: Bot = nonebot.get_bot()
            forward = await bot.get_forward_msg(id=segment.data["id"])
            logger.debug(forward)
            content += (
                " \\（合并转发\n" + await synthesize_forward_message(forward) + "）\\\n"
            )
    return content


def save_config(conf: dict):
    """
    保存配置文件

    参数:
    conf: dict - 配置文件，包含以下键值对{__default_config__}
    """
    config_dir = get_config_dir()
    main_config = get_config_file_path()
    if not Path(config_dir).exists():
        try:
            Path.mkdir(config_dir)
        except:
            pass
        with open(str(main_config), "w", encoding="utf-8") as f:
            json.dump(__default_config__, f, ensure_ascii=False, indent=4)
    with open(str(main_config), "w", encoding="utf-8") as f:
        conf = update_dict(__default_config__, conf)
        json.dump(conf, f, ensure_ascii=False, indent=4)


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


def get_config(no_base_prompt: bool = False) -> dict:
    f"""
    获取配置文件

    Returns:
    dict: 配置文件，包含以下键值对{__default_config__}


    """
    config_dir = get_config_dir()
    main_config = get_config_file_path()
    if (
        (not Path(config_dir).exists() or not Path(config_dir).is_dir())
        or not Path(main_config).exists()
        or not Path(main_config).is_file()
    ):
        logger.info("未找到默认配置文件，已自动创建默认配置文件")
        try:
            Path.mkdir(config_dir)
        except:
            pass
        with open(str(main_config), "w", encoding="utf-8") as f:
            json.dump(__default_config__, f, ensure_ascii=False, indent=4)
    convert_to_utf8(main_config)
    with open(str(main_config), encoding="utf-8") as f:
        conf: dict = json.load(f)
    if not no_base_prompt:
        conf = replace_env_vars(conf)
    conf = update_dict(__default_config__, conf)

    return conf


def get_group_prompt() -> dict:
    config = get_config()
    group_prompt = get_group_prompt_path()
    prompt_old = ""
    if config.get("group_train") != None:
        logger.warning(
            f"配置文件的group_train字段已经弃用，请将其存放在配置文件同级目录的{group_prompt}文件中，我们已自动为您迁移。"
        )
        prompt_old = config["group_train"]["content"]
        del config["group_train"]
        save_config(config)
    if not Path(group_prompt).exists() or not Path(group_prompt).is_file():
        with open(str(group_prompt), "w", encoding="utf-8") as f:
            f.write(prompt_old)
    if convert_to_utf8(str(group_prompt)):
        with open(str(group_prompt), encoding="utf-8") as f:
            prompt = f.read()
        return {"role": "system", "content": __base_group_prompt__ + prompt}
    else:
        raise EncodingWarning(f"提示词文件{group_prompt}编码错误！")


def get_private_prompt() -> dict:
    private_prompt = get_private_prompt_path()
    config = get_config()
    prompt_old = ""
    if config.get("private_train") != None:
        logger.warning(
            f"配置文件的private_train字段已经弃用，请将其存放在{private_prompt}中，我们已自动为您迁移。"
        )
        prompt_old = config["private_train"]["content"]
        del config["private_train"]
        save_config(config)
    if not Path(private_prompt).exists() or not Path(private_prompt).is_file():
        with open(str(private_prompt), "w", encoding="utf-8") as f:
            f.write(prompt_old)
    if convert_to_utf8(str(private_prompt)):
        with open(str(private_prompt), encoding="utf-8") as f:
            prompt = f.read()
        return {"role": "system", "content": __base_private_prompt__ + prompt}
    else:
        raise EncodingWarning(f"{private_prompt}编码错误！")


def get_memory_data(event: Event) -> dict:
    logger.debug(f"获取{event.get_type()} {event.get_session_id()} 的记忆数据")
    """
    根据消息事件获取记忆数据，如果用户或群组的记忆数据不存在，则创建初始数据结构

    参数:
    event: MessageEvent - 消息事件，可以是私聊消息事件或群聊消息事件，通过事件解析获取用户或群组ID

    返回:
    dict - 用户或群组的记忆数据字典
    """
    private_memory = get_private_memory_dir()
    group_memory = get_group_memory_dir()
    # 检查私聊记忆目录是否存在，如果不存在则创建
    if not Path(private_memory).exists() or not Path(private_memory).is_dir():
        Path.mkdir(private_memory)

    # 检查群聊记忆目录是否存在，如果不存在则创建
    if not Path(group_memory).exists() or not Path(group_memory).is_dir():
        Path.mkdir(group_memory)

    # 根据事件类型判断是私聊还是群聊
    if isinstance(event, PrivateMessageEvent):
        # 处理私聊事件
        user_id = event.user_id
        conf_path = Path(private_memory / f"{user_id}.json")
        # 如果私聊记忆数据不存在，则创建初始数据结构
        if not conf_path.exists():
            with open(str(conf_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "id": user_id,
                        "enable": True,
                        "memory": {"messages": []},
                        "full": False,
                    },
                    f,
                    ensure_ascii=True,
                    indent=0,
                )
    elif isinstance(event, GroupMessageEvent):
        # 处理群聊事件
        group_id = event.group_id
        conf_path = Path(group_memory / f"{group_id}.json")
        # 如果群聊记忆数据不存在，则创建初始数据结构
        if not conf_path.exists():
            with open(str(conf_path), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "id": group_id,
                        "enable": True,
                        "memory": {"messages": []},
                        "full": False,
                    },
                    f,
                    ensure_ascii=True,
                    indent=0,
                )
    elif isinstance(event, PokeNotifyEvent):
        if event.group_id:
            group_id = event.group_id
            conf_path = Path(group_memory / f"{group_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": group_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
        else:
            user_id = event.user_id
            conf_path = Path(private_memory / f"{user_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": user_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
    convert_to_utf8(conf_path)
    # 读取并返回记忆数据
    with open(str(conf_path), encoding="utf-8") as f:
        conf = json.load(f)
        logger.debug(f"读取到记忆数据{conf}")
        return conf


def write_memory_data(event: Event, data: dict) -> None:
    logger.debug(f"写入记忆数据{data}")
    logger.debug(f"事件：{type(event)}")
    """
    根据事件类型将数据写入到特定的记忆数据文件中。

    该函数根据传入的事件类型（群组消息事件或用户消息事件），将相应的数据以JSON格式写入到对应的文件中。
    对于群组消息事件，数据被写入到以群组ID命名的文件中；对于用户消息事件，数据被写入到以用户ID命名的文件中。

    参数:
    - event: MessageEvent类型，表示一个消息事件，可以是群组消息事件或用户消息事件。
    - data: dict类型，要写入的数据，以字典形式提供。

    返回值:
    无返回值。
    """
    group_memory = get_group_memory_dir()
    private_memory = get_private_memory_dir()

    # 判断事件是否为群组消息事件
    if isinstance(event, GroupMessageEvent):
        # 获取群组ID，并根据群组ID构造配置文件路径
        group_id = event.group_id
        conf_path = Path(group_memory / f"{group_id}.json")
    elif isinstance(event, PrivateMessageEvent):
        # 获取用户ID，并根据用户ID构造配置文件路径
        user_id = event.user_id
        conf_path = Path(private_memory / f"{user_id}.json")
    elif isinstance(event, PokeNotifyEvent):
        if event.group_id:
            group_id = event.group_id
            conf_path = Path(group_memory / f"{group_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": group_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
        else:
            user_id = event.user_id
            conf_path = Path(private_memory / f"{user_id}.json")
            if not conf_path.exists():
                with open(str(conf_path), "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "id": user_id,
                            "enable": True,
                            "memory": {"messages": []},
                            "full": False,
                        },
                        f,
                        ensure_ascii=True,
                        indent=0,
                    )
    # 打开配置文件路径对应的文件，以写入模式，并确保文件以UTF-8编码
    with open(str(conf_path), "w", encoding="utf-8") as f:
        # 将数据写入到文件中，确保ASCII字符以外的字符也能被正确处理
        json.dump(data, f, ensure_ascii=True)


async def get_friend_info(qq_number: int) -> str:
    bot = nonebot.get_bot()  # 假设只有一个Bot实例运行
    friend_list = await bot.get_friend_list()

    for friend in friend_list:
        if friend["user_id"] == qq_number:
            return friend["nickname"]  # 返回找到的好友的昵称

    return ""


async def get_friend_qq_list():
    bot = nonebot.get_bot()
    friend_list = await bot.get_friend_list()
    friend_qq_list = [friend["user_id"] for friend in friend_list]
    return friend_qq_list


def split_list(lst: list, threshold: int) -> list:
    """
    将列表分割成多个子列表，每个子列表的最大长度不超过threshold。

    :param lst: 原始列表
    :param threshold: 子列表的最大长度
    :return: 分割后的子列表列表
    """
    if len(lst) <= threshold:
        return [lst]

    result = []
    for i in range(0, len(lst), threshold):
        chunk = lst[i : i + threshold]
        result.append(chunk)

    return result


async def get_group_member_qq_numbers(group_id: int) -> list[int]:
    """
    获取指定群组的所有成员QQ号列表

    :param group_id: 群组ID
    :return: 成员QQ号列表
    """
    bot = nonebot.get_bot()  # 获取当前机器人实例
    member_list = await bot.get_group_member_list(group_id=group_id)

    # 提取每个成员的QQ号
    qq_numbers = [member["user_id"] for member in member_list]

    return qq_numbers


async def is_same_day(timestamp1: int, timestamp2: int) -> bool:
    # 将时间戳转换为datetime对象，并只保留日期部分
    date1 = datetime.fromtimestamp(timestamp1).date()
    date2 = datetime.fromtimestamp(timestamp2).date()

    # 比较两个日期是否相同
    return date1 == date2


async def synthesize_forward_message(forward_msg: dict) -> str:
    forw_msg = forward_msg
    # 初始化最终字符串
    result = ""

    # forward_msg 是一个包含多个消息段的字典+列表
    for segment in forw_msg["messages"]:
        nickname = segment["sender"]["nickname"]
        qq = segment["sender"]["user_id"]
        time = f"[{datetime.fromtimestamp(segment['time']).strftime('%Y-%m-%d %I:%M:%S %p')}]"
        result += f"{time}[{nickname}({qq})]说："
        for segments in segment["content"]:
            segments_type = segments["type"]
            if segments_type == "text":
                result += f"{segments['data']['text']}"

            elif segments_type == "at":
                result += f" [@{segments['data']['qq']}]"

        result += "\n"

    return result


def get_current_datetime_timestamp():
    # 获取当前 UTC 时间
    utc_time = datetime.now(pytz.utc)

    # 转换为+8时区的时间
    asia_shanghai = pytz.timezone("Asia/Shanghai")
    now = utc_time.astimezone(asia_shanghai)

    # 格式化日期、星期和时间（24小时制）
    formatted_date = now.strftime("%Y-%m-%d")  # 日期保持原格式[1](@ref)
    formatted_weekday = now.strftime("%A")  # 星期保持完整名称[9](@ref)
    formatted_time = now.strftime("%H:%M:%S")  # 关键修改点：%H 表示24小时制[2,8](@ref)

    # 组合格式化的字符串（移除AM/PM）
    formatted_datetime = f"[{formatted_date} {formatted_weekday} {formatted_time}]"

    return formatted_datetime
