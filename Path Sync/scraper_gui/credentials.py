"""
Credential Manager using Windows Credential Manager (via keyring library).
Securely stores Tista Scraper login credentials.
"""

import logging
import keyring
import keyring.errors

logger = logging.getLogger("tista_scraper")
SERVICE_NAME = "TistaScraper"
USERNAME_KEY = "tista_user"


class CredentialManager:
    """Secure credential storage using Windows Credential Manager."""

    @staticmethod
    def save(email: str, password: str) -> bool:
        """Save email and password to Windows Credential Manager."""
        try:
            keyring.set_password(SERVICE_NAME, USERNAME_KEY, email)
            keyring.set_password(SERVICE_NAME, f"{USERNAME_KEY}_password", password)
            return True
        except (keyring.errors.KeyringError, Exception) as e:
            logger.error("Failed to save credentials: %s", e)
            raise

    @staticmethod
    def get_email() -> str:
        """Retrieve stored email."""
        try:
            email = keyring.get_password(SERVICE_NAME, USERNAME_KEY)
            return email if email else ""
        except (keyring.errors.KeyringError, Exception) as e:
            logger.error("Failed to get email: %s", e)
            return ""

    @staticmethod
    def get_password() -> str:
        """Retrieve stored password."""
        try:
            password = keyring.get_password(SERVICE_NAME, f"{USERNAME_KEY}_password")
            return password if password else ""
        except (keyring.errors.KeyringError, Exception) as e:
            logger.error("Failed to get password: %s", e)
            return ""

    @staticmethod
    def has_credentials() -> bool:
        """Check if credentials are stored."""
        try:
            email = CredentialManager.get_email()
            password = CredentialManager.get_password()
            return bool(email and password)
        except Exception:
            return False

    @staticmethod
    def delete() -> bool:
        """Delete stored credentials."""
        try:
            email = CredentialManager.get_email()
            password = CredentialManager.get_password()
            if email:
                keyring.delete_password(SERVICE_NAME, USERNAME_KEY)
            if password:
                keyring.delete_password(SERVICE_NAME, f"{USERNAME_KEY}_password")
            return True
        except (keyring.errors.KeyringError, Exception) as e:
            logger.error("Failed to delete credentials: %s", e)
            return False
