"""Service category mappings and SM display name resolution.

Mappings are loaded from mappings.json if available, otherwise use
hardcoded defaults. This allows updating mappings without recompiling.
"""

import json
import os

# Fallback hardcoded defaults (in case JSON file is missing)
_SERVICE_CATEGORY_MAPPING_FALLBACK = {
    1: ("Clipping Path", "1", 1),
    2: ("Clipping Path", "1.5", 1),
    3: ("Clipping Path", "2", 1),
    4: ("Clipping Path", "2.25", 1),
    5: ("Clipping Path", "2.5", 1),
    6: ("Clipping Path", "2.75", 1),
    7: ("Clipping Path", "3", 1),
    8: ("Clipping Path", "3.25", 1),
    9: ("Clipping Path", "3.5", 1),
    10: ("Clipping Path", "3.75", 1),
    11: ("Clipping Path", "4", 1),
    12: ("Clipping Path", "4.25", 1),
    13: ("Clipping Path", "4.5", 1),
    14: ("Clipping Path", "4.75", 1),
    15: ("Clipping Path", "5", 1),
    16: ("Clipping Path", "5.5", 1),
    17: ("Clipping Path", "6", 1),
    21: ("Clipping Path", "10", 1),
    22: ("Multi-clipping Path", "1", 2),
    23: ("Multi-clipping Path", "2", 2),
    24: ("Multi-clipping Path", "2.5", 2),
    25: ("Multi-clipping Path", "3", 2),
    26: ("Multi-clipping Path", "3.5", 2),
    27: ("Multi-clipping Path", "4", 2),
    28: ("Image Masking", "1", 3),
    29: ("Image Masking", "2", 3),
    30: ("Image Masking", "2.5", 3),
    31: ("Image Masking", "3", 3),
    32: ("Image Masking", "3.25", 3),
    33: ("Image Masking", "3.5", 3),
    34: ("Image Masking", "3.75", 3),
    35: ("Image Masking", "4", 3),
    36: ("Image Masking", "4.5", 3),
    37: ("Image Masking", "5", 3),
    38: ("Drop Shadow", "1", 4),
    39: ("Existing Shadow", "1", 4),
    40: ("Natural Shadow", "1", 4),
    41: ("Natural Shadow", "2", 4),
    42: ("Natural Shadow", "3", 4),
    43: ("Floating Shadow", "1", 4),
    44: ("Reflection Shadow", "1", 4),
    45: ("Reflection Shadow", "2", 4),
    46: ("Reflection Shadow", "3", 4),
    47: ("Ghost Mannequin", "1", 5),
    48: ("Ghost Mannequin", "2", 5),
    49: ("Dust, Spot and Scratch Removal", "1", 6),
    50: ("Dust, Spot and Scratch Removal", "2", 6),
    51: ("Wrinkle on Clothing", "1", 6),
    52: ("Wrinkle on Clothing", "2", 6),
    53: ("Beauty Airbrushing", "1", 6),
    54: ("Beauty Airbrushing", "2", 6),
    55: ("Camera Reflection Removal", "1", 6),
    56: ("Camera Reflection Removal", "2", 6),
    77: ("Dust, Spot and Scratch Removal", "1.5", 6),
    78: ("Camera Reflection Removal", "1.5", 6),
    57: ("Color Variants", "1", 7),
    58: ("Logo", "1", 8),
    59: ("Logo", "1.5", 8),
    60: ("Logo", "2", 8),
    61: ("Logo", "2.5", 8),
    62: ("Logo", "3", 8),
    63: ("Artwork", "1", 8),
    64: ("Artwork", "2", 8),
    65: ("Artwork", "3", 8),
    66: ("Line Drawing", "1", 8),
    67: ("Line Drawing", "2", 8),
    68: ("Illustration", "1", 8),
    69: ("Illustration", "2", 8),
    70: ("Illustration", "3", 8),
    71: ("Additional Copy", "1", 9),
    79: ("Mirror Effect", "1", 15),
}

_SM_DISPLAY_NAMES_FALLBACK = {
    "rasel_sm": "Rasel668",
    "uzzal_prodhan": "uzzalprodhan663",
    "mehadi.hasan": "Mehadi672",
    "evan.sm": "Evan674",
    "riponkumar525": "Riponkumar525",
    "motiur567": "Motiur567",
    "sanjit203": "Sanjit203",
    "dipankar - asm": "Dipankar680",
}

_SM_PRIORITY_FALLBACK = {
    "evan.sm": 1,
    "mehadi.hasan": 1,
    "uzzal_prodhan": 1,
    "rasel_sm": 2,
    "motiur567": 3,
    "sanjit203": 3,
    "riponkumar525": 4,
    "dipankar - asm": 1,
}

VENDOR_3KEY_MAPPING = {
    "Creative Path (P1)": "P1",
    "Pixel Path (P2)": "P2",
    "Perfect Pixel (GB2)": "GB2",
    "Grasigner Kitchen": "GK",
    "Khandoker Graphics": "KG",
    "Graphics Picture": "GP",
    "Vectorio": "V",
    "Cutout Edge": "CE",
    "Edgebo": "E",
    "Healing Image": "HI",
    "Photo Fix Zone": "PFZ",
    "Clipping Pix": "CP",
}


def _load_mappings_json():
    """Load mappings from JSON config file. Returns (categories, sm_names, sm_priority) or None."""
    json_path = os.path.join(os.path.dirname(__file__), "mappings.json")
    if not os.path.exists(json_path):
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        categories = {}
        for key, val in data.get("service_categories", {}).items():
            categories[int(key)] = tuple(val)

        sm_names = data.get("sm_display_names", {})
        sm_priority = data.get("sm_priority", {})
        return categories, sm_names, sm_priority
    except Exception:
        return None


# Try loading from JSON, fall back to hardcoded defaults
_loaded = _load_mappings_json()
if _loaded:
    SERVICE_CATEGORY_MAPPING, SM_DISPLAY_NAMES, SM_PRIORITY = _loaded
else:
    SERVICE_CATEGORY_MAPPING = _SERVICE_CATEGORY_MAPPING_FALLBACK
    SM_DISPLAY_NAMES = _SM_DISPLAY_NAMES_FALLBACK
    SM_PRIORITY = _SM_PRIORITY_FALLBACK


def resolve_sm_display_name(raw_name: str) -> str:
    """Convert raw SM username to display-friendly name."""
    if not raw_name:
        return ""
    key = raw_name.strip().lower()
    return SM_DISPLAY_NAMES.get(key, raw_name.strip())


def sm_priority(raw_name: str) -> int:
    """Return the priority tier for an SM username.

    Lower number = higher priority. Unknown names return 99 (lowest).
    """
    if not raw_name:
        return 99
    key = raw_name.strip().lower()
    return SM_PRIORITY.get(key, 99)


def is_known_sm(raw_name: str) -> bool:
    """Check if a raw username is in the known SM list."""
    if not raw_name:
        return False
    key = raw_name.strip().lower()
    return key in SM_DISPLAY_NAMES


SYSTEM_USERS = {"tista", "tista_bot", "my account"}
SYSTEM_USER_LABELS = {"my account", "profile", "password", "logout", "login"}
