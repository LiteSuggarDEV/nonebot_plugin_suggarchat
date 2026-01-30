from __future__ import annotations

import time
from contextlib import nullcontext
from datetime import datetime
from typing import overload

from nonebot import logger
from nonebot.adapters.onebot.v11 import (
    Event,
)
from nonebot_plugin_orm import AsyncSession, get_session
from pydantic import Field

from .lock import transaction_lock
from .logging import debug_log
from .models import (
    BaseModel,
    MemorySessions,
    SessionMemoryModel,
    get_or_create_data,
)
from .models import (
    MemoryModel as Memory,
)


# TODO: 拆分(提高颗粒度与提升性能)+弃用
class MemoryModel(BaseModel):
    enable: bool = Field(default=True, description="是否启用")
    memory: Memory = Field(default=Memory(), description="记忆")
    sessions: list[SessionMemoryModel] = Field(default_factory=list, description="会话")
    timestamp: float = Field(default=time.time(), description="时间戳")
    fake_people: bool = Field(default=False, description="是否启用假人")
    prompt: str = Field(default="", description="用户自定义提示词")
    usage: int = Field(default=0, description="请求次数")
    input_token_usage: int = Field(default=0, description="token使用量")
    output_token_usage: int = Field(default=0, description="token使用量")

    async def save(
        self,
        event: Event,
        *,
        raise_err: bool = True,
        no_locking: bool = False,
    ) -> None:
        """保存当前记忆数据到文件"""

        session = get_session()

        async with session:
            await write_memory_data(event, self, session, raise_err, no_locking)


@overload
async def get_memory_data(*, user_id: int) -> MemoryModel: ...


@overload
async def get_memory_data(*, group_id: int) -> MemoryModel: ...


@overload
async def get_memory_data(event: Event) -> MemoryModel: ...


async def get_memory_data(
    event: Event | None = None,
    *,
    user_id: int | None = None,
    group_id: int | None = None,
) -> MemoryModel:
    """获取事件对应的记忆数据，如果不存在则创建初始数据"""
    is_group = False
    if (ins_id := (getattr(event, "group_id", None) or group_id)) is not None:
        ins_id = int(ins_id)
        debug_log(f"获取Group{ins_id} 的记忆数据")
        is_group = True
    else:
        ins_id = int(event.get_user_id()) if event else user_id
        debug_log(f"获取用户{ins_id}的记忆数据")
    assert ins_id is not None, "Ins_id is None!"

    debug_log(f"开始获取记忆数据，ins_id: {ins_id}, is_group: {is_group}")
    async with transaction_lock(ins_id, is_group):
        async with get_session() as session:
            group_conf = None
            if is_group:
                debug_log(f"获取群组配置和记忆数据，ins_id: {ins_id}")
                group_conf, memory = await get_or_create_data(
                    session=session,
                    ins_id=ins_id,
                    is_group=is_group,
                )
                debug_log(
                    f"成功获取群组配置: {group_conf.id if group_conf else 'None'}"
                )

            else:
                debug_log(f"获取用户记忆数据，ins_id: {ins_id}")
                memory = await get_or_create_data(session=session, ins_id=ins_id)
                debug_log(f"成功获取用户记忆: {memory.id if memory else 'None'}")
            memory_data = memory.memory_json
            debug_log(f"从数据库获取的记忆数据: {len(memory_data['messages'])} 条消息")

            sessions_data = await MemorySessions.get(session, ins_id, is_group)
            debug_log(f"获取到 {len(sessions_data)} 个会话数据")

            c_memory = Memory.model_validate(memory_data)
            debug_log(f"构建主记忆对象，包含 {len(c_memory.messages)} 条消息")

            sessions = [
                SessionMemoryModel.model_validate(
                    obj={
                        **i.data,
                        "id": i.id,
                    }
                )
                for i in sessions_data
            ]
            debug_log(f"构建会话列表，包含 {len(sessions)} 个会话")

            conf = MemoryModel(
                memory=c_memory,
                sessions=sessions,
                usage=memory.usage_count,
                timestamp=memory.time.timestamp(),
                input_token_usage=memory.input_token_usage,
                output_token_usage=memory.output_token_usage,
            )
            debug_log(
                f"构建MemoryModel完成，usage: {conf.usage}, timestamp: {conf.timestamp}"
            )

            if group_conf:
                conf.enable = group_conf.enable
                conf.fake_people = group_conf.fake_people
                conf.prompt = group_conf.prompt
                debug_log(
                    f"设置群组配置: enable={conf.enable}, fake_people={conf.fake_people}"
                )

            # 检查是否需要重置每日统计
            if (
                datetime.fromtimestamp(conf.timestamp).date().isoformat()
                != datetime.now().date().isoformat()
            ):
                old_usage = conf.usage
                old_input_tokens = conf.input_token_usage
                old_output_tokens = conf.output_token_usage
                conf.usage = 0
                conf.input_token_usage = 0
                conf.output_token_usage = 0
                conf.timestamp = int(datetime.now().timestamp())
                debug_log(
                    f"日期变更，重置统计数据: usage从{old_usage}变为0, "
                    f"input_tokens从{old_input_tokens}变为0, "
                    f"output_tokens从{old_output_tokens}变为0"
                )
                if event:
                    await conf.save(event, no_locking=True)
                    debug_log("因日期变更，已保存重置后的记忆数据")

        debug_log(
            f"完成记忆数据获取，总计 {len(conf.memory.messages)} 条消息，"
            f"{len(conf.sessions)} 个会话"
        )

        return conf


