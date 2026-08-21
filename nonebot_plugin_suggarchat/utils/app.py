# Pydantic Models
from datetime import datetime

from aiologic import Lock
from amrita_sense.weakcache import WeakValueLRUCache
from nonebot_plugin_amrita.cache import LRUCache
from nonebot_plugin_amrita.memory import BaseSchema
from pydantic import Field

from .sql import GroupConfigExecutor


class GroupConfigSchema(BaseSchema):
    enable: bool = Field(default=True, description="是否启用")
    autoreply: bool = Field(default=False, description="是否自动回复")
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(), description="最后更新时间"
    )


class CachedGroupDataRepository:
    _instance = None
    _action_lock: WeakValueLRUCache[str, Lock]
    _cached_group_config: LRUCache[str, GroupConfigSchema]

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._cached_group_config = LRUCache(1024)  # 其次最常访问
            cls._action_lock = WeakValueLRUCache(
                capacity=1024, loose_mode=True
            )  # 动态锁池
            cls._instance = super().__new__(cls)
        return cls._instance

    def make_lock(self, session_id: str) -> Lock:
        if (lock := self._action_lock.get(session_id)) is None:
            lock = Lock()
            self._action_lock.put(session_id, lock)
        return lock

    @staticmethod
    def make_uni_id(id: int, is_group: bool) -> str:
        return f"{'group' if is_group else 'user'}_{id}"

    async def get_group_config(self, group_id: int) -> GroupConfigSchema:
        uni_id = self.make_uni_id(group_id, True)
        if config := self._cached_group_config.get(uni_id):
            return config
        async with self.make_lock(uni_id):
            async with GroupConfigExecutor(uni_id) as exc:
                conf = await exc.get_or_create_group_config()
                data = GroupConfigSchema.model_validate(conf)
            self._cached_group_config[uni_id] = data
            return data

    async def update_group_config(self, data: GroupConfigSchema) -> None:
        uni_id = data.user_id
        dirty_attrs = data.get_dirty_vars()
        async with self.make_lock(uni_id):
            async with GroupConfigExecutor(uni_id, with_for_update=True) as exc:
                gf = await exc.get_or_create_group_config()
                for attr in dirty_attrs:
                    setattr(gf, attr, getattr(data, attr))
        data.clean()
        self._cached_group_config[uni_id] = data
