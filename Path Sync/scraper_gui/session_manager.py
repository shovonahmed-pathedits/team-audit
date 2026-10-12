"""
Session Manager - Saves and restores HTTP session cookies between app restarts.

Encryption strategy (Windows-first):
1. Primary: Windows DPAPI (CryptProtectData / CryptUnprotectData) — OS-level
   encryption tied to the current Windows user account. No key management needed.
2. Fallback: Fernet symmetric encryption with machine-derived key — for
   compatibility when DPAPI is unavailable.

Storage: %APPDATA%/TistaScraper/session.dat
"""

import os
import json
import logging
import base64
from pathlib import Path

logger = logging.getLogger("tista_scraper")

# Storage location: hidden folder in %APPDATA%
_APPDATA = os.environ.get("APPDATA", "")
_SESSION_DIR = os.path.join(_APPDATA, "TistaScraper")
_SESSION_FILE = os.path.join(_SESSION_DIR, "session.dat")

# Try to import Windows DPAPI support
_DPAPI_AVAILABLE = False
try:
    import win32crypt

    _DPAPI_AVAILABLE = True
except ImportError:
    pass

# Fallback: Fernet encryption
if not _DPAPI_AVAILABLE:
    try:
        from cryptography.fernet import Fernet, InvalidToken
        import hashlib

        _MACHINE_KEY_MATERIAL = f"tista-session-{os.environ.get('USERNAME', 'default')}-{os.environ.get('COMPUTERNAME', 'default')}".encode()
        _MACHINE_KEY = base64.urlsafe_b64encode(
            hashlib.sha256(_MACHINE_KEY_MATERIAL).digest()
        )

        def _get_fernet() -> "Fernet":
            return Fernet(_MACHINE_KEY)
    except ImportError:
        pass


def _ensure_dir():
    """Ensure session storage directory exists."""
    os.makedirs(_SESSION_DIR, exist_ok=True)


