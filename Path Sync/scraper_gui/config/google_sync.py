"""Google Sheets sync settings and validation helpers."""

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Tuple

APP_SCRIPT_PROJECT_NAME = "SYNC_TISTA_DATA"
DEFAULT_SHEET_TAB = "RawData"

_APPDATA = os.environ.get("APPDATA", "")
_SETTINGS_DIR = (
    os.path.join(_APPDATA, "TistaScraper")
    if _APPDATA
    else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"
    )
)
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "google_sync_settings.json")


@dataclass
class GoogleSyncSettings:
    sheet_link: str = ""
    spreadsheet_id: str = ""
    sheet_tab: str = DEFAULT_SHEET_TAB
    script_url: str = ""
    secret_token: str = ""
    is_validated: bool = False
    last_test_at: str = ""
    configured_at: str = ""


def extract_spreadsheet_id(sheet_link: str) -> str:
    """Extract a Google Sheets spreadsheet ID from a full link or raw ID."""
    value = (sheet_link or "").strip()
    if not value:
        return ""

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", value)
    if match:
        return match.group(1)

    if re.fullmatch(r"[a-zA-Z0-9-_]{20,}", value):
        return value

    return ""


def validate_script_url(script_url: str) -> bool:
    value = (script_url or "").strip()
    return value.startswith("https://script.google.com/macros/s/") and value.endswith(
        "/exec"
    )


def validate_settings(settings: GoogleSyncSettings) -> Tuple[bool, str]:
    if not extract_spreadsheet_id(settings.sheet_link):
        return False, "Paste a valid Google Sheet link or spreadsheet ID."
    if not validate_script_url(settings.script_url):
        return (
            False,
            "Paste the public Web App URL like https://script.google.com/macros/s/.../exec. "
            "Do not use a domain URL containing /a/macros/.",
        )
    if not (settings.secret_token or "").strip():
        return False, "Enter a secret token."
    if not (settings.sheet_tab or "").strip():
        return False, "Enter a sheet tab name."
    return True, "Settings are ready."


def load_google_sync_settings() -> GoogleSyncSettings:
    try:
        if not os.path.exists(_SETTINGS_FILE):
            return GoogleSyncSettings()
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        settings = GoogleSyncSettings(**{**asdict(GoogleSyncSettings()), **data})
        settings.spreadsheet_id = extract_spreadsheet_id(settings.sheet_link)
        return settings
    except Exception:
        return GoogleSyncSettings()


def save_google_sync_settings(settings: GoogleSyncSettings) -> None:
    os.makedirs(_SETTINGS_DIR, exist_ok=True)
    settings.spreadsheet_id = extract_spreadsheet_id(settings.sheet_link)
    if not settings.configured_at:
        settings.configured_at = datetime.now().isoformat(timespec="seconds")
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(settings), f, indent=2)


def is_google_sync_configured(settings: GoogleSyncSettings) -> bool:
    ok, _ = validate_settings(settings)
    return ok and settings.is_validated
