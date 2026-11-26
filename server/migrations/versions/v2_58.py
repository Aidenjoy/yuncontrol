"""Administrator-managed installer release records.

New table only; existing rows are not rewritten.
"""

import sqlalchemy as sa
from alembic import op

revision = "v2_58"
down_revision = "v2_57"
branch_labels = None
depends_on = None

PLATFORM_CHECK = (
    "platform IN ("
    "'desktop-macos-arm64', 'desktop-macos-x64', 'desktop-windows', "
    "'desktop-linux', 'android', 'ios'"
    ")"
)


def upgrade() -> None:
    """Create the release registry used by the public version check."""
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "release_files" in tables:
        return
    op.create_table(
        "release_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("download_url", sa.String(length=2048), nullable=False),
        sa.Column(
            "file_name", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("notes", sa.String(length=4000), nullable=False, server_default=""),
        sa.Column(
            "published", sa.SmallInteger(), nullable=False, server_default="0"
        ),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("create_by", sa.String(length=160), nullable=False),
        sa.Column("update_by", sa.String(length=160), nullable=False),
        sa.Column("deleted", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint(PLATFORM_CHECK, name="ck_release_files_platform"),
        sa.CheckConstraint("published IN (0, 1)", name="ck_release_files_published"),
        sa.CheckConstraint("deleted IN (0, 1)", name="ck_release_files_deleted"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uk_release_files_active_platform",
        "release_files",
        ["platform"],
        unique=True,
        postgresql_where=sa.text("deleted = 0"),
    )


def downgrade() -> None:
    """Remove only the release registry."""
    op.drop_index("uk_release_files_active_platform", table_name="release_files")
    op.drop_table("release_files")
