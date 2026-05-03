"""Stream proxy endpoints for playback and fast downloads."""

# Import as side effect to register routes on the shared router.
import routers.proxy._fast_download as _fast_download  # noqa: F401
import routers.proxy._relay as _relay  # noqa: F401
from routers.proxy._cleanup import cleanup_old_files_sync, start_cleanup_task
from routers.proxy._relay import signed_relay_url
from routers.proxy._streaming import router

__all__ = [
    "router",
    "cleanup_old_files_sync",
    "start_cleanup_task",
    "signed_relay_url",
]
