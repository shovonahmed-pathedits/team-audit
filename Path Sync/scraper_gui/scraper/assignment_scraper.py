"""Core scraping engine with proper Tista API authentication."""

import json
import logging
import os
import re
import csv
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup

from config import (
    APP_NAME,
    BASE_URL,
    OUTPUT_DIR,
    DEFAULT_LOCATION_ID,
    ASSIGNMENT_URL_PATTERN,
    SERVICE_CATEGORY_MAPPING,
    SM_DISPLAY_NAMES,
    resolve_sm_display_name,
    is_known_sm,
    safe_str,
    SYSTEM_USERS,
    SYSTEM_USER_LABELS,
    REQUEST_TIMEOUTS,
    PARALLEL_CONFIG,
    VENDOR_3KEY_MAPPING,
)
from logger import logger
from scraper.parsers import (
    parse_header,
    parse_history,
    format_date,
    calculate_week,
    normalize_note_text,
    extract_locations_from_files_filter,
    normalize_vendor_name,
)
from utils.validators import validate_url_list, validate_assignment_url

# Import credential and session managers (with fallback)
try:
    from credentials import CredentialManager
except Exception:
    CredentialManager = None

try:
    from session_manager import SessionManager
except Exception:
    SessionManager = None


class AssignmentScraper:
    """Core scraping engine with proper Tista API authentication."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept": "text/html, application/xhtml+xml",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/users/sign_in",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        )

        self._stored_email = ""
        self._stored_pwd = ""
        self._current_user_full_name = ""
        self.progress_callback = None
        self.csrf_token = None
        self.csrf_param = "authenticity_token"
        self.is_authenticated = False

        # Load saved session cookies
        try:
            saved_cookies = SessionManager.load_session()
            if saved_cookies:
                self.session.cookies.update(saved_cookies)
                logger.info("Loaded saved session cookies")
        except Exception as e:
            pass

        # Load stored credentials
        try:
            if CredentialManager and CredentialManager.has_credentials():
                self._stored_email = CredentialManager.get_email()
                self._stored_pwd = CredentialManager.get_password()
                logger.info("Loaded stored credentials from Windows Credential Manager")
        except Exception as e:
            pass

    def set_progress(self, callback):
        self.progress_callback = callback

    def _log(self, msg):
        """Legacy log wrapper — forwards to structured logger and progress callback."""
        # Parse prefix for structured logging
        level = logging.INFO
        text = msg
        if msg.startswith("[OK] "):
            level = logging.INFO
            text = msg[5:]
        elif msg.startswith("[FAIL] "):
            level = logging.ERROR
            text = msg[7:]
        elif msg.startswith("[WARN] "):
            level = logging.WARNING
            text = msg[7:]
        elif msg.startswith("[INFO] "):
            level = logging.INFO
            text = msg[7:]
        elif msg.startswith("DEBUG: ") or msg.startswith("WARNING: "):
            level = logging.DEBUG
        logger.log(level, text)

        if self.progress_callback:
            self.progress_callback(msg)

    def _is_session_valid(self) -> bool:
        """Quick check if session is still valid."""
        try:
            r = self.session.get(
                f"{BASE_URL}/users/profile",
                timeout=REQUEST_TIMEOUTS["session_validate"],
            )
            return r.status_code == 200
        except Exception:
            return False

    def validate_session(self) -> Tuple[bool, str]:
        """Validate existing session without full login.

        Returns:
            Tuple of (is_valid, message)
        """
        try:
            logger.info("Validating existing session...")
            if not self.session.cookies:
                return False, "No session cookies found"

            # Quick check to profile endpoint
            resp = self.session.get(
                f"{BASE_URL}/users/profile",
                timeout=REQUEST_TIMEOUTS["session_validate"],
                allow_redirects=False,
            )

            # Valid session returns 200, expired returns redirect to login
            if resp.status_code == 200:
                logger.info("Session validation successful")
                self.is_authenticated = True
                return True, "Session valid"
            elif resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "")
                if "sign_in" in location.lower():
                    logger.info("Session expired - redirected to login")
                    return False, "Session expired"
                else:
                    # Redirect to non-login page is OK
                    logger.info("Session valid (redirect to dashboard)")
                    self.is_authenticated = True
                    return True, "Session valid"
            else:
                logger.warning(f"Unexpected status code: {resp.status_code}")
                return False, f"Unexpected response: {resp.status_code}"

        except requests.exceptions.Timeout:
            logger.error("Session validation timeout")
            return False, "Validation timeout"
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False, str(e)

    def ensure_logged_in(self) -> Tuple[bool, str]:
        """Lazy authentication — checks session validity, auto-relogin if needed."""
        if self._is_session_valid():
            logger.info("Session valid - using existing session")
            self.is_authenticated = True
            if not self._current_user_full_name:
                self._current_user_full_name = self.fetch_user_profile(
                    force_refresh=True
                )
            return True, "Session valid"

        logger.info("Session expired or not authenticated")

        if not self._stored_email or not self._stored_pwd:
            logger.warning("No stored credentials - need manual login")
            return False, "No stored credentials"

        logger.info("Attempting auto-relogin with stored credentials...")
        success, msg = self.login(self._stored_email, self._stored_pwd)
        if success:
            logger.info("Auto-relogin successful")
        else:
            logger.error(f"Auto-relogin failed: {msg}")

        return success, msg

    def _get_csrf(self) -> bool:
        """Fetch login page and extract CSRF token."""
        try:
            logger.info("Fetching login page for CSRF token...")
            response = self.session.get(
                f"{BASE_URL}/users/sign_in", timeout=REQUEST_TIMEOUTS["login_page"]
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch login page: {response.status_code}")
                return False

            soup = BeautifulSoup(response.text, "html.parser")

            # Method 1: meta tag with csrf-token
            csrf_meta = soup.find("meta", {"name": "csrf-token"})
            if csrf_meta:
                self.csrf_token = csrf_meta.get("content")
                logger.info("CSRF token retrieved from meta tag")
                return True

            # Method 2: input field with authenticity_token
            token_input = soup.find("input", {"name": "authenticity_token"})
            if token_input:
                self.csrf_token = token_input.get("value")
                logger.info("CSRF token retrieved from input field")
                return True

            # Method 3: csrf-param meta
            csrf_param_meta = soup.find("meta", {"name": "csrf-param"})
            if csrf_param_meta:
                self.csrf_param = csrf_param_meta.get("content", "authenticity_token")
                token_input = soup.find("input", {"name": self.csrf_param})
                if token_input:
                    self.csrf_token = token_input.get("value")
                    logger.info(
                        f"CSRF token retrieved from input (param: {self.csrf_param})"
                    )
                    return True

            logger.error("CSRF token not found in login page")
            return False

        except Exception as e:
            logger.error(f"Error fetching CSRF token: {str(e)}")
            return False

    def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Authenticate with Tista using proper session handling."""
        try:
            logger.info("Attempting login...")

            if not self._get_csrf():
                return False, "Failed to retrieve authentication token"

            turbo_request_id = str(uuid.uuid4())
            login_data = {
                self.csrf_param: self.csrf_token,
                "user[email]": email,
                "user[password]": password,
                "user[remember_me]": "0",
                "commit": "Log in",
            }

            headers = {
                "x-csrf-token": self.csrf_token,
                "x-turbo-request-id": turbo_request_id,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/users/sign_in",
            }

            response = self.session.post(
                f"{BASE_URL}/users/sign_in",
                data=login_data,
                headers=headers,
                timeout=REQUEST_TIMEOUTS["login_post"],
                allow_redirects=False,
            )

            logger.info(f"Login response: HTTP {response.status_code}")

            if response.status_code in [302, 303]:
                redirect_url = response.headers.get("Location", "")
                logger.info(f"Following redirect: {redirect_url}")

                follow_response = self.session.get(
                    redirect_url
                    if redirect_url.startswith("http")
                    else f"{BASE_URL}{redirect_url}",
                    timeout=REQUEST_TIMEOUTS["login_post"],
                    allow_redirects=True,
                )

                logger.info(f"Redirect final URL: {follow_response.url}")

                if (
                    "sign_in" not in follow_response.url.lower()
                    and "login" not in follow_response.url.lower()
                ):
                    self.is_authenticated = True
                    logger.info("Login successful!")
                    self._current_user_full_name = self.fetch_user_profile(
                        force_refresh=True
                    )
                    self._post_login_success(email, password)
                    return True, "Login successful"
                else:
                    logger.info("Redirected back to login page - invalid credentials")
                    return False, "Invalid email or password"

            elif response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                alert = soup.find("div", class_="alert") or soup.find(
                    "p", class_="alert"
                )
                if alert and (
                    "invalid" in alert.text.lower() or "incorrect" in alert.text.lower()
                ):
                    logger.error("Login failed - invalid credentials")
                    return False, "Invalid email or password"

                if "sign_in" in response.url.lower() or "login" in response.url.lower():
                    logger.error("Still on login page - authentication failed")
                    return False, "Invalid email or password"

                self.is_authenticated = True
                logger.info("Login successful!")
                self._current_user_full_name = self.fetch_user_profile(
                    force_refresh=True
                )
                self._post_login_success(email, password)
                return True, "Login successful"

            else:
                error_msg = f"Login failed: HTTP {response.status_code}"
                logger.error(error_msg)
                return False, error_msg

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during login: {str(e)}")
            return False, f"Network error: {str(e)}"
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            return False, f"Error: {str(e)}"

    def _post_login_success(self, email: str, password: str) -> None:
        """Handle session/credential persistence after successful login."""
        try:
            if SessionManager:
                SessionManager.save_session(self.session)
                logger.info("Session cookies saved")
        except Exception as e:
            logger.warning(f"Could not save session: {e}")

        try:
            self._stored_email = email
            self._stored_pwd = password
            if CredentialManager:
                CredentialManager.save(email, password)
                logger.info("Credentials saved to Windows Credential Manager")
        except Exception as e:
            logger.warning(f"Could not save credentials: {e}")

        # SECURITY: Clear password from memory after saving to secure storage
        self._stored_pwd = ""

    @staticmethod
    def parse_url(url: str) -> Optional[str]:
        """Parse assignment URL and extract only the assignment ID.

        Returns:
            Assignment ID string, or None if URL doesn't match.
            Location ID is NO longer extracted here — use discover_loc_id() instead.
        """
        match = ASSIGNMENT_URL_PATTERN.match(url.strip())
        return match.group("assignment_id") if match else None

    def discover_loc_id(self, asn_id: str, _cache: Dict[str, str] = None) -> str:
        """Dynamically discover the location ID for an assignment.

        Strategy (in priority order):
        1. Fetch the assignment detail page and extract loc_id from href/action URLs
        2. Fetch user profile and extract default location/team ID
        3. Fall back to DEFAULT_LOCATION_ID from config

        FIX H2: Cache uses per-assignment key (asn_id) instead of single shared key,
        so different assignments with different location IDs are handled correctly.
        """
        # FIX H2: Check per-assignment cache first
        if _cache is not None and asn_id in _cache:
            cached = _cache[asn_id]
            logger.debug(f"Using cached loc_id={cached} for assignment {asn_id}")
            return cached

        # Strategy 1: Extract from assignment detail page (reduced timeout)
        try:
            resp = self.session.get(
                f"{BASE_URL}/team_coordinator/assignment_details/{asn_id}",
                timeout=REQUEST_TIMEOUTS["discover_loc"],
            )
            if resp.status_code == 200:
                # Look for location ID in URLs like /team_coordinator/{loc_id}/...
                loc_match = re.search(r"/team_coordinator/(\d+)/", resp.text)
                if loc_match:
                    found_id = loc_match.group(1)
                    logger.info(
                        f"Discovered loc_id={found_id} from assignment detail page"
                    )
                    if _cache is not None:
                        _cache[asn_id] = found_id  # FIX H2: Use asn_id as cache key
                    return found_id
        except Exception as e:
            logger.warning(
                f"Failed to discover loc_id from detail page for {asn_id}: {e}"
            )

        # Strategy 2: Try user profile (reduced timeout)
        try:
            profile_resp = self.session.get(
                f"{BASE_URL}/users/profile", timeout=REQUEST_TIMEOUTS["profile"]
            )
            if profile_resp.status_code == 200:
                # Look for location/team ID in the profile page
                profile_loc = re.search(
                    r"(?:location|team|department)[^\d]*(\d{3,5})",
                    profile_resp.text,
                    re.IGNORECASE,
                )
                if profile_loc:
                    found_id = profile_loc.group(1)
                    logger.info(f"Discovered loc_id={found_id} from user profile")
                    if _cache is not None:
                        _cache[asn_id] = found_id  # FIX H2: Use asn_id as cache key
                    return found_id
        except Exception as e:
            logger.warning(
                f"Failed to discover loc_id from user profile for {asn_id}: {e}"
            )

        # Strategy 3: Fallback to configured default
        fallback_id = DEFAULT_LOCATION_ID
        logger.warning(
            f"Could not discover loc_id dynamically for assignment {asn_id}, using default: {fallback_id}"
        )
        if _cache is not None:
            _cache[asn_id] = fallback_id  # FIX H2: Use asn_id as cache key
        return fallback_id

    def fetch_data(self, loc_id: str, asn_id: str) -> Dict:
        """Fetch assignment header and history data with Turbo Stream headers."""
        hdr = ""

        # Load assignment details page first — required for turbo-frame session context
        try:
            self.session.get(
                f"{BASE_URL}/team_coordinator/assignment_details/{asn_id}",
                timeout=REQUEST_TIMEOUTS["data_fetch"],
            )
        except Exception as e:
            logger.warning(f"Warning loading context: {str(e)}")

        # Fetch header via Turbo Stream API endpoint
        try:
            turbo_headers = {
                "turbo-frame": f"order_assignment_{asn_id}_header",
                "x-turbo-request-id": str(uuid.uuid4()),
            }

            r = self.session.get(
                f"{BASE_URL}/team_coordinator/{loc_id}/assignment_header/{asn_id}",
                headers=turbo_headers,
                timeout=REQUEST_TIMEOUTS["discover_loc"],
            )
            if r.status_code == 200:
                hdr = r.text
            elif r.status_code == 500:
                logger.warning(f"Header endpoint returned 500 for assignment {asn_id}")
            else:
                logger.warning(
                    f"Header endpoint returned HTTP {r.status_code} for assignment {asn_id}"
                )
        except Exception as e:
            logger.error(f"Error fetching header: {str(e)}")

        if not hdr:
            logger.warning(f"Could not fetch header data for assignment {asn_id}")

        his = ""
        try:
            r = self.session.get(
                f"{BASE_URL}/team_coordinator/{loc_id}/assignments/{asn_id}/history",
                timeout=REQUEST_TIMEOUTS["discover_loc"],
            )
            if r.status_code == 200:
                his = r.text
        except Exception as e:
            logger.error(f"Error fetching history: {str(e)}")

        return {"header_html": hdr, "history_html": his}

    def fetch_order_files_html(self, order_id: str) -> str:
        """Fetch HTML content of /orders/{order_id}/files."""
        try:
            if not order_id or not str(order_id).strip():
                return ""
            
            url = f"{BASE_URL}/orders/{order_id}/files"
            logger.info(f"Fetching files page HTML: {url}")
            
            response = self.session.get(url, timeout=REQUEST_TIMEOUTS["data_fetch"])
            if response.status_code == 200:
                return response.text
            
            logger.warning(f"Failed to fetch files page: HTTP {response.status_code}")
            return ""
        except Exception as e:
            logger.error(f"Error fetching files page HTML: {str(e)}")
            return ""

    def fetch_order_assignments_json(self, order_id: str) -> List[Dict]:
        """Fetch /orders/{order_id}/order_assignments.json to check for multi-vendor status."""
        try:
            if not order_id or not str(order_id).strip():
                return []
            
            url = f"{BASE_URL}/orders/{order_id}/order_assignments.json"
            logger.info(f"Checking multi-vendor status via API: {url}")
            
            response = self.session.get(url, timeout=REQUEST_TIMEOUTS["data_fetch"])
            if response.status_code == 200:
                data = response.json()
                logger.info(f"API returned {len(data)} assignments for order {order_id}")
                return data
            
            logger.warning(f"Failed to fetch order assignments: HTTP {response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error fetching order assignments JSON: {str(e)}")
            return []

    def fetch_order_items(self, order_id: str) -> Tuple[Dict[int, int], str, List[int]]:
        """Fetch /orders/{order_id}/files.json for service counts, SM layer-1 candidate, and unique assignment IDs."""
        try:
            if not order_id or not str(order_id).strip():
                logger.warning(f"Order ID is empty or invalid: '{order_id}'")
                return {}, "", []

            order_id = str(order_id).strip()
            logger.info(f"Fetching order items for order ID: {order_id}...")

            url = f"{BASE_URL}/orders/{order_id}/files.json"
            logger.info(f"Request URL: {url}")

            response = self.session.get(url, timeout=REQUEST_TIMEOUTS["data_fetch"])
            logger.info(f"HTTP Status: {response.status_code}")

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch order items: HTTP {response.status_code}"
                )
                logger.debug(f"Response text (first 500 chars): {response.text[:500]}")
                return {}, "", []

            try:
                items = response.json()
                logger.info(
                    f"Successfully parsed JSON. Found {len(items)} items in response"
                )
            except Exception as e:
                logger.error(f"Failed to parse JSON: {str(e)}")
                logger.debug(f"Response text: {response.text[:500]}")
                return {}, "", []

            item_counts = {}
            sm_candidate_original = ""
            sm_candidate_any = ""
            original_task_count = 0
            non_original_task_count = 0
            task_types_found = set()
            unique_assignment_ids = set()

            for idx, item in enumerate(items):
                # Capture unique assignment IDs from each item
                asn_id = item.get("orderAssignmentId")
                if asn_id:
                    unique_assignment_ids.add(asn_id)

                if "itemTasks" in item and isinstance(item["itemTasks"], list):
                    for task in item["itemTasks"]:
                        task_type = task.get("taskType", "")
                        task_types_found.add(task_type)
                        created_by_username = (
                            (task.get("createdBy") or {}).get("username") or ""
                        ).strip()

                        if task_type == "original" and "serviceCategoryId" in task:
                            service_cat_id = task["serviceCategoryId"]
                            item_counts[service_cat_id] = (
                                item_counts.get(service_cat_id, 0) + 1
                            )
                            original_task_count += 1
                            if (
                                created_by_username
                                and created_by_username.lower() not in SYSTEM_USERS
                                and not sm_candidate_original
                            ):
                                sm_candidate_original = created_by_username
                        else:
                            non_original_task_count += 1

                        if (
                            created_by_username
                            and created_by_username.lower() not in SYSTEM_USERS
                            and not sm_candidate_any
                        ):
                            sm_candidate_any = created_by_username

            logger.info(
                f"Processed {len(items)} items. Found {len(item_counts)} unique service categories"
            )
            if item_counts:
                logger.info(f"Service category counts: {item_counts}")

            logger.info(
                f"Task type analysis: {original_task_count} original, {non_original_task_count} non-original"
            )
            logger.info(f"Task types found in response: {task_types_found}")
            
            assignment_id_list = sorted(list(unique_assignment_ids))
            logger.info(f"[OK] Unique Assignment IDs in files: {assignment_id_list}")

            if original_task_count == 0 and non_original_task_count > 0:
                logger.warning(
                    "No 'original' tasks found - using all tasks as fallback"
                )
                # FIX H3: Clear item_counts before re-counting to prevent double-counting
                item_counts = {}
                for idx, item in enumerate(items):
                    if "itemTasks" in item and isinstance(item["itemTasks"], list):
                        for task in item["itemTasks"]:
                            if "serviceCategoryId" in task:
                                service_cat_id = task["serviceCategoryId"]
                                item_counts[service_cat_id] = (
                                    item_counts.get(service_cat_id, 0) + 1
                                )

            if not item_counts:
                logger.warning("Could not find any service categories in order items")
                layer1_sm = sm_candidate_original or sm_candidate_any
                if layer1_sm:
                    logger.info(f"[OK] SM layer-1 from itemTasks: {layer1_sm}")
                return {}, layer1_sm, assignment_id_list

            logger.info(
                f"[OK] Found {len(item_counts)} service types with {sum(item_counts.values())} total images"
            )
            layer1_sm = sm_candidate_original or sm_candidate_any
            if layer1_sm:
                logger.info(f"[OK] SM layer-1 from itemTasks: {layer1_sm}")
            return item_counts, layer1_sm, assignment_id_list
        except Exception as e:
            logger.error(f"Error fetching order items: {str(e)}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return {}, "", []

    def resolve_sm_name(self, itemtasks_sm: str, history_data: Dict) -> str:
        """Resolve SM using the new 3-Layer Priority System.

        Layer 1: itemTasks createdBy (from order items JSON)
        Layer 2: History (Before Creation)
        Layer 3: History (After Creation / Full Fallback)
        """
        # Layer 1: itemTasks createdBy (from order items JSON)
        candidate = (itemtasks_sm or "").strip()
        if candidate and is_known_sm(candidate):
            logger.info(f"[OK] SM resolved from Layer 1 (itemTasks): {candidate}")
            return candidate

        # Layer 2: History BEFORE creation
        candidate = (history_data.get("layer2_sm", "") or "").strip()
        if candidate and is_known_sm(candidate):
            logger.info(f"[OK] SM resolved from Layer 2 (Before Creation): {candidate}")
            return candidate

        # Layer 3: History AFTER creation or FULL fallback
        candidate = (history_data.get("layer3_sm", "") or "").strip()
        if candidate and is_known_sm(candidate):
            logger.info(f"[OK] SM resolved from Layer 3 (After/Full Fallback): {candidate}")
            return candidate

        logger.warning("No valid SM found across all layers")
        return ""

    def fetch_user_profile(self, force_refresh: bool = False) -> str:
        """Fetch current user profile and cache full name for auditor."""
        try:
            if self._current_user_full_name and not force_refresh:
                return self._current_user_full_name

            logger.info("Fetching user profile...")
            response = self.session.get(
                f"{BASE_URL}/users/profile",
                timeout=REQUEST_TIMEOUTS["profile"],
            )

            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch user profile: HTTP {response.status_code}"
                )
                return ""

            soup = BeautifulSoup(response.text, "html.parser")

            candidates = []
            for selector in ["h1.font-weight-bold.mb-1", "h1.font-weight-bold", "h1"]:
                for node in soup.select(selector):
                    text = node.get_text(" ", strip=True)
                    text = re.sub(r"\s+", " ", text).strip()
                    if text:
                        candidates.append(text)
                if candidates:
                    break

            invalid_labels = SYSTEM_USER_LABELS
            full_name = ""
            for c in candidates:
                lower = c.lower()
                if lower in invalid_labels:
                    continue
                if len(c.split()) >= 2:
                    full_name = c
                    break
                if not full_name:
                    full_name = c

            if full_name:
                self._current_user_full_name = full_name
                logger.info(f"[OK] Auditor: {full_name}")
                return full_name

            logger.warning("Could not find user full name in profile")
            return ""
        except Exception as e:
            logger.error(f"Error fetching user profile: {str(e)}")
            return ""

    def get_current_user_full_name(self) -> str:
        """Return cached logged-in user's full name (refresh if needed)."""
        if self._current_user_full_name:
            return self._current_user_full_name
        return self.fetch_user_profile(force_refresh=True)

    def scrape_one(
        self,
        url: str,
        loc_id_cache: Dict[str, str] = None,
        auditor_name: str = "",
        pause_event=None,
        stop_check=None,
    ) -> List[Dict]:
        """Scrape a single assignment and generate one row per service type.

        PERF FIX: Removed redundant ensure_logged_in() - already called by scrape_bulk().
        PERF FIX: Accept cached loc_id_cache and auditor_name to avoid redundant HTTP calls.
        """

        def _yield_to_pause():
            if pause_event is not None:
                while not pause_event.wait(0.1):
                    if stop_check is not None and stop_check():
                        return False
                if stop_check is not None and stop_check():
                    return False
            elif stop_check is not None and stop_check():
                return False
            return True

        try:
            logger.info(f"Scraping URL: {url}")

            asn = self.parse_url(url)
            if not asn:
                logger.error("Invalid URL - no assignment ID")
                return [{"error": "Invalid URL", "url": url}]
            if not _yield_to_pause():
                logger.info("Scrape interrupted after parse_url")
                return []

            # PERF FIX: Use cached loc_id if available
            loc = self.discover_loc_id(asn, _cache=loc_id_cache)
            logger.info(f"Fetching assignment {asn} (loc={loc})")
            if not _yield_to_pause():
                logger.info("Scrape interrupted after discover_loc_id")
                return []

            raw = self.fetch_data(loc, asn)
            if not _yield_to_pause():
                logger.info("Scrape interrupted after fetch_data")
                return []

            header_data = parse_header(
                raw.get("header_html", ""), asn, log_func=self._log
            )
            history_data = parse_history(
                raw.get("history_html", ""), log_func=self._log
            )

            internal_order_id = header_data.get("internal_order_id", "")
            logger.debug(f"Internal order ID from header: '{internal_order_id}'")

            rows = []

            item_counts = {}
            itemtasks_sm_candidate = ""
            unique_assignment_ids = []
            if internal_order_id:
                logger.debug(
                    f"Calling fetch_order_items with internal_order_id='{internal_order_id}'"
                )
                item_counts, itemtasks_sm_candidate, unique_assignment_ids = self.fetch_order_items(
                    internal_order_id
                )
                if not _yield_to_pause():
                    logger.info("Scrape interrupted after fetch_order_items")
                    return []
            else:
                logger.debug("internal_order_id is empty, skipping fetch_order_items")

            # PERF FIX: Use pre-resolved auditor name from scrape_bulk
            auditor_full_name = auditor_name or history_data.get("auditor", "")
            auditor_first_name = (
                auditor_full_name.split()[0] if auditor_full_name else ""
            )

            received_date = header_data.get("received", "")
            formatted_date = format_date(received_date)
            week_num = calculate_week(received_date)

            # --- Senior Refactor: Definitive Multi-Vendor Logic (API-Driven) ---
            final_order_number = header_data.get("order_number", "")
            primary_vendor_raw = header_data.get("subcontractor", "")
            
            try:
                # Trigger suffix if multiple assignment IDs are found in the files list
                is_multi_vendor = len(unique_assignment_ids) > 1
                
                # Fallback: Double check via dedicated assignments API if needed
                if not is_multi_vendor and internal_order_id:
                    assignments_api = self.fetch_order_assignments_json(internal_order_id)
                    if len(assignments_api) > 1:
                        is_multi_vendor = True
                        if self._log:
                            self._log(f"[DEBUG] Multi-vendor confirmed via Assignments API.")

                if is_multi_vendor:
                    if self._log:
                        self._log(f"[DEBUG] Multi-vendor order detected (IDs: {unique_assignment_ids}).")
                    
                    primary_vendor_norm = normalize_vendor_name(primary_vendor_raw)
                    primary_code = ""
                    
                    # Lookup the primary vendor's shortcode using normalized matching
                    for v_full_name, code in VENDOR_3KEY_MAPPING.items():
                        if normalize_vendor_name(v_full_name) == primary_vendor_norm:
                            primary_code = code
                            break
                    
                    if primary_code:
                        final_order_number = f"{final_order_number}-{primary_code}"
                        if self._log:
                            self._log(f"[OK] Multi-vendor detected. Final Order #: {final_order_number}")
                    else:
                        if self._log:
                            self._log(f"[WARN] Multi-vendor detected but no shortcode for: {primary_vendor_raw}")
                else:
                    if self._log:
                        self._log("[DEBUG] Single vendor order. Standard Order # used.")

            except Exception as e:
                # SAFETY: Log the error but DO NOT fail the entire scrape
                logger.error(f"Error in multi-vendor logic (non-blocking): {str(e)}")
                if self._log:
                    self._log(f"[ERROR] Multi-vendor logic failed: {str(e)}. Using default Order #.")

            sm_name_resolved = self.resolve_sm_name(
                itemtasks_sm_candidate, history_data
            )
            logger.debug(
                f"SM resolution -> "
                f"Layer 1(itemTasks)='{itemtasks_sm_candidate}', "
                f"Layer 2(Before Creation)='{history_data.get('layer2_sm', '')}', "
                f"Layer 3(After/Full Fallback)='{history_data.get('layer3_sm', '')}', "
                f"Final='{sm_name_resolved}'"
            )

            service_type_groups = {}

            if item_counts:
                for service_cat_id, task_count in item_counts.items():
                    if service_cat_id in SERVICE_CATEGORY_MAPPING:
                        service_name, category_level, _ = SERVICE_CATEGORY_MAPPING[
                            service_cat_id
                        ]
                    else:
                        service_name = f"Unmapped Service ({service_cat_id})"
                        category_level = "-"
                        logger.warning(
                            f"Unknown service category ID {service_cat_id}; using fallback label"
                        )

                    if service_name not in service_type_groups:
                        service_type_groups[service_name] = {
                            "count": 0,
                            "level": category_level,
                        }

                    service_type_groups[service_name]["count"] += task_count

                    try:
                        current_level = (
                            float(service_type_groups[service_name]["level"])
                            if service_type_groups[service_name]["level"] != "-"
                            else 0
                        )
                        new_level = (
                            float(category_level) if category_level != "-" else 0
                        )
                        if new_level > current_level:
                            service_type_groups[service_name]["level"] = category_level
                    except (ValueError, TypeError):
                        pass

            if service_type_groups:
                for service_name, service_data in service_type_groups.items():
                    row = {
                        "scraped_at": datetime.now().isoformat(),
                        "url": url,
                        "assignment_id": asn,
                        "location_id": loc,
                        "date": formatted_date,
                        "auditor": auditor_first_name,
                        "week": week_num,
                        "subcontractor": primary_vendor_raw,
                        "order_number": final_order_number,
                        "service_type": service_name,
                        "image_count": service_data["count"],
                        "match": "Yes",
                        "category_level": service_data["level"],
                        "sm_name": sm_name_resolved,
                        "return_format": header_data.get("return_format", ""),
                        "comments": header_data.get("comments", ""),
                        "notes": header_data.get("notes", ""),
                    }
                    rows.append(row)
            else:
                logger.warning(f"No service types found for assignment {asn}")
                fallback_count = sum(item_counts.values()) if item_counts else 0
                rows.append(
                    {
                        "scraped_at": datetime.now().isoformat(),
                        "url": url,
                        "assignment_id": asn,
                        "location_id": loc,
                        "date": formatted_date,
                        "auditor": auditor_first_name,
                        "week": week_num,
                        "subcontractor": primary_vendor_raw,
                        "order_number": final_order_number,
                        "service_type": "N/A",
                        "image_count": fallback_count,
                        "match": "Yes",
                        "category_level": "-",
                        "sm_name": sm_name_resolved,
                        "return_format": header_data.get("return_format", ""),
                        "comments": header_data.get("comments", ""),
                        "notes": header_data.get("notes", ""),
                    }
                )
                logger.info(
                    f"Added fallback row for assignment {asn} (image_count={fallback_count})"
                )

            logger.info(f"[OK] Generated {len(rows)} rows for assignment {asn}")
            return rows

        except Exception as e:
            # FIX: Catch ALL exceptions and return error row instead of crashing
            import traceback

            logger.error(f"EXCEPTION in scrape_one for {url}: {e}")
            logger.error(traceback.format_exc())
            return [{"error": f"Scrape error: {str(e)}", "url": url}]

    def scrape_bulk(
        self,
        urls: List[str],
        email: str,
        pwd: str,
        progress_callback=None,
        pause_event=None,
        stop_check=None,
    ) -> List[Dict]:
        """Scrape multiple assignments with lazy authentication."""
        logger.info(f"Starting bulk scrape for {len(urls)} URLs")
        logger.info(f"URLs to scrape: {urls}")

        if email and pwd:
            self._stored_email = email
            self._stored_pwd = pwd
            if CredentialManager:
                CredentialManager.save(email, pwd)
                logger.info("Saved credentials")

        logger.info(
            f"Stored email: '{self._stored_email}', has password: {bool(self._stored_pwd)}"
        )
        ok, msg = self.ensure_logged_in()
        logger.info(f"ensure_logged_in result: ok={ok}, msg='{msg}'")
        if not ok:
            logger.error(f"Initial login failed: {msg}")
            error_rows = [
                {"error": f"Authentication failed: {msg}", "url": u} for u in urls
            ]
            logger.info(f"Returning {len(error_rows)} error rows due to auth failure")
            return error_rows

        # Validate all URLs upfront
        valid_urls, invalid_urls = validate_url_list(urls)
        if invalid_urls:
            logger.warning(f"Found {len(invalid_urls)} invalid URLs")
        for inv in invalid_urls:
            logger.warning(f"Invalid URL: {inv['url']} - {inv['error']}")

        # PERF FIX: Cache loc_id (usually same for all assignments in bulk run)
        loc_id_cache: Dict[str, str] = {}

        # PERF FIX: Cache auditor name once (same user for entire bulk run)
        auditor_full_name = self.get_current_user_full_name()
        auditor_first_name = auditor_full_name.split()[0] if auditor_full_name else ""
        logger.info(f"Resolved auditor name: '{auditor_first_name}'")

        results = []
        seen_urls: set = set()  # Deduplication set

        for i, url in enumerate(urls):
            # Pause/resume check — responsive to both resume and terminate while paused
            if pause_event is not None:
                while not pause_event.wait(0.1):
                    if stop_check is not None and stop_check():
                        logger.info("Bulk scrape cancelled while paused")
                        return results

            # Stop/close check — clean exit on window close
            if stop_check is not None and stop_check():
                logger.info("Bulk scrape interrupted by user")
                break

            # Skip invalid URLs
            is_valid, _ = validate_assignment_url(url)
            if not is_valid:
                results.append({"error": "Invalid URL format", "url": url})
                continue

            # Deduplication: skip already processed URLs
            if url in seen_urls:
                logger.warning(f"Skipping duplicate URL: {url}")
                continue
            seen_urls.add(url)

            logger.info(f"Processing URL {i + 1}/{len(urls)}: {url}")

            if progress_callback:
                progress_callback(i + 1, len(urls))

            # Rate limiting: 2 second delay between requests, chunked for responsive pause/stop
            if i > 0:
                if pause_event is not None:
                    for _ in range(20):
                        if stop_check is not None and stop_check():
                            logger.info(
                                "Bulk scrape interrupted during rate-limit delay"
                            )
                            return results
                        if not pause_event.is_set():
                            pause_event.wait()
                        time.sleep(0.1)
                else:
                    time.sleep(2)

            # PERF FIX: Only check session validity every 5 assignments instead of every one
            # This reduces redundant /users/profile HTTP calls
            if i % 5 == 0 and i > 0:
                if not self._is_session_valid():
                    logger.info("Session expired mid-bulk, auto-relogging...")
                    ok, msg = self.ensure_logged_in()
                    if not ok:
                        logger.error(f"Auto-relogin failed: {msg}")
                        # FIX: Continue with remaining URLs instead of breaking
                        # Add error rows for remaining URLs so user knows what failed
                        for remaining_url in urls[i:]:
                            results.append(
                                {
                                    "error": f"Session expired and re-login failed: {msg}",
                                    "url": remaining_url,
                                }
                            )
                        break
                    # Refresh auditor name after re-login (user might be different)
                    auditor_full_name = self.get_current_user_full_name()
                    auditor_first_name = (
                        auditor_full_name.split()[0] if auditor_full_name else ""
                    )

            rows = self.scrape_one(
                url, loc_id_cache, auditor_first_name, pause_event, stop_check
            )
            logger.info(f"scrape_one returned {len(rows)} rows for {url}")
            results.extend(rows)

        logger.info(
            f"scrape_bulk returning {len(results)} total rows for {len(urls)} URLs"
        )
        return results

    def scrape_bulk_parallel(
        self,
        urls: List[str],
        email: str,
        pwd: str,
        progress_callback=None,
        max_workers: int = None,
        pause_event=None,
        stop_check=None,
    ) -> List[Dict]:
        """Scrape multiple assignments in PARALLEL using thread pool."""
        if max_workers is None:
            max_workers = PARALLEL_CONFIG["default_workers"]

        logger.info(
            f"Starting PARALLEL bulk scrape for {len(urls)} URLs with {max_workers} workers"
        )
        logger.info(f"URLs to scrape: {urls}")

        if email and pwd:
            self._stored_email = email
            self._stored_pwd = pwd
            if CredentialManager:
                CredentialManager.save(email, pwd)
                logger.info("Saved credentials")

        ok, msg = self.ensure_logged_in()
        logger.info(f"ensure_logged_in result: ok={ok}, msg='{msg}'")
        if not ok:
            logger.error(f"Initial login failed: {msg}")
            error_rows = [
                {"error": f"Authentication failed: {msg}", "url": u} for u in urls
            ]
            return error_rows

        # Validate URLs
        valid_urls, invalid_urls = validate_url_list(urls)
        for inv in invalid_urls:
            logger.warning(f"Invalid URL: {inv['url']} - {inv['error']}")

        # Prepare auditor
        auditor_full_name = self.get_current_user_full_name()
        auditor_first_name = auditor_full_name.split()[0] if auditor_full_name else ""
        logger.info(f"Resolved auditor name: '{auditor_first_name}'")

        # Pre-shared loc_id cache
        loc_id_cache: Dict[str, str] = {}

        # Process URLs in parallel using ThreadPoolExecutor — cancellable via pause_event/stop_check
        results = []
        completed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(
                    self.scrape_one,
                    url,
                    loc_id_cache,
                    auditor_first_name,
                    pause_event,
                    stop_check,
                ): url
                for url in valid_urls
            }

            while future_to_url:
                if stop_check is not None and stop_check():
                    logger.info("Parallel scrape interrupted by user")
                    for f in future_to_url:
                        f.cancel()
                    break

                if pause_event is not None:
                    while not pause_event.wait(0.1):
                        if stop_check is not None and stop_check():
                            logger.info("Parallel scrape cancelled while paused")
                            for f in future_to_url:
                                f.cancel()
                            return results

                done, pending = wait(
                    list(future_to_url.keys()),
                    timeout=0.3,
                    return_when="FIRST_COMPLETED",
                )

                for future in done:
                    url = future_to_url.pop(future)
                    completed_count += 1

                    if progress_callback:
                        progress_callback(completed_count, len(urls))

                    try:
                        rows = future.result()
                        logger.info(f"Parallel: {url} returned {len(rows)} rows")
                        results.extend(rows)
                    except Exception as e:
                        logger.error(f"Parallel error for {url}: {e}")
                        results.append({"error": str(e), "url": url})

                future_to_url = {f: future_to_url[f] for f in pending}

        logger.info(
            f"scrape_bulk_parallel returning {len(results)} total rows for {len(urls)} URLs"
        )
        return results

    def save_json(self, data: List[Dict], fname: str) -> str:
        """Save results to JSON."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        p = os.path.join(OUTPUT_DIR, fname)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return p

    def save_csv(self, data: List[Dict], fname: str) -> str:
        """Save results to CSV with all 12 columns."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        p = os.path.join(OUTPUT_DIR, fname)

        if not data:
            return p

        fieldnames = [
            "Date",
            "Auditor",
            "Week",
            "Subcontractor",
            "Order #",
            "Service Type",
            "Match",
            "Image Count",
            "SM Name",
            "Category Level",
            "Return Format",
            "Comments",
            "Notes",
        ]

        all_rows = []
        error_row_count = 0
        for item in data:
            if "error" in item:
                # FIX M7: Include error rows in CSV (consistent with JSON export)
                error_row_count += 1
                flat = {
                    "Date": "ERROR",
                    "Auditor": "",
                    "Week": "",
                    "Subcontractor": "",
                    "Order #": "",
                    "Service Type": f"ERROR: {item.get('error', 'Unknown')[:80]}",
                    "Match": "",
                    "Image Count": "",
                    "SM Name": "",
                    "Category Level": "",
                    "Return Format": "",
                    "Comments": "",
                    "Notes": f"URL: {item.get('url', 'Unknown')}",
                }
                all_rows.append(flat)
                continue

            flat = {
                "Date": item.get("date", ""),
                "Auditor": item.get("auditor", ""),
                "Week": item.get("week", ""),
                "Subcontractor": item.get("subcontractor", ""),
                "Order #": item.get("order_number", ""),
                "Service Type": item.get("service_type", ""),
                "Match": "Yes",
                "Image Count": item.get("image_count", ""),
                "SM Name": item.get("sm_name", ""),
                "Category Level": item.get("category_level", ""),
                "Return Format": item.get("return_format", ""),
                "Comments": item.get("comments", ""),
                "Notes": item.get("notes", ""),
            }
            all_rows.append(flat)

        if all_rows:
            with open(p, "w", newline="", encoding="utf-8") as w:
                writer = csv.DictWriter(w, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            if error_row_count > 0:
                logger.info(f"CSV export includes {error_row_count} error row(s)")
        return p
