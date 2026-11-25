# YunWork-compatible plugin catalog; audit fields follow the project table conventions.
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    SmallInteger,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import JSONB


def catalog_tables(metadata):
    """Declare catalog and transactional publication history on the supplied metadata."""

    def audit():
        """Return fresh audit columns for each catalog table."""
        return [
            Column("create_time", DateTime(timezone=True), nullable=False),
            Column("update_time", DateTime(timezone=True), nullable=False),
            Column("create_by", String(160), nullable=False),
            Column("update_by", String(160), nullable=False),
            Column("deleted", SmallInteger, nullable=False, server_default="0"),
        ]

    info = Table(
        "plugin_catalog_info",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=False),
        Column("plugin_key", String(160), nullable=False),
        Column("item", JSONB, nullable=False),
        Column("status", String(16), nullable=False, server_default="draft"),
        *audit(),
        CheckConstraint(
            "status IN ('draft', 'published')", name="ck_plugin_catalog_info_status"
        ),
        CheckConstraint("deleted IN (0, 1)", name="ck_plugin_catalog_info_deleted"),
    )
    Index("uk_plugin_catalog_info_plugin_key", info.c.plugin_key, unique=True)
    Index("idx_plugin_catalog_info_status", info.c.status, info.c.deleted)
    flow = Table(
        "plugin_catalog_flow",
        metadata,
        Column("id", BigInteger, primary_key=True, autoincrement=False),
        Column("plugin_catalog_info_id", BigInteger, nullable=False),
        Column("action", String(24), nullable=False),
        Column("status", String(16), nullable=False),
        *audit(),
        CheckConstraint("deleted IN (0, 1)", name="ck_plugin_catalog_flow_deleted"),
    )
    Index(
        "idx_plugin_catalog_flow_plugin_catalog_info_id", flow.c.plugin_catalog_info_id
    )
    return info, flow
