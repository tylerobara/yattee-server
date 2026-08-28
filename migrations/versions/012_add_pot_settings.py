"""Add PO token provider (bgutil) settings.

yt_pot_enabled toggles the bgutil POT provider for yt-dlp;
yt_pot_provider_url optionally points at an external provider instead of
the bundled one.

Revision ID: 012
Revises: 011
Create Date: 2026-08-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, Sequence[str], None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == column for row in result)


def upgrade() -> None:
    if not _column_exists("settings", "yt_pot_enabled"):
        op.execute("ALTER TABLE settings ADD COLUMN yt_pot_enabled INTEGER DEFAULT 0")
    if not _column_exists("settings", "yt_pot_provider_url"):
        op.execute("ALTER TABLE settings ADD COLUMN yt_pot_provider_url TEXT")


def downgrade() -> None:
    if _column_exists("settings", "yt_pot_enabled"):
        op.execute("ALTER TABLE settings DROP COLUMN yt_pot_enabled")
    if _column_exists("settings", "yt_pot_provider_url"):
        op.execute("ALTER TABLE settings DROP COLUMN yt_pot_provider_url")
