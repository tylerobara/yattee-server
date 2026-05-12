"""Add invidious_local_streams toggle.

When true, requests local=true from Invidious so video stream URLs are
proxied through the Invidious instance (companion) instead of pointing
directly at googlevideo.com.

Revision ID: 010
Revises: 009
Create Date: 2026-04-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, Sequence[str], None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _column_exists("settings", "invidious_local_streams"):
        op.execute("ALTER TABLE settings ADD COLUMN invidious_local_streams INTEGER DEFAULT 0")


def downgrade() -> None:
    if _column_exists("settings", "invidious_local_streams"):
        op.execute("ALTER TABLE settings DROP COLUMN invidious_local_streams")
