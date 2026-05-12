"""Add yt_egress_proxy_enabled toggle.

Allows temporarily disabling the egress proxy without clearing the URL.

Revision ID: 009
Revises: 008
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, Sequence[str], None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _column_exists("settings", "yt_egress_proxy_enabled"):
        op.execute("ALTER TABLE settings ADD COLUMN yt_egress_proxy_enabled INTEGER DEFAULT 1")


def downgrade() -> None:
    if _column_exists("settings", "yt_egress_proxy_enabled"):
        op.execute("ALTER TABLE settings DROP COLUMN yt_egress_proxy_enabled")
