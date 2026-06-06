"""Stub for Google Sheets backup service — not yet implemented."""


def enqueue_tiktok_live_sheet_backup(session_id, event_type):
    return None


def get_tiktok_live_sheet_backup_status(session_id):
    return {"ok": True, "status": "unavailable", "error": "google_sheets_not_configured"}


def get_full_workbook_backup_status():
    return {"ok": True, "status": "unavailable", "error": "google_sheets_not_configured"}


def sync_full_workbook_backup_to_google_sheet():
    return {"ok": False, "error": "google_sheets_not_configured"}