async def write_memory_data(
    event: Event,
    data: MemoryModel,
    session: AsyncSession | None = None,
    raise_err: bool = False,
    no_locking: bool = False,
) -> None:
    """将记忆数据写入对应的文件"""
    session = session or get_session()
    debug_log("开始写入记忆数据")
    debug_log(f"事件类型：{type(event)}")
    debug_log(
        f"记忆数据概览：{len(data.memory.messages)} 条消息，{len(data.sessions)} 个会话"
    )

    is_group = hasattr(event, "group_id")
    ins_id = int(
        getattr(event, "group_id")
        if is_group and getattr(event, "group_id", None)
        else event.get_user_id()
    )

    debug_log(f"识别事件类型：{'群组' if is_group else '用户'}，ID: {ins_id}")
    async with nullcontext() if no_locking else transaction_lock(ins_id, is_group):
        debug_log(
            f"已获取事务锁，开始写入数据库，ins_id: {ins_id}, is_group: {is_group}"
        )
        async with session:
            try:
                debug_log(
                    f"准备获取数据库记录以供更新，ins_id: {ins_id}, is_group: {is_group}"
                )
                group_conf = None
                if is_group:
                    debug_log(f"正在获取群组配置和记忆数据用于更新，ins_id: {ins_id}")
                    group_conf, memory = await get_or_create_data(
                        session=session,
                        ins_id=ins_id,
                        is_group=is_group,
                        for_update=True,
                    )
                    debug_log(f"成功获取群组配置用于更新: {group_conf.id}")

                else:
                    debug_log(f"正在获取用户记忆数据用于更新，ins_id: {ins_id}")
                    memory = await get_or_create_data(
                        session=session,
                        ins_id=ins_id,
                        for_update=True,
                    )
                    debug_log(f"成功获取用户记忆用于更新: {memory.id}")

                debug_log(f"准备更新主记忆数据，消息数量: {len(data.memory.messages)}")
                memory.memory_json = data.memory.model_dump()
                debug_log(f"已更新主记忆数据，包含 {len(data.memory.messages)} 条消息")

                # 统计实际保存的会话数量
                debug_log(f"开始处理会话数据保存，总共有 {len(data.sessions)} 个会话")
                saved_session_count = 0
                for idx, m_session in enumerate(data.sessions):
                    debug_log(
                        f"处理第 {idx + 1}/{len(data.sessions)} 个会话，"
                        f"ID: {getattr(m_session, 'id', 'unknown')}, "
                        f"dirty状态: {getattr(m_session, '__dirty__', 'unknown')}"
                    )

                    # 调用会话的保存方法
                    debug_log(f"准备保存会话 {idx + 1} 到数据库")
                    await m_session.save(
                        ins_id=ins_id, is_group=is_group, arg_session=session
                    )
                    debug_log(f"会话 {idx + 1} 保存完成")

                    # 检查是否实际进行了保存操作
                    if getattr(m_session, "__dirty__", False) is False:
                        saved_session_count += 1

                debug_log(
                    f"完成会话数据保存，总共 {len(data.sessions)} 个会话，"
                    f"其中 {saved_session_count} 个实际被保存"
                )

                debug_log("准备更新记忆元数据")
                memory.time = datetime.fromtimestamp(data.timestamp)
                memory.usage_count = data.usage
                memory.input_token_usage = data.input_token_usage
                memory.output_token_usage = data.output_token_usage

                debug_log(
                    f"已更新记忆元数据: time={data.timestamp}, usage={data.usage}, "
                    f"input_tokens={data.input_token_usage}, "
                    f"output_tokens={data.output_token_usage}"
                )

                if group_conf:
                    debug_log("准备更新群组配置")
                    group_conf.enable = data.enable
                    group_conf.prompt = data.prompt
                    group_conf.fake_people = data.fake_people
                    group_conf.last_updated = datetime.now()

                    debug_log(
                        f"已更新群组配置: enable={data.enable}, "
                        f"fake_people={data.fake_people}, "
                        f"prompt length={len(data.prompt)}"
                    )

                debug_log("准备提交数据库事务")
                await session.commit()
                debug_log("数据库事务提交成功")

            except Exception as e:
                debug_log(f"写入记忆数据过程中发生异常: {e}")
                await session.rollback()
                logger.warning(f"写入记忆数据时出错: {e}")
                if raise_err:
                    raise
                else:
                    logger.opt(exception=e, colors=True).error(
                        f"写入记忆数据时出错: {e}"
                    )
