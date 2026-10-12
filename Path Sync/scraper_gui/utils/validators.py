"""Input validation utilities."""

import re
from typing import Tuple
from config import ASSIGNMENT_URL_PATTERN


def validate_assignment_url(url: str) -> Tuple[bool, str]:
    """Validate assignment URL format.

    Args:
        url: The URL to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid type"

    url = url.strip()

    if not url.startswith("https://tista.app"):
        return False, "URL must start with https://tista.app"

    if not ASSIGNMENT_URL_PATTERN.match(url):
        return (
            False,
            "Invalid URL format. Expected: https://tista.app/team_coordinator/assignment_details/{id}",
        )

    return True, "Valid"


def validate_email(email: str) -> Tuple[bool, str]:
    """Validate email format.

    Args:
        email: The email to validate

    Returns:
        Tuple of (is_valid, message)
    """
    if not email or not isinstance(email, str):
        return False, "Email is empty"

    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(email_pattern, email.strip()):
        return False, "Invalid email format"

    return True, "Valid"


def validate_url_list(urls: list) -> Tuple[list, list]:
    """Validate a list of URLs and separate valid from invalid.

    Args:
        urls: List of URLs to validate

    Returns:
        Tuple of (valid_urls, invalid_urls_with_errors)
    """
    valid_urls = []
    invalid_urls = []

    for url in urls:
        is_valid, msg = validate_assignment_url(url)
        if is_valid:
            valid_urls.append(url)
        else:
            invalid_urls.append({"url": url, "error": msg})

    return valid_urls, invalid_urls
