"""Repair legacy release constraints; keep retired-platform records without rewriting installers."""

import sqlalchemy as sa
from alembic import op

revision = "v2_59"
down_revision = "v2_58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow independent Apple Silicon/Intel records and enforce one live row per platform."""
    conn = op.get_bind()
    # Fail explicitly rather than silently deleting historical versions to create the unique index.
    duplicates = (
        conn.execute(
            sa.text(
                "SELECT platform FROM release_files WHERE deleted = 0 GROUP BY platform HAVING count(*) > 1"
            )
        )
        .scalars()
        .all()
    )
    if duplicates:
        raise RuntimeError(
            "Consolidate live release records before migration: "
            + ", ".join(duplicates)
        )
    op.drop_constraint("ck_release_files_platform", "release_files", type_="check")
    # Retired values remain valid for existing rows; the API rejects new Linux/legacy-Mac entries.
    op.create_check_constraint(
        "ck_release_files_platform",
        "release_files",
        "platform IN ('desktop-macos-arm64', 'desktop-macos-x64', 'desktop-macos', 'desktop-windows', 'desktop-linux', 'android', 'ios')",
    )
    indexes = {entry["name"] for entry in sa.inspect(conn).get_indexes("release_files")}
    if "uk_release_files_active_version" in indexes:
        op.drop_index("uk_release_files_active_version", table_name="release_files")
    if "uk_release_files_active_platform" not in indexes:
        op.create_index(
            "uk_release_files_active_platform",
            "release_files",
            ["platform"],
            unique=True,
            postgresql_where=sa.text("deleted = 0"),
        )


def downgrade() -> None:
    """Restore version-based uniqueness while retaining valid architecture-specific rows."""
    op.drop_index("uk_release_files_active_platform", table_name="release_files")
    op.create_index(
        "uk_release_files_active_version",
        "release_files",
        ["platform", "version"],
        unique=True,
        postgresql_where=sa.text("deleted = 0"),
    )
