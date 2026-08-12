"""Background sync scheduler. Runs sync.run_sync() on a timer whose interval
is read from app_settings.sync_interval_minutes, re-checking that value each
cycle so a change made on the Settings page takes effect on the next tick
without a restart.
"""
import logging
import threading

from . import db
from .sync import run_sync

logger = logging.getLogger("powerliftingdash.scheduler")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _loop():
    while not _stop_event.is_set():
        settings = db.get_settings()
        interval_minutes = settings.get("sync_interval_minutes") or 10
        if settings.get("google_sheet_id"):
            try:
                run_sync()
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("Background sync failed")
        else:
            logger.debug("No Google Sheet configured yet; skipping scheduled sync")
        _stop_event.wait(timeout=max(60, interval_minutes * 60))


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="sheet-sync", daemon=True)
    _thread.start()
    logger.info("Background sync scheduler started")


def stop():
    _stop_event.set()
