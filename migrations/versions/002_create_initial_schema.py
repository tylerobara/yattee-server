"""Create initial schema.

Creates all tables for fresh databases. Uses IF NOT EXISTS so it's safe
to run on databases that already have the schema (existing databases).

Revision ID: 002
Revises: 001
Create Date: 2026-01-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables."""
    bind = op.get_bind()
    dialect = bind.dialect.name

    def has_table(table_name: str) -> bool:
        return sa.inspect(bind).has_table(table_name)

    def has_index(table_name: str, index_name: str) -> bool:
        return any(ix.get("name") == index_name for ix in sa.inspect(bind).get_indexes(table_name))

    # Users table
    if not has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.Text(), nullable=False, unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("is_admin", sa.Integer(), server_default=sa.text("0")),
            sa.Column("created_at", sa.Text(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("last_login", sa.TIMESTAMP(), nullable=True),
        )
    if has_table("users") and not has_index("users", "idx_users_username"):
        op.create_index("idx_users_username", "users", ["username"])

    # Legacy admins table for backwards compatibility
    if not has_table("admins"):
        op.create_table(
            "admins",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.Text(), nullable=False, unique=True),
            sa.Column("password_hash", sa.Text(), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("last_login", sa.TIMESTAMP(), nullable=True),
        )

    # Cached videos table
    if not has_table("cached_videos"):
        op.create_table(
            "cached_videos",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.Text(), nullable=False),
            sa.Column("site", sa.Text(), nullable=False),
            sa.Column("video_id", sa.Text(), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("author", sa.Text(), nullable=False),
            sa.Column("author_id", sa.Text(), nullable=False),
            sa.Column("length_seconds", sa.Integer(), server_default=sa.text("0")),
            sa.Column("view_count", sa.Integer(), nullable=True),
            sa.Column("published", sa.Integer(), nullable=True),
            sa.Column("published_text", sa.Text(), nullable=True),
            sa.Column("thumbnail_url", sa.Text(), nullable=True),
            sa.Column("thumbnail_data", sa.Text(), nullable=True),
            sa.Column("video_url", sa.Text(), nullable=True),
            sa.Column("fetched_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.UniqueConstraint("channel_id", "site", "video_id", name="uq_cached_videos_channel_site_video"),
        )
    if has_table("cached_videos") and not has_index("cached_videos", "idx_cached_videos_channel"):
        op.create_index("idx_cached_videos_channel", "cached_videos", ["channel_id", "site"])
    if has_table("cached_videos") and not has_index("cached_videos", "idx_cached_videos_published"):
        op.create_index("idx_cached_videos_published", "cached_videos", ["published"])
    if has_table("cached_videos") and not has_index("cached_videos", "idx_cached_videos_channel_published"):
        op.create_index("idx_cached_videos_channel_published", "cached_videos", ["channel_id", "site", "published"])

    # Feed fetch status table
    if not has_table("feed_fetch_status"):
        op.create_table(
            "feed_fetch_status",
            sa.Column("channel_id", sa.Text(), nullable=False),
            sa.Column("site", sa.Text(), nullable=False),
            sa.Column("last_fetch", sa.TIMESTAMP(), nullable=True),
            sa.Column("fetch_error", sa.Text(), nullable=True),
            sa.Column("max_videos_fetched", sa.Integer(), nullable=True),
            sa.Column("pagination_limited", sa.Boolean(), server_default=sa.text("false" if dialect == "postgresql" else "0")),
            sa.Column("pagination_limit_reason", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("channel_id", "site", name="pk_feed_fetch_status"),
        )

    # Watched channels table
    if not has_table("watched_channels"):
        op.create_table(
            "watched_channels",
            sa.Column("channel_id", sa.Text(), nullable=False),
            sa.Column("site", sa.Text(), nullable=False),
            sa.Column("channel_name", sa.Text(), nullable=True),
            sa.Column("channel_url", sa.Text(), nullable=True),
            sa.Column("avatar_url", sa.Text(), nullable=True),
            sa.Column("last_requested", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("subscriber_count", sa.Integer(), nullable=True),
            sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false" if dialect == "postgresql" else "0")),
            sa.Column("metadata_updated_at", sa.TIMESTAMP(), nullable=True),
            sa.PrimaryKeyConstraint("channel_id", "site", name="pk_watched_channels"),
        )
    if has_table("watched_channels") and not has_index("watched_channels", "idx_watched_channels_last_requested"):
        op.create_index("idx_watched_channels_last_requested", "watched_channels", ["last_requested"])

    # Sites table
    if not has_table("sites"):
        op.create_table(
            "sites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("extractor_pattern", sa.Text(), nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.text("true" if dialect == "postgresql" else "1")),
            sa.Column("priority", sa.Integer(), server_default=sa.text("0")),
            sa.Column("proxy_streaming", sa.Boolean(), server_default=sa.text("true" if dialect == "postgresql" else "1")),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if has_table("sites") and not has_index("sites", "idx_sites_enabled"):
        op.create_index("idx_sites_enabled", "sites", ["enabled"])
    if has_table("sites") and not has_index("sites", "idx_sites_extractor"):
        op.create_index("idx_sites_extractor", "sites", ["extractor_pattern"])

    # Insert default YouTube site if no sites exist
    op.execute(
        """
        INSERT INTO sites (id, name, extractor_pattern, enabled, priority, proxy_streaming)
        VALUES (1, 'YouTube', 'youtube', TRUE, 100, FALSE)
        ON CONFLICT (id) DO NOTHING
        """
    )

    # Credentials table
    if not has_table("credentials"):
        op.create_table(
            "credentials",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("credential_type", sa.Text(), nullable=False),
            sa.Column("key", sa.Text(), nullable=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("is_encrypted", sa.Boolean(), server_default=sa.text("false" if dialect == "postgresql" else "0")),
            sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        )
    if has_table("credentials") and not has_index("credentials", "idx_credentials_site_id"):
        op.create_index("idx_credentials_site_id", "credentials", ["site_id"])

    # Settings table
    if not has_table("settings"):
        op.create_table(
            "settings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("jwt_expiry_hours", sa.Integer(), server_default=sa.text("24")),
            sa.Column("ytdlp_path", sa.Text(), server_default=sa.text("'yt-dlp'")),
            sa.Column("ytdlp_timeout", sa.Integer(), server_default=sa.text("120")),
            sa.Column("cache_video_ttl", sa.Integer(), server_default=sa.text("3600")),
            sa.Column("cache_stream_ttl", sa.Integer(), server_default=sa.text("300")),
            sa.Column("cache_search_ttl", sa.Integer(), server_default=sa.text("900")),
            sa.Column("cache_channel_ttl", sa.Integer(), server_default=sa.text("1800")),
            sa.Column("cache_avatar_ttl", sa.Integer(), server_default=sa.text("86400")),
            sa.Column("cache_extract_ttl", sa.Integer(), server_default=sa.text("900")),
            sa.Column("default_search_results", sa.Integer(), server_default=sa.text("20")),
            sa.Column("max_search_results", sa.Integer(), server_default=sa.text("50")),
            sa.Column("invidious_instance", sa.Text(), nullable=True),
            sa.Column("invidious_timeout", sa.Integer(), server_default=sa.text("10")),
            sa.Column("invidious_author_thumbnails", sa.Integer(), server_default=sa.text("0")),
            sa.Column("invidious_proxy_channels", sa.Integer(), server_default=sa.text("1")),
            sa.Column("invidious_proxy_channel_tabs", sa.Integer(), server_default=sa.text("1")),
            sa.Column("invidious_proxy_videos", sa.Integer(), server_default=sa.text("1")),
            sa.Column("invidious_proxy_playlists", sa.Integer(), server_default=sa.text("1")),
            sa.Column("invidious_proxy_captions", sa.Integer(), server_default=sa.text("1")),
            sa.Column("invidious_proxy_thumbnails", sa.Integer(), server_default=sa.text("1")),
            sa.Column("feed_fetch_interval", sa.Integer(), server_default=sa.text("1800")),
            sa.Column("feed_channel_delay", sa.Integer(), server_default=sa.text("2")),
            sa.Column("feed_max_videos", sa.Integer(), server_default=sa.text("30")),
            sa.Column("feed_video_max_age", sa.Integer(), server_default=sa.text("30")),
            sa.Column("feed_ytdlp_use_flat_playlist", sa.Integer(), server_default=sa.text("0")),
            sa.Column("feed_fallback_ytdlp_on_414", sa.Integer(), server_default=sa.text("0")),
            sa.Column("basic_auth_enabled", sa.Integer(), server_default=sa.text("0")),
            sa.Column("allow_all_sites_for_extraction", sa.Integer(), server_default=sa.text("0")),
            sa.Column("rate_limit_window", sa.Integer(), server_default=sa.text("60")),
            sa.Column("rate_limit_max_failures", sa.Integer(), server_default=sa.text("5")),
            sa.Column("proxy_download_max_age", sa.Integer(), server_default=sa.text("300")),
            sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.CheckConstraint("id = 1", name="ck_settings_singleton"),
        )
    op.execute("INSERT INTO settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    """Drop all tables."""
    op.execute("DROP TABLE IF EXISTS credentials")
    op.execute("DROP TABLE IF EXISTS sites")
    op.execute("DROP TABLE IF EXISTS settings")
    op.execute("DROP TABLE IF EXISTS watched_channels")
    op.execute("DROP TABLE IF EXISTS feed_fetch_status")
    op.execute("DROP TABLE IF EXISTS cached_videos")
    op.execute("DROP TABLE IF EXISTS admins")
    op.execute("DROP TABLE IF EXISTS users")
