"""Logging setup for Tista Assignment Scraper.

Configures file and console logging with rotation.
All modules should import `logger` from this module.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Log directory
_APPDATA = os.environ.get("APPDATA", "")
_LOG_DIR = os.path.join(_APPDATA, "TistaScraper", "logs") if _APPDATA else os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
)

LOG_FILE = os.path.join(_LOG_DIR, "scraper.log")


def setup_logging(level: int = logging.DEBUG) -> logging.Logger:
    """Configure logging with file and console handlers.

    Args:
        level: Minimum log level (default: DEBUG)

    Returns:
        Configured logger instance
    """
    os.makedirs(_LOG_DIR, exist_ok=True)

    logger = logging.getLogger("tista_scraper")
    logger.setLevel(level)

    # Avoid duplicate handlers on re-import
    if logger.handlers:
        return logger

    # Format: 2025-04-13 09:30:00 [INFO] tista_scraper: message
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler — rotated at 5MB, keep 3 backups
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler — INFO and above (less verbose than file)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info("Logging initialized. Log file: %s", LOG_FILE)
    return logger


# Module-level logger instance
logger = setup_logging()
