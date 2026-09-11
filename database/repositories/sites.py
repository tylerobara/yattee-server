"""Sites and credentials repository."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from database.connection import get_connection


def create_site(
    name: str, extractor_pattern: str, enabled: bool = True, priority: int = 0, proxy_streaming: bool = True
) -> int:
    """Create a new site configuration. Returns the site ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO sites (name, extractor_pattern, enabled, priority, proxy_streaming)
               VALUES (?, ?, ?, ?, ?)""",
            (name, extractor_pattern, enabled, priority, proxy_streaming),
        )
        conn.commit()
        return cursor.lastrowid


def get_site(site_id: int) -> Optional[Dict[str, Any]]:
    """Get a site by ID with its credentials."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sites WHERE id = ?", (site_id,))
        site_row = cursor.fetchone()
        if not site_row:
            return None

        site = dict(site_row)

        # Get credentials for this site (include value to check has_value, but don't expose actual content)
        cursor.execute(
            """SELECT id, credential_type, key, value, is_encrypted, created_at,
                      status, stale_since, last_validated_at, last_error
               FROM credentials WHERE site_id = ?""",
            (site_id,),
        )
        site["credentials"] = [dict(row) for row in cursor.fetchall()]

        return site


def get_all_sites() -> List[Dict[str, Any]]:
    """Get all sites with credential counts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.*, COUNT(c.id) as credential_count,
                   COALESCE(SUM(CASE WHEN c.status = 'stale' THEN 1 ELSE 0 END), 0) as stale_credential_count
            FROM sites s
            LEFT JOIN credentials c ON s.id = c.site_id
            GROUP BY s.id
            ORDER BY s.priority DESC, s.name
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_enabled_sites(include_stale: bool = False) -> List[Dict[str, Any]]:
    """Get all enabled sites with their credentials for yt-dlp / InnerTube.

    Credentials marked stale (rotated account cookies) are omitted unless
    include_stale is True, so consumers fall back to anonymous access.
    """
    cred_sql = "SELECT * FROM credentials WHERE site_id = ?"
    if not include_stale:
        cred_sql += " AND status != 'stale'"
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sites WHERE enabled = 1 ORDER BY priority DESC
        """)
        sites = []
        for site_row in cursor.fetchall():
            site = dict(site_row)
            cursor.execute(cred_sql, (site["id"],))
            site["credentials"] = [dict(row) for row in cursor.fetchall()]
            sites.append(site)
        return sites


def update_site(
    site_id: int,
    name: str = None,
    extractor_pattern: str = None,
    enabled: bool = None,
    priority: int = None,
    proxy_streaming: bool = None,
) -> bool:
    """Update a site's configuration. Returns True if updated."""
    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if extractor_pattern is not None:
        updates.append("extractor_pattern = ?")
        params.append(extractor_pattern)
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(enabled)
    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)
    if proxy_streaming is not None:
        updates.append("proxy_streaming = ?")
        params.append(proxy_streaming)

    if not updates:
        return False

    updates.append("updated_at = ?")
    params.append(datetime.utcnow().isoformat())
    params.append(site_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE sites SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
        return cursor.rowcount > 0


def delete_site(site_id: int) -> bool:
    """Delete a site and its credentials. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.cursor()
        # Credentials are deleted by CASCADE
        cursor.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_site_by_extractor(extractor: str) -> Optional[Dict[str, Any]]:
    """Get a site by matching extractor pattern."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sites WHERE enabled = 1 ORDER BY priority DESC")
        for row in cursor.fetchall():
            site = dict(row)
            import re

            if re.search(site["extractor_pattern"], extractor, re.IGNORECASE):
                return site
        return None


def add_credential(site_id: int, credential_type: str, value: str, key: str = None, is_encrypted: bool = False) -> int:
    """Add a credential to a site. Returns the credential ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO credentials (site_id, credential_type, key, value, is_encrypted)
               VALUES (?, ?, ?, ?, ?)""",
            (site_id, credential_type, key, value, is_encrypted),
        )
        conn.commit()
        return cursor.lastrowid


def get_credential(credential_id: int) -> Optional[Dict[str, Any]]:
    """Get a credential by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM credentials WHERE id = ?", (credential_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def delete_credential(credential_id: int) -> bool:
    """Delete a credential. Returns True if deleted."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM credentials WHERE id = ?", (credential_id,))
        conn.commit()
        return cursor.rowcount > 0


def get_cookie_credentials(site_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all cookies_file credentials joined with their site (for validation)."""
    sql = """SELECT c.*, s.extractor_pattern, s.enabled AS site_enabled
             FROM credentials c JOIN sites s ON s.id = c.site_id
             WHERE c.credential_type = 'cookies_file'"""
    params: tuple = ()
    if site_id is not None:
        sql += " AND c.site_id = ?"
        params = (site_id,)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql + " ORDER BY c.id", params)
        return [dict(row) for row in cursor.fetchall()]


def update_credential_status(
    credential_id: int,
    *,
    status: str,
    stale_since: Optional[str] = None,
    last_validated_at: Optional[str] = None,
    last_error: Optional[str] = None,
) -> bool:
    """Set staleness columns on a credential. Returns True if updated."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE credentials
               SET status = ?, stale_since = ?, last_validated_at = ?, last_error = ?
               WHERE id = ?""",
            (status, stale_since, last_validated_at, last_error, credential_id),
        )
        conn.commit()
        return cursor.rowcount > 0
