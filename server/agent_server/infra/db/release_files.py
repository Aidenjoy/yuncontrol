"""Administrator-managed installer releases; storage stays outside this table."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    SmallInteger,
    String,
    Table,
    text,
)

PLATFORMS = (
    "desktop-macos-arm64",
    "desktop-macos-x64",
    "desktop-macos",  # Retained for historical rows; no longer accepted by the API.
    "desktop-windows",
    "desktop-linux",
    "android",
    "ios",
)

# Rendered into the CHECK constraint so the tuple above stays the only source.
_PLATFORM_SQL = ", ".join(f"'{value}'" for value in PLATFORMS)


def release_tables(metadata):
    """Declare release records without touching any existing table."""

    def audit():
        """Return fresh audit columns for the release table."""
        return [
            Column("create_time", DateTime(timezone=True), nullable=False),
            Column("update_time", DateTime(timezone=True), nullable=False),
            Column("create_by", String(160), nullable=False),
            Column("update_by", String(160), nullable=False),
            Column("deleted", SmallInteger, nullable=False, server_default="0"),
        ]

    releases = Table(
        "release_files",
        metadata,
        # Autoincrement keeps this low-traffic administrative table independent
        # of the snowflake clock the catalog uses.
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("platform", String(32), nullable=False),
        Column("version", String(64), nullable=False),
        Column("download_url", String(2048), nullable=False),
        Column("file_name", String(255), nullable=False, server_default=""),
        Column("notes", String(4000), nullable=False, server_default=""),
        Column("published", SmallInteger, nullable=False, server_default="0"),
        *audit(),
        CheckConstraint(
            f"platform IN ({_PLATFORM_SQL})",
            name="ck_release_files_platform",
        ),
        CheckConstraint("published IN (0, 1)", name="ck_release_files_published"),
        CheckConstraint("deleted IN (0, 1)", name="ck_release_files_deleted"),
    )
    # Exactly one live record per platform: a new build replaces the old one
    # by editing that row, so clients never see two candidates.
    Index(
        "uk_release_files_active_platform",
        releases.c.platform,
        unique=True,
        postgresql_where=text("deleted = 0"),
    )
    return (releases,)
