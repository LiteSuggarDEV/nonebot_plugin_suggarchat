"""upd_amrita_models

迁移 ID: 9f3a2c1e7b4d
父迁移: 40596fc17a61
创建时间: 2026-08-21 20:30:00.000000

参照 amrita chat 模块的临时表迁移策略，将 suggarchat_* 旧表数据迁移到
amrita_* 新表，并通过"临时表 + 重建"方式确保 amrita_group_config 的外键
约束被正确创建（SQLite 无法对已有表追加外键，必须先删后建）。

数据映射：
- (ins_id, is_group) -> user_id：``{"group" if is_group else "user"}_{ins_id}``
- fake_people -> autoreply（旧 prompt 列新表无对应列，丢弃）
- memory_data.time -> user_metadata.last_active
- 旧计数列 -> user_metadata.total_* 计数（tokens_*/called_count 置 0）
- amrita_memory_data.extra_prompt 使用模型默认值 ""

升级/降级均为幂等操作（按主键去重）；downgrade 不删除 amrita_* 基础表
（属于 amrita 插件链），仅删除本插件的 amrita_group_config。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "9f3a2c1e7b4d"
down_revision: str | Sequence[str] | None = "40596fc17a61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "072361e8936f"

_TMP = "_amrita_group_config_tmp"

# ---- 新表列定义（参照 amrita 模型 / 初始迁移 072361e8936f）----
_GLOBAL_INSIGHTS_COLS = [
    sa.Column("date", sa.String(length=64), nullable=False),
    sa.Column(
        "token_input", sa.BigInteger(), server_default=sa.text("0"), nullable=False
    ),
    sa.Column(
        "token_output", sa.BigInteger(), server_default=sa.text("0"), nullable=False
    ),
    sa.Column("usage_count", sa.Integer(), nullable=False),
]
_USER_METADATA_COLS = [
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("user_id", sa.String(length=64), nullable=False),
    sa.Column("last_active", sa.DateTime(), nullable=False),
    sa.Column("total_called_count", sa.BigInteger(), nullable=False),
    sa.Column("total_input_token", sa.BigInteger(), nullable=False),
    sa.Column("total_output_token", sa.BigInteger(), nullable=False),
    sa.Column("tokens_input", sa.BigInteger(), nullable=False),
    sa.Column("tokens_output", sa.BigInteger(), nullable=False),
    sa.Column("called_count", sa.Integer(), nullable=False),
]
_MEMORY_DATA_COLS = [
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("user_id", sa.String(length=64), nullable=False),
    sa.Column("memory_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    sa.Column("extra_prompt", sa.Text(), nullable=False),
]
_MEMORY_SESSIONS_COLS = [
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("user_id", sa.String(length=64), nullable=False),
    sa.Column("created_at", sa.Float(), nullable=False),
    sa.Column("data", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
]
_GROUP_CONFIG_COLS = [
    sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
    sa.Column("user_id", sa.String(length=64), nullable=False),
    sa.Column("enable", sa.Boolean(), nullable=False),
    sa.Column("autoreply", sa.Boolean(), nullable=False),
    sa.Column("last_updated", sa.DateTime(), nullable=False),
]

# ---- 新旧表列名（供 sa.table / from_select 使用）----
_GLOBAL_INSIGHTS_COL_NAMES = ["date", "token_input", "token_output", "usage_count"]
_USER_METADATA_COL_NAMES = [
    "id",
    "user_id",
    "last_active",
    "total_called_count",
    "total_input_token",
    "total_output_token",
    "tokens_input",
    "tokens_output",
    "called_count",
]
_MEMORY_DATA_COL_NAMES = ["id", "user_id", "memory_json", "extra_prompt"]
_MEMORY_SESSIONS_COL_NAMES = ["id", "user_id", "created_at", "data"]
_GROUP_CONFIG_COL_NAMES = ["id", "user_id", "enable", "autoreply", "last_updated"]

_OLD_MEMORY_DATA_COL_NAMES = [
    "id",
    "ins_id",
    "is_group",
    "memory_json",
    "time",
    "usage_count",
    "input_token_usage",
    "output_token_usage",
]
_OLD_GROUP_CONFIG_COL_NAMES = [
    "id",
    "group_id",
    "enable",
    "prompt",
    "fake_people",
    "last_updated",
]
_OLD_MEMORY_SESSIONS_COL_NAMES = ["id", "ins_id", "is_group", "created_at", "data"]

# 需兜底确保的 amrita 模型索引
_INDICES: list[tuple[str, str, list[str]]] = [
    (
        "idx_amrita_user_id_last_active",
        "amrita_user_metadata",
        ["user_id", "last_active"],
    ),
    ("idx_am_sessions_user_id", "amrita_memory_sessions", ["user_id"]),
    ("idx_am_sessions_created_at_time", "amrita_memory_sessions", ["created_at"]),
    ("idx_amrita_group_config_user_id", "amrita_group_config", ["user_id"]),
]


def _inspector() -> sa.Inspector:
    insp = sa.inspect(op.get_bind())
    assert insp is not None
    return insp


def _table(name: str, cols: list[str]) -> sa.sql.expression.TableClause:
    return sa.table(name, *[sa.column(c) for c in cols])


def _old_tables_exist() -> bool:
    """suggarchat_* 旧表是否存在（以核心表为准）。"""
    return _inspector().has_table("suggarchat_memory_data")


def _copy_table(src_name: str, dst_name: str, col_names: list[str]) -> None:
    """按第一列（主键）去重拷贝，保证幂等。"""
    if not _inspector().has_table(src_name):
        return
    pk_col = col_names[0]
    dst = _table(dst_name, col_names)
    src = _table(src_name, col_names)
    sel = sa.select(src).where(
        ~sa.exists(sa.select(1).select_from(dst).where(dst.c[pk_col] == src.c[pk_col]))
    )
    op.execute(dst.insert().from_select(col_names, sel))


def _user_id_expr(
    is_group: sa.ColumnElement[Any], ins_id: sa.ColumnElement[Any]
) -> sa.ColumnElement[Any]:
    """(ins_id, is_group) -> user_id 字符串（make_uni_id 格式）。"""
    return sa.case(
        (
            is_group,
            sa.cast(sa.literal("group_"), sa.String) + sa.cast(ins_id, sa.String),
        ),
        else_=sa.cast(sa.literal("user_"), sa.String) + sa.cast(ins_id, sa.String),
    )


def _ins_id_expr(user_id: sa.ColumnElement[Any]) -> sa.ColumnElement[Any]:
    """user_id -> ins_id（'group_' 6 字符 / 'user_' 5 字符，用 instr 定位 '_'）。"""
    return sa.cast(
        sa.func.substr(user_id, sa.func.instr(user_id, "_") + 1),
        sa.BigInteger,
    )


def _is_group_expr(user_id: sa.ColumnElement[Any]) -> sa.ColumnElement[Any]:
    """user_id -> is_group（转义下划线，避免被当作单字符通配符）。"""
    return user_id.like("group\\_%", escape="\\")


def _ensure_amrita_tables() -> None:
    """防御性创建 amrita_* 基础表（若 amrita 链尚未创建）。"""
    insp = _inspector()
    if not insp.has_table("amrita_global_insights"):
        op.create_table(
            "amrita_global_insights",
            *_GLOBAL_INSIGHTS_COLS,
            sa.PrimaryKeyConstraint("date", name=op.f("pk_amrita_global_insights")),
        )
    if not insp.has_table("amrita_user_metadata"):
        op.create_table(
            "amrita_user_metadata",
            *_USER_METADATA_COLS,
            sa.PrimaryKeyConstraint("id", name=op.f("pk_amrita_user_metadata")),
            sa.UniqueConstraint("user_id", name="uq_amrita_user_metadata_user_id"),
        )
    if not insp.has_table("amrita_memory_data"):
        op.create_table(
            "amrita_memory_data",
            *_MEMORY_DATA_COLS,
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["amrita_user_metadata.user_id"],
                ondelete="CASCADE",
                name=op.f("fk_amrita_memory_data_user_id_amrita_user_metadata"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_amrita_memory_data")),
            sa.UniqueConstraint("user_id", name="uq_amrita_memory_user_id"),
        )
    if not insp.has_table("amrita_memory_sessions"):
        op.create_table(
            "amrita_memory_sessions",
            *_MEMORY_SESSIONS_COLS,
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["amrita_user_metadata.user_id"],
                ondelete="CASCADE",
                name=op.f("fk_amrita_memory_sessions_user_id_amrita_user_metadata"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_amrita_memory_sessions")),
        )


def _ensure_old_tables() -> None:
    """防御性重建 suggarchat_* 旧表（downgrade 使用，含 FK/约束/索引）。"""
    insp = _inspector()
    if not insp.has_table("suggarchat_memory_data"):
        op.create_table(
            "suggarchat_memory_data",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ins_id", sa.BigInteger(), nullable=False),
            sa.Column("is_group", sa.Boolean(), nullable=False),
            sa.Column(
                "memory_json",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            ),
            sa.Column("time", sa.DateTime(), nullable=False),
            sa.Column("usage_count", sa.Integer(), nullable=False),
            sa.Column(
                "input_token_usage",
                sa.BigInteger(),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.Column(
                "output_token_usage",
                sa.BigInteger(),
                server_default=sa.text("0"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_suggarchat_memory_data")),
            sa.UniqueConstraint("ins_id", "is_group", name="uq_ins_id_is_group"),
            sa.Index("idx_ins_id", "ins_id"),
            sa.Index("idx_is_group", "is_group"),
        )
    if not insp.has_table("suggarchat_global_insights"):
        op.create_table(
            "suggarchat_global_insights",
            *_GLOBAL_INSIGHTS_COLS,
            sa.PrimaryKeyConstraint("date", name=op.f("pk_suggarchat_global_insights")),
        )
    if not insp.has_table("suggarchat_group_config"):
        op.create_table(
            "suggarchat_group_config",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("group_id", sa.BigInteger(), nullable=False),
            sa.Column("enable", sa.Boolean(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("fake_people", sa.Boolean(), nullable=False),
            sa.Column("last_updated", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["group_id"],
                ["suggarchat_memory_data.ins_id"],
                name=op.f("fk_suggarchat_group_config_group_id_suggarchat_memory_data"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_suggarchat_group_config")),
            sa.UniqueConstraint("group_id", name="uq_suggarchat_config_group_id"),
            sa.Index("idx_suggarchat_group_id", "group_id"),
        )
    if not insp.has_table("suggarchat_memory_sessions"):
        op.create_table(
            "suggarchat_memory_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ins_id", sa.BigInteger(), nullable=False),
            sa.Column("is_group", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column(
                "data", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
            ),
            sa.ForeignKeyConstraint(
                ["ins_id"],
                ["suggarchat_memory_data.ins_id"],
                name=op.f(
                    "fk_suggarchat_memory_sessions_ins_id_suggarchat_memory_data"
                ),
            ),
            sa.ForeignKeyConstraint(
                ["is_group"],
                ["suggarchat_memory_data.is_group"],
                name=op.f(
                    "fk_suggarchat_memory_sessions_is_group_suggarchat_memory_data"
                ),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_suggarchat_memory_sessions")),
            sa.Index("idx_sessions_created_at", "created_at"),
            sa.Index("idx_sessions_ins_id", "ins_id"),
            sa.Index("idx_sessions_is_group", "is_group"),
        )


def _create_tmp_table() -> None:
    """创建无外键的 amrita_group_config 临时表。"""
    if not _inspector().has_table(_TMP):
        op.create_table(
            _TMP,
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.String(length=64), nullable=False),
            sa.Column("enable", sa.Boolean(), nullable=False),
            sa.Column("autoreply", sa.Boolean(), nullable=False),
            sa.Column("last_updated", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{_TMP}")),
            sa.UniqueConstraint("user_id", name=op.f(f"uq_{_TMP}_user_id")),
        )


def _create_group_config() -> None:
    """创建带外键的 amrita_group_config（指向 amrita_user_metadata）。"""
    op.create_table(
        "amrita_group_config",
        *_GROUP_CONFIG_COLS,
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["amrita_user_metadata.user_id"],
            ondelete="CASCADE",
            name=op.f("fk_amrita_group_config_user_id_amrita_user_metadata"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amrita_group_config")),
        sa.UniqueConstraint("user_id", name="uq_amrita_group_config_user_id"),
    )


def _ensure_indexes() -> None:
    """幂等补齐 amrita 模型索引。"""
    for index_name, table_name, columns in _INDICES:
        if not _inspector().has_table(table_name):
            continue
        existing = {i["name"] for i in _inspector().get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def _migrate_user_metadata() -> None:
    """suggarchat_memory_data -> amrita_user_metadata。"""
    if not _inspector().has_table("suggarchat_memory_data"):
        return
    src = _table("suggarchat_memory_data", _OLD_MEMORY_DATA_COL_NAMES)
    dst = _table("amrita_user_metadata", _USER_METADATA_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        _user_id_expr(src.c["is_group"], src.c["ins_id"]),
        src.c["time"],
        src.c["usage_count"],
        src.c["input_token_usage"],
        src.c["output_token_usage"],
        sa.literal(0),
        sa.literal(0),
        sa.literal(0),
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_USER_METADATA_COL_NAMES, sel))


def _migrate_memory_data() -> None:
    """suggarchat_memory_data -> amrita_memory_data。"""
    if not _inspector().has_table("suggarchat_memory_data"):
        return
    src = _table("suggarchat_memory_data", _OLD_MEMORY_DATA_COL_NAMES)
    dst = _table("amrita_memory_data", _MEMORY_DATA_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        _user_id_expr(src.c["is_group"], src.c["ins_id"]),
        src.c["memory_json"],
        sa.literal(""),
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_MEMORY_DATA_COL_NAMES, sel))


def _migrate_memory_sessions() -> None:
    """suggarchat_memory_sessions -> amrita_memory_sessions。"""
    if not _inspector().has_table("suggarchat_memory_sessions"):
        return
    src = _table("suggarchat_memory_sessions", _OLD_MEMORY_SESSIONS_COL_NAMES)
    dst = _table("amrita_memory_sessions", _MEMORY_SESSIONS_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        _user_id_expr(src.c["is_group"], src.c["ins_id"]),
        src.c["created_at"],
        src.c["data"],
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_MEMORY_SESSIONS_COL_NAMES, sel))


def _migrate_group_config() -> None:
    """suggarchat_group_config -> 临时表（prompt 丢弃，fake_people -> autoreply）。"""
    if not _inspector().has_table("suggarchat_group_config"):
        return
    src = _table("suggarchat_group_config", _OLD_GROUP_CONFIG_COL_NAMES)
    dst = _table(_TMP, _GROUP_CONFIG_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        sa.cast(sa.literal("group_"), sa.String)
        + sa.cast(src.c["group_id"], sa.String),
        src.c["enable"],
        src.c["fake_people"],
        src.c["last_updated"],
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_GROUP_CONFIG_COL_NAMES, sel))


def _restore_memory_data() -> None:
    """amrita_user_metadata + amrita_memory_data -> suggarchat_memory_data。"""
    if not _inspector().has_table("amrita_user_metadata"):
        return
    src_um = _table("amrita_user_metadata", _USER_METADATA_COL_NAMES)
    src_md = _table("amrita_memory_data", _MEMORY_DATA_COL_NAMES)
    dst = _table("suggarchat_memory_data", _OLD_MEMORY_DATA_COL_NAMES)
    memory_json = sa.func.coalesce(
        src_md.c["memory_json"], sa.cast(sa.literal("{}"), sa.JSON)
    )
    sel = (
        sa.select(
            src_um.c["id"],
            _ins_id_expr(src_um.c["user_id"]),
            _is_group_expr(src_um.c["user_id"]),
            memory_json,
            src_um.c["last_active"],
            src_um.c["total_called_count"],
            src_um.c["total_input_token"],
            src_um.c["total_output_token"],
        )
        .select_from(
            src_um.join(
                src_md,
                src_um.c["user_id"] == src_md.c["user_id"],
                isouter=True,
            )
        )
        .where(
            ~sa.exists(
                sa.select(1).select_from(dst).where(dst.c["id"] == src_um.c["id"])
            )
        )
    )
    op.execute(dst.insert().from_select(_OLD_MEMORY_DATA_COL_NAMES, sel))


def _restore_memory_sessions() -> None:
    """amrita_memory_sessions -> suggarchat_memory_sessions。"""
    if not _inspector().has_table("amrita_memory_sessions"):
        return
    src = _table("amrita_memory_sessions", _MEMORY_SESSIONS_COL_NAMES)
    dst = _table("suggarchat_memory_sessions", _OLD_MEMORY_SESSIONS_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        _ins_id_expr(src.c["user_id"]),
        _is_group_expr(src.c["user_id"]),
        src.c["created_at"],
        src.c["data"],
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_OLD_MEMORY_SESSIONS_COL_NAMES, sel))


def _restore_group_config() -> None:
    """临时表 -> suggarchat_group_config（autoreply -> fake_people，prompt 置空）。"""
    if not _inspector().has_table(_TMP):
        return
    src = _table(_TMP, _GROUP_CONFIG_COL_NAMES)
    dst = _table("suggarchat_group_config", _OLD_GROUP_CONFIG_COL_NAMES)
    sel = sa.select(
        src.c["id"],
        _ins_id_expr(src.c["user_id"]),
        src.c["enable"],
        sa.literal(""),
        src.c["autoreply"],
        src.c["last_updated"],
    ).where(~sa.exists(sa.select(1).select_from(dst).where(dst.c["id"] == src.c["id"])))
    op.execute(dst.insert().from_select(_OLD_GROUP_CONFIG_COL_NAMES, sel))


def upgrade() -> None:
    if not _old_tables_exist():
        # 全新安装或旧表已清理：仅确保新表、本插件表与索引存在
        _ensure_amrita_tables()
        if not _inspector().has_table("amrita_group_config"):
            _create_group_config()
        _ensure_indexes()
        return

    # 1. 确保 amrita_* 基础表存在（amrita 链可能尚未执行）
    _ensure_amrita_tables()

    # 2. 创建无外键的临时表
    _create_tmp_table()

    # 3. 迁移数据：旧表 -> 新表 / 临时表（按主键去重，幂等）
    _copy_table(
        "suggarchat_global_insights",
        "amrita_global_insights",
        _GLOBAL_INSIGHTS_COL_NAMES,
    )
    _migrate_user_metadata()
    _migrate_memory_data()
    _migrate_memory_sessions()
    _migrate_group_config()
    _copy_table("amrita_group_config", _TMP, _GROUP_CONFIG_COL_NAMES)

    # 4. 删除旧表（先删依赖方）及旧的 amrita_group_config
    for tbl in (
        "suggarchat_memory_sessions",
        "suggarchat_group_config",
        "suggarchat_memory_data",
        "suggarchat_global_insights",
        "amrita_group_config",
    ):
        if _inspector().has_table(tbl):
            op.drop_table(tbl)

    # 5. 重建带外键的 amrita_group_config
    _create_group_config()

    # 6. 临时表回拷
    _copy_table(_TMP, "amrita_group_config", _GROUP_CONFIG_COL_NAMES)

    # 7. 清理临时表
    op.drop_table(_TMP)

    # 8. 兜底补齐索引
    _ensure_indexes()


def downgrade() -> None:
    # 1. 重建 suggarchat_* 旧表（含 FK/约束/索引）
    _ensure_old_tables()

    # 2. 创建临时表，承载 amrita_group_config 数据
    _create_tmp_table()

    # 3. 回拷数据：新表 -> 旧表（按主键去重，幂等）
    _copy_table(
        "amrita_global_insights",
        "suggarchat_global_insights",
        _GLOBAL_INSIGHTS_COL_NAMES,
    )
    _restore_memory_data()
    _restore_memory_sessions()
    _copy_table("amrita_group_config", _TMP, _GROUP_CONFIG_COL_NAMES)
    _restore_group_config()

    # 4. 删除本插件的 amrita_group_config（amrita_* 基础表保留，属 amrita 链）
    if _inspector().has_table("amrita_group_config"):
        op.drop_table("amrita_group_config")

    # 5. 清理临时表
    if _inspector().has_table(_TMP):
        op.drop_table(_TMP)