def save_session(session) -> bool:
    """
    Save cookies from a requests.Session object to encrypted file.

    Saves full cookie metadata (domain, path, expires, secure, etc.) to ensure
    proper restoration.

    Uses Windows DPAPI if available, otherwise falls back to Fernet.

    Args:
        session: requests.Session object with active cookies

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Save full cookie metadata, not just name:value
        cookies_list = []
        for cookie in session.cookies:
            cookies_list.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "expires": cookie.expires,
                    "secure": cookie.secure,
                    "httponly": getattr(cookie, "httponly", False),
                    "samesite": getattr(cookie, "samesite", None),
                }
            )

        if not cookies_list:
            return False

        json_data = json.dumps(cookies_list, indent=2)
        _ensure_dir()

        if _DPAPI_AVAILABLE:
            # DPAPI: encrypt with user-account-bound key
            encrypted = win32crypt.CryptProtectData(
                json_data.encode("utf-8"),
                "TistaScraper Session",  # description
                None,  # optional entropy
                None,  # reserved - must be None for Python 3
                None,  # prompt - must be None for Python 3
                0,  # flags
            )
            # Prefix with version byte so we know the format
            with open(_SESSION_FILE, "wb") as f:
                f.write(b"\x02")  # version 2 = DPAPI with full metadata
                f.write(encrypted)
        else:
            # Fallback: Fernet encryption
            fernet = _get_fernet()
            encrypted = fernet.encrypt(json_data.encode("utf-8"))
            with open(_SESSION_FILE, "wb") as f:
                f.write(b"\x00")  # version 0 = Fernet (legacy, but we'll update)
                f.write(encrypted)

        logger.info(f"Saved session with {len(cookies_list)} cookies")
        return True

    except Exception as e:
        logger.error("Failed to save session: %s", e)
        return False


def load_session() -> dict:
    """
    Load and decrypt saved session cookies.

    Auto-detects encryption format (DPAPI or Fernet) and handles legacy formats.
    Returns full cookie metadata for proper restoration.

    Returns:
        List of cookie dicts with full metadata, or empty list if not found/invalid
    """
    try:
        if not os.path.exists(_SESSION_FILE):
            return []

        with open(_SESSION_FILE, "rb") as f:
            data = f.read()

        if not data:
            return []

        version = data[0]
        payload = data[1:]

        if version == 0x02 and _DPAPI_AVAILABLE:
            # Version 2: DPAPI with full metadata
            decrypted = win32crypt.CryptUnprotectData(payload, None, None, None, 0)[1]
            json_data = decrypted.decode("utf-8")
        elif version == 0x01:
            # Version 1: DPAPI with name:value only (legacy)
            decrypted = win32crypt.CryptUnprotectData(payload, None, None, None, 0)[1]
            json_data = decrypted.decode("utf-8")
            # Convert legacy dict to list format
            cookies_dict = json.loads(json_data)
            cookies_list = [
                {
                    "name": k,
                    "value": v,
                    "domain": "",
                    "path": "/",
                    "expires": None,
                    "secure": False,
                    "httponly": False,
                    "samesite": None,
                }
                for k, v in cookies_dict.items()
            ]
            return cookies_list
        elif version == 0x00:
            # Version 0: Fernet (legacy)
            fernet = _get_fernet()
            json_data = fernet.decrypt(payload).decode("utf-8")
            # Assume legacy dict format
            cookies_dict = json.loads(json_data)
            cookies_list = [
                {
                    "name": k,
                    "value": v,
                    "domain": "",
                    "path": "/",
                    "expires": None,
                    "secure": False,
                    "httponly": False,
                    "samesite": None,
                }
                for k, v in cookies_dict.items()
            ]
            return cookies_list
        elif _DPAPI_AVAILABLE:
            # Try DPAPI first (maybe old file without version byte)
            try:
                decrypted = win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]
                json_data = decrypted.decode("utf-8")
                cookies_dict = json.loads(json_data)
                if isinstance(cookies_dict, dict):
                    cookies_list = [
                        {
                            "name": k,
                            "value": v,
                            "domain": "",
                            "path": "/",
                            "expires": None,
                            "secure": False,
                            "httponly": False,
                            "samesite": None,
                        }
                        for k, v in cookies_dict.items()
                    ]
                else:
                    cookies_list = cookies_dict
                return cookies_list
            except Exception:
                return []
        else:
            return []

        cookies_list = json.loads(json_data)
        logger.info(f"Loaded session with {len(cookies_list)} cookies")
        return cookies_list

    except Exception as e:
        logger.error("Failed to load session: %s", e)
        return []


def has_session() -> bool:
    """Check if a saved session file exists."""
    return os.path.exists(_SESSION_FILE)


def clear_all() -> bool:
    """Clear all saved session data."""
    try:
        if os.path.exists(_SESSION_FILE):
            os.remove(_SESSION_FILE)
            logger.info("Cleared saved session")
        return True
    except Exception as e:
        logger.error("Failed to clear session: %s", e)
        return False


def restore_cookies_to_session(session, cookies_list: list) -> None:
    """
    Restore a list of cookie dicts into a requests.Session.

    Args:
        session: requests.Session object
        cookies_list: List of cookie dicts with metadata
    """
    for cookie_data in cookies_list:
        session.cookies.set(
            name=cookie_data["name"],
            value=cookie_data["value"],
            domain=cookie_data.get("domain", ""),
            path=cookie_data.get("path", "/"),
            expires=cookie_data.get("expires"),
            secure=cookie_data.get("secure", False),
        )


class SessionManager:
    """Class-based wrapper for session management.
    Matches the import pattern used in main.py.
    """

    @staticmethod
    def save_session(session) -> bool:
        return save_session(session)

    @staticmethod
    def load_session() -> list:
        return load_session()

    @staticmethod
    def has_session() -> bool:
        return has_session()

    @staticmethod
    def clear_all() -> bool:
        return clear_all()

    @staticmethod
    def restore_cookies_to_session(session, cookies_list: list) -> None:
        return restore_cookies_to_session(session, cookies_list)
