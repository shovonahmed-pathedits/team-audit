"""Application constants and configuration."""

import os
import re

# Application name
APP_NAME = "Path Sync"

# Tista 2 base URL
BASE_URL = "https://tista.app"

# Output directory for exported files
OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"
)

# Default location ID fallback (used when URL doesn't contain loc_id)
# TODO: Replace with dynamic discovery from assignment detail page or user profile
DEFAULT_LOCATION_ID = "1492"

# Regex pattern to match assignment detail URLs
ASSIGNMENT_URL_PATTERN = re.compile(
    r"^https://tista\.app/team_coordinator/assignment_details/(?P<assignment_id>\d+)/?(?:[?#].*)?$"
)


def safe_str(s):
    """Convert string to safe ASCII for console output."""
    if isinstance(s, str):
        return s.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    return str(s)


REQUEST_TIMEOUTS = {
    "session_validate": 10,
    "login_page": 30,
    "login_post": 30,
    "data_fetch": 15,
    "profile": 30,
    "discover_loc": 15,
}

# Parallel scraping configuration
PARALLEL_CONFIG = {
    "default_workers": 5,
    "max_workers": 10,
    "sequential_delay": 2,
    "parallel_delay": 0,
    "session_check_interval": 25,
}
