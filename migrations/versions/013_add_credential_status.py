"""Add staleness tracking columns to credentials.

status is 'ok' or 'stale'; a stale cookies_file row is skipped by
get_enabled_sites() so yt-dlp and InnerTube fall back to anonymous access
instead of silently degrading (rotated account cookies yield 360p-only).

Revision ID: 013
Revises: 012
Create Date: 2026-09-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, Sequence[str], None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = {
    "status": "TEXT NOT NULL DEFAULT 'ok'",
    "stale_since": "TIMESTAMP",
    "last_validated_at": "TIMESTAMP",
    "last_error": "TEXT",
}


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    for column, ddl in _COLUMNS.items():
        if not _column_exists("credentials", column):
            op.execute(f"ALTER TABLE credentials ADD COLUMN {column} {ddl}")


def downgrade() -> None:
    for column in _COLUMNS:
        if _column_exists("credentials", column):
            op.execute(f"ALTER TABLE credentials DROP COLUMN {column}")
