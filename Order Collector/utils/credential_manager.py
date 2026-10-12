"""
Windows Credential Manager integration for secure password storage
Uses Windows Vault (DPAPI) for OS-level encryption
"""
import keyring
from utils.logger import app_logger

SERVICE_NAME = "OrderCollector"
REGISTRY_PATH = r"Software\OrderCollector"


class CredentialManager:
    """Windows Credential Manager wrapper for password storage"""

    @staticmethod
    def save_credentials(email: str, password: str) -> bool:
        """
        Save password to Windows Credential Manager
        
        Args:
            email: User email (acts as username)
            password: User password to store securely
        
        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.set_password(SERVICE_NAME, email, password)
            app_logger.info(f"Credentials saved to Windows Vault for {email}")
            return True
        except Exception as e:
            app_logger.error(f"Failed to save credentials to Windows Vault: {e}")
            return False

    @staticmethod
    def get_password(email: str) -> str:
        """
        Retrieve password from Windows Credential Manager
        
        Args:
            email: User email to lookup
        
        Returns:
            Password string or None if not found
        """
        try:
            password = keyring.get_password(SERVICE_NAME, email)
            if password:
                app_logger.debug(f"Password retrieved from Windows Vault for {email}")
            return password
        except Exception as e:
            app_logger.error(f"Failed to get password from Windows Vault: {e}")
            return None

    @staticmethod
    def get_saved_email() -> str:
        """
        Get the last saved email from Windows Registry
        
        Returns:
            Email string or empty string if not found
        """
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REGISTRY_PATH,
                0,
                winreg.KEY_READ
            )
            email = winreg.QueryValueEx(key, "LastEmail")[0]
            winreg.CloseKey(key)
            return email
        except Exception:
            return ""

    @staticmethod
    def save_email(email: str) -> bool:
        """
        Save email to Windows Registry for auto-fill
        
        Args:
            email: User email to save
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH)
            winreg.SetValueEx(key, "LastEmail", 0, winreg.REG_SZ, email)
            winreg.CloseKey(key)
            app_logger.debug(f"Email saved to registry: {email}")
            return True
        except Exception as e:
            app_logger.error(f"Failed to save email to registry: {e}")
            return False

    @staticmethod
    def delete_credentials(email: str) -> bool:
        """
        Delete password from Windows Credential Manager
        
        Args:
            email: User email to remove
        
        Returns:
            True if successful, False otherwise
        """
        try:
            keyring.delete_password(SERVICE_NAME, email)
            app_logger.info(f"Credentials deleted from Windows Vault for {email}")
            return True
        except Exception as e:
            app_logger.error(f"Failed to delete credentials from Windows Vault: {e}")
            return False

    @staticmethod
    def clear_email() -> bool:
        """
        Remove email from Windows Registry
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH)
            winreg.DeleteValue(key, "LastEmail")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False
