"""
Tista API Client - Handles authentication, session management, and order requests
"""

import requests
import uuid
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from config import REQUEST_TIMEOUT, MAX_RETRIES, DEBUG_MODE
from api.endpoints import Endpoints
from utils.logger import app_logger, log_api_request, log_api_error


class TistaAPI:
    """Client for Tista API with session management"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept": "text/vnd.turbo-stream.html, text/html, application/xhtml+xml",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
                "Origin": Endpoints.BASE_URL,
                "Referer": f"{Endpoints.BASE_URL}/users/sign_in",
            }
        )
        self.is_authenticated = False
        self.csrf_token = None
        self.csrf_param = "authenticity_token"
        self.session_email = None  # Track email for current session
        self.session_saved_at = None  # Track when session was last saved

    def _get_login_page(self) -> bool:
        """Fetch login page to get CSRF token from meta tag"""
        try:
            app_logger.debug("Fetching login page for CSRF token...")
            response = self.session.get(
                f"{Endpoints.BASE_URL}/users/sign_in", timeout=REQUEST_TIMEOUT
            )

            log_api_request(
                "GET", f"{Endpoints.BASE_URL}/users/sign_in", response.status_code
            )

            if DEBUG_MODE:
                app_logger.debug(f"Login page status: {response.status_code}")
                app_logger.debug(f"Login page URL: {response.url}")
                app_logger.debug(
                    f"Cookies after GET: {list(self.session.cookies.keys())}"
                )

            response.raise_for_status()

            # Parse HTML to get CSRF token from meta tag
            soup = BeautifulSoup(response.text, "html.parser")

            # Method 1: Look for meta tag with csrf-token
            csrf_meta = soup.find("meta", {"name": "csrf-token"})
            if csrf_meta:
                self.csrf_token = csrf_meta.get("content")
                app_logger.info("CSRF token retrieved from meta tag")
                if DEBUG_MODE:
                    app_logger.debug(f"CSRF token: {self.csrf_token[:30]}...")
                return True

            # Method 2: Look for input field with authenticity_token
            token_input = soup.find("input", {"name": "authenticity_token"})
            if token_input:
                self.csrf_token = token_input.get("value")
                app_logger.info("CSRF token retrieved from input field")
                if DEBUG_MODE:
                    app_logger.debug(f"CSRF token: {self.csrf_token[:30]}...")
                return True

            # Method 3: Look for csrf-param meta to find the correct input name
            csrf_param_meta = soup.find("meta", {"name": "csrf-param"})
            if csrf_param_meta:
                self.csrf_param = csrf_param_meta.get("content", "authenticity_token")
                if DEBUG_MODE:
                    app_logger.debug(f"CSRF param name: {self.csrf_param}")

                # Now look for input with that name
                token_input = soup.find("input", {"name": self.csrf_param})
                if token_input:
                    self.csrf_token = token_input.get("value")
                    app_logger.info(
                        f"CSRF token retrieved from input (param: {self.csrf_param})"
                    )
                    return True

            app_logger.error("CSRF token not found in login page")
            if DEBUG_MODE:
                app_logger.debug("Looking for all meta tags with csrf...")
                for meta in soup.find_all("meta"):
                    if meta.get("name") and "csrf" in meta.get("name", "").lower():
                        app_logger.debug(
                            f"  Meta: name={meta.get('name')}, content={meta.get('content', '')[:50]}"
                        )
            return False

        except Exception as e:
            log_api_error("GET", f"{Endpoints.BASE_URL}/users/sign_in", str(e))
            return False

    def login(self, email: str, password: str) -> Tuple[bool, str]:
        """
        Authenticate with Tista

        Args:
            email: User email
            password: User password

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            app_logger.info(f"Attempting login for {email}")

            # Get CSRF token
            if not self._get_login_page():
                return False, "Failed to retrieve authentication token"

            # Generate turbo request ID
            turbo_request_id = str(uuid.uuid4())

            # Prepare login data
            login_data = {
                self.csrf_param: self.csrf_token,
                "user[email]": email,
                "user[password]": password,
                "user[remember_me]": "0",
                "commit": "Log in",
            }

            if DEBUG_MODE:
                app_logger.debug(f"Login payload keys: {list(login_data.keys())}")
                app_logger.debug(f"Turbo request ID: {turbo_request_id}")

            # Set additional headers for the login request
            headers = {
                "x-csrf-token": self.csrf_token,
                "x-turbo-request-id": turbo_request_id,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": Endpoints.BASE_URL,
                "Referer": f"{Endpoints.BASE_URL}/users/sign_in",
            }

            # Send login request
            response = self.session.post(
                f"{Endpoints.BASE_URL}/users/sign_in",
                data=login_data,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,  # Handle redirect manually
            )

            log_api_request(
                "POST", f"{Endpoints.BASE_URL}/users/sign_in", response.status_code
            )

            if DEBUG_MODE:
                app_logger.debug(f"Login response status: {response.status_code}")
                app_logger.debug(f"Login response headers: {dict(response.headers)}")
                app_logger.debug(
                    f"Login response body (first 500): {response.text[:500]}"
                )
                app_logger.debug(
                    f"Cookies after login: {list(self.session.cookies.keys())}"
                )

            # Check if login was successful
            # Successful login returns 301, 302 or 303 redirect to dashboard
            if response.status_code in [301, 302, 303]:
                redirect_url = response.headers.get("Location", "")
                app_logger.info(f"Login redirect: {redirect_url}")

                # Follow the redirect
                follow_response = self.session.get(
                    redirect_url
                    if redirect_url.startswith("http")
                    else f"{Endpoints.BASE_URL}{redirect_url}",
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )

                if DEBUG_MODE:
                    app_logger.debug(f"Redirect final URL: {follow_response.url}")
                    app_logger.debug(f"Redirect status: {follow_response.status_code}")

                # Check if we landed on dashboard (not login page)
                if (
                    "sign_in" not in follow_response.url.lower()
                    and "login" not in follow_response.url.lower()
                ):
                    self.is_authenticated = True
                    self.session_email = email
                    app_logger.info("Login successful!")
                    if DEBUG_MODE:
                        app_logger.debug(
                            f"Authenticated session cookies: {list(self.session.cookies.keys())}"
                        )
                    return True, "Login successful"
                else:
                    app_logger.warning(
                        "Redirected back to login page - authentication failed"
                    )
                    return False, "Invalid email or password"

            # If we got a 200, check the response content
            elif response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")

                # Check for error messages
                alert = soup.find("div", class_="alert") or soup.find(
                    "p", class_="alert"
                )
                if alert and (
                    "invalid" in alert.text.lower() or "incorrect" in alert.text.lower()
                ):
                    app_logger.warning("Login failed - invalid credentials")
                    return False, "Invalid email or password"

                # Check if we're still on login page
                if "sign_in" in response.url.lower() or "login" in response.url.lower():
                    app_logger.warning("Still on login page - authentication failed")
                    return False, "Invalid email or password"

                self.is_authenticated = True
                self.session_email = email
                app_logger.info("Login successful!")
                return True, "Login successful"

            else:
                error_msg = f"Login failed: HTTP {response.status_code}"
                app_logger.error(error_msg)
                if DEBUG_MODE:
                    app_logger.debug(
                        f"Response content (first 500 chars): {response.text[:500]}"
                    )
                return False, error_msg

        except requests.exceptions.RequestException as e:
            log_api_error("POST", f"{Endpoints.BASE_URL}/users/sign_in", str(e))
            return False, f"Network error: {str(e)}"
        except Exception as e:
            app_logger.error(f"Unexpected error during login: {e}")
            if DEBUG_MODE:
                import traceback

                app_logger.debug(traceback.format_exc())
            return False, f"Error: {str(e)}"

    def fetch_orders(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> Tuple[bool, Dict]:
        """
        Fetch orders from API with auto-relogin support

        Args:
            location_id: Filter by location ID
            start_date: Start date (DD/MM/YY)
            end_date: End date (DD/MM/YY)
            page: Page number
            per_page: Results per page

        Returns:
            Tuple of (success: bool, data: dict)
        """
        return self._ensure_authenticated(
            self._fetch_orders_internal,
            location_id,
            start_date,
            end_date,
            page,
            per_page,
        )

    def _fetch_orders_internal(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
    ) -> Tuple[bool, Dict]:
        """
        Internal fetch orders method (assumes authenticated)
        """

        try:
            url = Endpoints.orders_url(
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
                page=page,
                per_page=per_page,
            )

            app_logger.info(f"Fetching orders from: {url}")

            response = self.session.get(url, timeout=REQUEST_TIMEOUT)

            if DEBUG_MODE:
                app_logger.debug(f"Orders response status: {response.status_code}")
                app_logger.debug(f"Response content length: {len(response.text)} bytes")

            response.raise_for_status()

            data = response.json()

            orders_count = len(data.get("orders", []))
            meta = data.get("meta", {})
            pagination = meta.get("pagination", {})

            app_logger.info(f"Fetched {orders_count} orders (page {page})")

            if DEBUG_MODE:
                total_records = pagination.get("total_records", "N/A")
                total_pages = pagination.get("total_pages", "N/A")
                app_logger.debug(
                    f"Pagination: page {page}/{total_pages}, total records: {total_records}"
                )
                if orders_count > 0:
                    first_order = data["orders"][0]
                    app_logger.debug(f"Sample order keys: {list(first_order.keys())}")

            log_api_request("GET", url, response.status_code, str(data)[:500])

            return True, data

        except requests.exceptions.HTTPError as e:
            if "response" in dir():
                log_api_error("GET", url, f"{str(e)} - Response: {response.text[:500]}")
            else:
                log_api_error("GET", url, str(e))
            return False, {"error": f"HTTP error: {str(e)}"}
        except requests.exceptions.RequestException as e:
            log_api_error("GET", url, str(e))
            return False, {"error": str(e)}
        except Exception as e:
            app_logger.error(f"Error parsing orders: {e}")
            if DEBUG_MODE:
                import traceback

                app_logger.debug(traceback.format_exc())
            return False, {"error": str(e)}

    def fetch_all_orders(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        per_page: int = 100,
    ) -> Tuple[bool, List[Dict], Dict]:
        """
        Fetch all orders across all pages with auto-relogin support

        Args:
            location_id: Filter by location ID
            start_date: Start date (DD/MM/YY)
            end_date: End date (DD/MM/YY)
            per_page: Results per page

        Returns:
            Tuple of (success: bool, orders: list, meta: dict)
        """
        return self._ensure_authenticated(
            self._fetch_all_orders_internal, location_id, start_date, end_date, per_page
        )

    def _fetch_all_orders_internal(
        self,
        location_id: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        per_page: int = 100,
    ) -> Tuple[bool, List[Dict], Dict]:
        """
        Internal fetch all orders method (assumes authenticated)
        """
        all_orders = []
        meta = {}

        # Fetch first page to get pagination info
        success, data = self.fetch_orders(
            location_id=location_id,
            start_date=start_date,
            end_date=end_date,
            page=1,
            per_page=per_page,
        )

        if not success:
            return False, [], data

        # Parse first page
        orders = data.get("orders", [])
        meta = data.get("meta", {})
        all_orders.extend(orders)

        pagination = meta.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)

        app_logger.info(f"Total pages to fetch: {total_pages}")

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            success, data = self.fetch_orders(
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
                page=page,
                per_page=per_page,
            )

            if success:
                orders = data.get("orders", [])
                all_orders.extend(orders)
                app_logger.info(
                    f"Fetched page {page}/{total_pages} ({len(orders)} orders)"
                )
            else:
                app_logger.error(f"Failed to fetch page {page}")
                break

        app_logger.info(f"Total orders fetched: {len(all_orders)}")
        return True, all_orders, meta

    def fetch_locations(self) -> Tuple[bool, List[Dict]]:
        """
        Fetch available locations/vendors with auto-relogin support

        Returns:
            Tuple of (success: bool, locations: list)
        """
        return self._ensure_authenticated(self._fetch_locations_internal)

    def _fetch_locations_internal(self) -> Tuple[bool, List[Dict]]:
        """
        Internal fetch locations method (assumes authenticated)
        """

        try:
            app_logger.info("Fetching locations...")
            response = self.session.get(Endpoints.LOCATIONS, timeout=REQUEST_TIMEOUT)

            if DEBUG_MODE:
                app_logger.debug(f"Locations response status: {response.status_code}")
                app_logger.debug(
                    f"Response content (first 300 chars): {response.text[:300]}"
                )

            response.raise_for_status()

            data = response.json()
            locations = data if isinstance(data, list) else data.get("locations", [])

            app_logger.info(f"Fetched {len(locations)} locations")

            if DEBUG_MODE and locations:
                if isinstance(locations[0], dict):
                    app_logger.debug(
                        f"Sample location keys: {list(locations[0].keys())}"
                    )
                    app_logger.debug(f"Sample location: {locations[0]}")

            return True, locations

        except Exception as e:
            app_logger.error(f"Error fetching locations: {e}")
            if DEBUG_MODE:
                import traceback

                app_logger.debug(traceback.format_exc())
            return False, []

    def logout(self) -> bool:
        """Logout and clear session"""
        try:
            if self.is_authenticated:
                self.session.delete(
                    f"{Endpoints.BASE_URL}/users/sign_out",
                    timeout=REQUEST_TIMEOUT,
                    headers={"Referer": Endpoints.BASE_URL},
                )
            self.is_authenticated = False
            self.session.cookies.clear()
            self.csrf_token = None
            app_logger.info("Logged out successfully")
            return True
        except Exception as e:
            app_logger.error(f"Error during logout: {e}")
            return False

    # ==================== Session Persistence Methods ====================

    def _get_session_dir(self) -> str:
        """Get hidden session storage path in %APPDATA%"""
        import os

        appdata = os.environ.get("APPDATA", os.path.expanduser("~\\AppData\\Roaming"))
        session_dir = os.path.join(appdata, "OrderCollector", "sessions")
        os.makedirs(session_dir, exist_ok=True)
        return session_dir

    def save_session(self, email: str) -> bool:
        """
        Save session cookies to JSON file after successful login

        Args:
            email: User email for session identification

        Returns:
            True if successful, False otherwise
        """
        try:
            import os
            import json
            from datetime import datetime

            # Use hidden session directory in %APPDATA%
            session_dir = self._get_session_dir()

            # Export cookies to dict with metadata
            cookies_dict = requests.utils.dict_from_cookiejar(self.session.cookies)
            session_data = {
                "cookies": cookies_dict,
                "saved_at": datetime.now().isoformat(),
                "email": email,
            }

            # Save as plain JSON (OS-level protection via keyring for passwords)
            session_file = os.path.join(session_dir, f"session_{hash(email)}.json")
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2)

            app_logger.info(f"Session saved for {email}")
            self.session_email = email
            self.session_saved_at = datetime.now().isoformat()
            return True

        except Exception as e:
            app_logger.error(f"Failed to save session: {e}")
            return False

    def load_session(self, email: str) -> bool:
        """
        Load and restore session cookies from JSON file

        Args:
            email: User email to load session for

        Returns:
            True if session loaded successfully, False otherwise
        """
        try:
            import os
            import json

            session_dir = self._get_session_dir()
            session_file = os.path.join(session_dir, f"session_{hash(email)}.json")

            if not os.path.exists(session_file):
                app_logger.debug(f"No session file found for {email}")
                return False

            # Load session data
            with open(session_file, "r", encoding="utf-8") as f:
                session_data = json.load(f)

            cookies_dict = session_data.get("cookies", {})
            if not cookies_dict:
                app_logger.warning("No cookies found in session file")
                return False

            # Restore cookies
            requests.utils.add_dict_to_cookiejar(self.session.cookies, cookies_dict)

            self.is_authenticated = True
            self.session_email = email
            self.session_saved_at = session_data.get("saved_at")
            app_logger.info(f"Session loaded for {email}")
            return True

        except Exception as e:
            app_logger.error(f"Failed to load session: {e}")
            return False

    def validate_session(self) -> bool:
        """
        Ping test to check if session is still valid

        Returns:
            True if session is valid, False if expired
        """
        try:
            # Send request to protected endpoint
            response = self.session.get(
                f"{Endpoints.BASE_URL}/dashboard",
                timeout=5,
                allow_redirects=True,  # Follow redirects to see final destination
            )

            # Check if redirected to login page
            final_url = response.url.lower()
            if any(keyword in final_url for keyword in ["sign_in", "login", "auth"]):
                app_logger.debug(f"Session expired: redirected to {response.url}")
                return False

            # Check if response contains login page indicators
            if "sign_in" in response.text.lower() or "login" in response.text.lower():
                # Could be false positive, check for specific login page elements
                if "user[email]" in response.text or "user[password]" in response.text:
                    app_logger.debug("Session expired: login page detected in response")
                    return False

            # 200 OK and not login page = valid session
            return response.status_code == 200

        except Exception as e:
            app_logger.error(f"Session validation failed: {e}")
            return False

    def clear_session(self, email: str) -> None:
        """
        Delete session file and clear cookies

        Args:
            email: User email to clear session for
        """
        try:
            import os

            session_dir = self._get_session_dir()
            session_file = os.path.join(session_dir, f"session_{hash(email)}.json")

            if os.path.exists(session_file):
                os.remove(session_file)
                app_logger.info(f"Session cleared for {email}")

            self.is_authenticated = False
            self.session.cookies.clear()

        except Exception as e:
            app_logger.error(f"Error clearing session: {e}")

    # ==================== Auto-Relogin Feature ====================

    def _relogin_with_saved_credentials(self) -> bool:
        """
        Automatically re-login using saved credentials from Windows Credential Manager

        Returns:
            True if re-login successful, False otherwise
        """
        try:
            from utils.credential_manager import CredentialManager

            # Get saved email
            saved_email = CredentialManager.get_saved_email()
            if not saved_email:
                app_logger.warning("No saved email found for auto-relogin")
                return False

            app_logger.info(f"Attempting auto-relogin for {saved_email}...")

            # Get saved password
            saved_password = CredentialManager.get_password(saved_email)
            if not saved_password:
                app_logger.warning("No saved password found for auto-relogin")
                return False

            # Perform login
            success, message = self.login(saved_email, saved_password)

            if success:
                app_logger.info("Auto-relogin successful!")
                # Save new session
                self.save_session(saved_email)
                return True
            else:
                app_logger.warning(f"Auto-relogin failed: {message}")
                return False

        except Exception as e:
            app_logger.error(f"Auto-relogin error: {e}")
            return False

    def _ensure_authenticated(self, func, *args, **kwargs):
        """
        Wrapper to ensure user is authenticated before making API calls.
        If session expired, attempts auto-relogin.

        Args:
            func: The API method to call
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Result from the function call
        """
        # Check if authenticated
        if not self.is_authenticated:
            app_logger.warning("Not authenticated, attempting auto-relogin...")
            if not self._relogin_with_saved_credentials():
                app_logger.error("Auto-relogin failed, cannot proceed")
                # Return failure based on function type
                if func.__name__ == "fetch_locations":
                    return False, []
                elif func.__name__ in ["fetch_orders", "fetch_all_orders"]:
                    if func.__name__ == "fetch_all_orders":
                        return False, [], {}
                    return False, {"error": "Authentication failed"}
                return False, {"error": "Authentication failed"}

        # Call the function
        result = func(*args, **kwargs)

        # Auto-save session after successful API calls (enhanced persistence)
        if isinstance(result, tuple) and len(result) >= 1:
            success = result[0]
            if success and self.is_authenticated and self.session_email:
                # Auto-save session to keep cookies fresh
                try:
                    self.save_session(self.session_email)
                except Exception as e:
                    app_logger.debug(f"Auto-save skipped: {e}")

        # Check if result indicates session expiration
        if isinstance(result, tuple) and len(result) >= 2:
            success = result[0]
            if not success:
                error_data = result[1]
                if isinstance(error_data, dict) and "error" in error_data:
                    error_msg = error_data["error"].lower()
                    if (
                        "not authenticated" in error_msg
                        or "session" in error_msg
                        or "expired" in error_msg
                    ):
                        # Attempt re-login
                        app_logger.warning(
                            "Session expired during request, attempting relogin..."
                        )
                        if self._relogin_with_saved_credentials():
                            # Retry the function call
                            app_logger.info(
                                "Retrying request after successful relogin..."
                            )
                            return func(*args, **kwargs)

        return result
