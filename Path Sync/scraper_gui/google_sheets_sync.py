"""Google Apps Script sync client for assignment rows."""

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import requests

from config import resolve_sm_display_name, safe_str, sm_priority
from config.google_sync import GoogleSyncSettings


class RetryableError(RuntimeError):
    """Raised when the server indicates another user holds the lock."""


def _clean_cell(value: Any) -> str:
    text = safe_str(value)
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    text = text.replace("\t", " ")
    return " ".join(text.split())


def _format_category_level(item: Dict[str, Any]) -> str:
    raw_level = safe_str(item.get("category_level", "")).strip()
    if not raw_level or raw_level == "-":
        return raw_level
    normalized = re.sub(r"^category\s*", "", raw_level, flags=re.IGNORECASE).strip()
    return f"Category {normalized}" if normalized else ""


def normalize_results_for_sheet(results: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    sorted_results = sorted(
        results,
        key=lambda item: (
            999 if "error" in item else sm_priority(item.get("sm_name", "")),
            item.get("url", ""),
        ),
    )

    rows = []
    for item in sorted_results:
        if "error" in item:
            rows.append(
                {
                    "Date": "ERROR",
                    "Auditor": "",
                    "Week": "",
                    "Subcontractor": "",
                    "Order #": "",
                    "Service Type": f"ERROR: {_clean_cell(item.get('error', 'Unknown'))[:80]}",
                    "Match": "",
                    "Image Count": "",
                    "SM Name": "",
                    "Category Level": "",
                    "Return Format": "",
                    "Comments": "",
                    "Notes": f"URL: {_clean_cell(item.get('url', 'Unknown'))}",
                }
            )
            continue

        rows.append(
            {
                "Date": _clean_cell(item.get("date", "")),
                "Auditor": _clean_cell(item.get("auditor", "")),
                "Week": _clean_cell(item.get("week", "")),
                "Subcontractor": _clean_cell(
                    item.get("subcontractor", "").replace("ClippingPix", "Clipping Pix")
                ),
                "Order #": _clean_cell(item.get("order_number", "")),
                "Service Type": _clean_cell(item.get("service_type", "")),
                "Match": "Yes",
                "Image Count": _clean_cell(item.get("image_count", "")),
                "SM Name": _clean_cell(
                    resolve_sm_display_name(item.get("sm_name", ""))
                ),
                "Category Level": _clean_cell(_format_category_level(item)),
                "Return Format": _clean_cell(item.get("return_format", "")),
                "Comments": _clean_cell(item.get("comments", "")),
                "Notes": _clean_cell(item.get("notes", "")),
            }
        )
    return rows


def build_payload(
    settings: GoogleSyncSettings, rows: List[Dict[str, str]], *, test: bool = False
) -> Dict[str, Any]:
    return {
        "token": settings.secret_token.strip(),
        "spreadsheetId": settings.spreadsheet_id.strip(),
        "sheetTab": (settings.sheet_tab or "RawData").strip(),
        "rows": rows,
        "test": test,
        "sentAt": datetime.now(timezone.utc).isoformat(),
    }


def post_to_apps_script(
    settings: GoogleSyncSettings, rows: List[Dict[str, str]], *, test: bool = False
) -> Dict[str, Any]:
    payload = build_payload(settings, rows, test=test)
    response = requests.post(settings.script_url.strip(), json=payload, timeout=120)
    if response.status_code in (401, 403):
        raise RuntimeError(
            "Apps Script denied access. Redeploy the Web App with Execute as 'Me' "
            "and Who has access set to 'Anyone', then paste the normal "
            "https://script.google.com/macros/s/.../exec URL. Domain URLs containing "
            "/a/macros/ are login-restricted and will fail here."
        )
    response.raise_for_status()
    data = response.json()
    if data.get("retryable"):
        raise RetryableError(data.get("message", "Another user is currently syncing."))
    if not data.get("ok"):
        raise RuntimeError(data.get("message", "Google sync failed"))
    return data


RETRY_MAX_ATTEMPTS = 10
RETRY_BASE_DELAY = 2.0


def sync_rows_in_batches(
    settings: GoogleSyncSettings,
    rows: List[Dict[str, str]],
    batch_size: int = 100,
    retry_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> int:
    appended = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
            if cancel_check and cancel_check():
                raise RuntimeError("Sync cancelled by user.")

            try:
                data = post_to_apps_script(settings, batch)
                appended += int(data.get("appended", len(batch)))
                break
            except (RetryableError, requests.ReadTimeout, requests.ConnectionError):
                if attempt == RETRY_MAX_ATTEMPTS:
                    raise RuntimeError(
                        "Google Sheets is not responding. "
                        "Check your internet connection and try again."
                    )
                if retry_callback:
                    retry_callback(attempt, RETRY_MAX_ATTEMPTS)
                delay = RETRY_BASE_DELAY * attempt
                for _ in range(int(delay / 0.2)):
                    if cancel_check and cancel_check():
                        raise RuntimeError("Sync cancelled by user.")
                    time.sleep(0.2)
    return appended
