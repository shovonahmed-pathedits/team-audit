"""Configuration module — theme, constants, and data mappings."""

from config.theme import THEME
from config.constants import (
    APP_NAME,
    BASE_URL,
    OUTPUT_DIR,
    DEFAULT_LOCATION_ID,
    ASSIGNMENT_URL_PATTERN,
    safe_str,
    REQUEST_TIMEOUTS,
    PARALLEL_CONFIG,
)
from config.mappings import (
    SERVICE_CATEGORY_MAPPING,
    SM_DISPLAY_NAMES,
    SM_PRIORITY,
    resolve_sm_display_name,
    sm_priority,
    is_known_sm,
    SYSTEM_USERS,
    SYSTEM_USER_LABELS,
    VENDOR_3KEY_MAPPING,
)

__all__ = [
    "THEME",
    "APP_NAME",
    "BASE_URL",
    "OUTPUT_DIR",
    "DEFAULT_LOCATION_ID",
    "ASSIGNMENT_URL_PATTERN",
    "safe_str",
    "REQUEST_TIMEOUTS",
    "PARALLEL_CONFIG",
    "SERVICE_CATEGORY_MAPPING",
    "SM_DISPLAY_NAMES",
    "SM_PRIORITY",
    "resolve_sm_display_name",
    "sm_priority",
    "is_known_sm",
    "SYSTEM_USERS",
    "SYSTEM_USER_LABELS",
    "VENDOR_3KEY_MAPPING",
]
