"""Add yt_egress_proxy setting.

Adds a runtime-configurable proxy URL used by yt-dlp and the InnerTube
HTTP client for YouTube-bound traffic. Previously sourced only from the
YT_EGRESS_PROXY env var; the env var is preserved as an autoprovisioning
seed.

Revision ID: 008
Revises: 007
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, Sequence[str], None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return any(col_info.get("name") == column for col_info in inspector.get_columns(table))


def upgrade() -> None:
    if not _column_exists("settings", "yt_egress_proxy"):
        op.execute("ALTER TABLE settings ADD COLUMN yt_egress_proxy TEXT")


def downgrade() -> None:
    if _column_exists("settings", "yt_egress_proxy"):
        op.execute("ALTER TABLE settings DROP COLUMN yt_egress_proxy")
