"""
Order Collector - Main Application Entry Point

A PySide6-based desktop application for fetching and analyzing
order data from Tista dashboard.

Usage:
    python main.py                  # Normal GUI mode
    python main.py --debug          # Debug mode with verbose logging
    python main.py --headless       # Headless mode (no GUI, for testing)
    python main.py --test-login     # Test login and exit
"""
import sys
import os
import ctypes
import argparse
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from api.client import TistaAPI
from gui.login_window import LoginDialog
from gui.main_window import MainWindow
from gui.theme import apply_theme
from utils.logger import app_logger, setup_logger
from config import DEBUG_MODE, HEADLESS_MODE, DEBUG_LOG_FILE

# Fix Windows Taskbar Icon (Must run before QApplication)
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OrderCollector.OrderCollector.1")
except Exception:
    pass


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Order Collector - Tista Dashboard Data Fetcher')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode with verbose logging')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode (no GUI)')
    parser.add_argument('--test-login', action='store_true', help='Test login credentials and exit')
    parser.add_argument('--email', type=str, help='Email for login (used with --test-login)')
    parser.add_argument('--password', type=str, help='Password for login (used with --test-login)')
    parser.add_argument('--start-date', type=str, help='Start date (DD/MM/YY format)')
    parser.add_argument('--end-date', type=str, help='End date (DD/MM/YY format)')
    parser.add_argument('--location-id', type=int, help='Location ID filter')
    parser.add_argument('--theme', choices=['light', 'dark'], help='Force light or dark UI theme')
    return parser.parse_args()


def run_headless_test(api, args):
    """Run headless data fetch test"""
    app_logger.info("=" * 60)
    app_logger.info("HEADLESS MODE - Testing data extraction")
    app_logger.info("=" * 60)
    
    # Use provided credentials or prompt
    email = args.email or input("Enter email: ")
    password = args.password or input("Enter password: ")
    
    # Login
    app_logger.info(f"Logging in as {email}...")
    success, message = api.login(email, password)
    
    if not success:
        app_logger.error(f"Login failed: {message}")
        return False
    
    app_logger.info("Login successful!")
    
    # Fetch locations
    app_logger.info("Fetching locations...")
    success, locations = api.fetch_locations()
    
    if success:
        app_logger.info(f"Found {len(locations)} locations:")
        for loc in locations[:10]:  # Show first 10
            if isinstance(loc, dict):
                app_logger.info(f"  - {loc.get('name', loc.get('title', 'Unknown'))} (ID: {loc.get('id')})")
            else:
                app_logger.info(f"  - {loc}")
    else:
        app_logger.warning("Failed to fetch locations")
    
    # Fetch orders
    start_date = args.start_date or input("Enter start date (DD/MM/YY) or press Enter for last 7 days: ")
    end_date = args.end_date or input("Enter end date (DD/MM/YY) or press Enter for today: ")
    
    if not start_date:
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=7)).strftime("%d/%m/%y")
    if not end_date:
        from datetime import datetime
        end_date = datetime.now().strftime("%d/%m/%y")
    
    app_logger.info(f"Fetching orders from {start_date} to {end_date}...")
    
    location_id = args.location_id
    if not location_id and locations:
        app_logger.info("Using all locations (no filter)")
    
    success, orders, meta = api.fetch_all_orders(
        location_id=location_id,
        start_date=start_date,
        end_date=end_date
    )
    
    if success:
        app_logger.info(f"Successfully fetched {len(orders)} orders!")
        
        # Show sample order structure
        if orders and DEBUG_MODE:
            app_logger.debug("Sample order structure:")
            sample = orders[0]
            for key, value in sample.items():
                if key != 'lineItems':  # Skip large arrays
                    app_logger.debug(f"  {key}: {type(value).__name__} = {str(value)[:100]}")

        return True
    else:
        app_logger.error(f"Failed to fetch orders: {meta.get('error', 'Unknown error')}")
        return False


class Application:
    """Main application controller"""

    def __init__(self):
        # Fix Windows taskbar icon for PyInstaller --onefile builds
        try:
            myappid = "OrderCollector.OrderCollector.1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Order Collector")
        self.app.setOrganizationName("OrderCollector")
        self.app.setOrganizationDomain("ordercollector.app")

        # Set taskbar and window icon from bundled resource
        try:
            base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base_path, "Logo.ico")
            if os.path.exists(icon_path):
                self.app.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        # Set application-wide dark theme
        self.app.setStyle("Fusion")

        # API client
        self.api = TistaAPI()

        # Windows
        self.login_dialog = None
        self.main_window = None
    
    def run(self):
        """Start the application with smart session validation"""
        app_logger.info("Application starting...")

        if DEBUG_MODE:
            app_logger.info(f"Debug log file: logs/{DEBUG_LOG_FILE}")

        if HEADLESS_MODE:
            app_logger.info("Running in headless mode")
            return

        # Smart startup: Try to skip login with valid session
        if self._try_auto_login():
            # Session valid, show dashboard directly
            self.show_dashboard()
        else:
            # No valid session, show login dialog
            self.show_login()

        # Run application
        sys.exit(self.app.exec())

    def _try_auto_login(self) -> bool:
        """
        Try to auto-login with saved session/credentials (no user interaction)

        Returns:
            True if login successful and ready to show dashboard, False otherwise
        """
        try:
            from utils.credential_manager import CredentialManager

            # Step 1: Get saved email from Windows Registry
            saved_email = CredentialManager.get_saved_email()
            if not saved_email:
                app_logger.debug("No saved email found in registry")
                return False

            app_logger.info(f"Found saved email: {saved_email}")

            # Step 2: Try loading session
            if self.api.load_session(saved_email):
                app_logger.info("Session loaded, validating...")

                # Step 3: Validate session (5-second ping test)
                if self.api.validate_session():
                    app_logger.info("Session is valid, skipping login")
                    return True
                else:
                    app_logger.warning("Session expired, clearing...")
                    self.api.clear_session(saved_email)

            # Step 4: Session expired/missing, try login with saved credentials
            app_logger.info("Attempting auto-login with saved credentials...")
            saved_password = CredentialManager.get_password(saved_email)

            if saved_password:
                app_logger.info(f"Found saved password for {saved_email}, attempting login...")
                success, message = self.api.login(saved_email, saved_password)

                if success:
                    app_logger.info("Auto-login successful!")
                    # Save new session
                    self.api.save_session(saved_email)
                    return True
                else:
                    app_logger.warning(f"Auto-login failed: {message}")
                    return False
            else:
                app_logger.debug("No saved password found")
                return False

        except Exception as e:
            app_logger.error(f"Auto-login failed: {e}")
            return False
    
    def show_login(self):
        """Show login dialog"""
        self.login_dialog = LoginDialog()
        self.login_dialog.login_successful.connect(self.on_login_success)
        self.login_dialog.show()
    
    def on_login_success(self, email: str, password: str):
        """Handle successful login credentials"""
        app_logger.info(f"Attempting login for {email}")

        # Disable login UI
        self.login_dialog.set_loading(True)

        # Perform login
        success, message = self.api.login(email, password)

        if success:
            app_logger.info("Login successful, saving session...")

            # Save session cookies for future auto-login
            self.api.save_session(email)

            # Save credentials to Windows Credential Manager if requested
            if self.login_dialog.remember_checked:
                from utils.credential_manager import CredentialManager
                CredentialManager.save_credentials(email, password)
                CredentialManager.save_email(email)
                app_logger.info("Credentials saved to Windows Vault")

            app_logger.info("Showing dashboard")
            self.login_dialog.accept()
            self.show_dashboard()
        else:
            app_logger.warning(f"Login failed: {message}")
            self.login_dialog.set_loading(False)
            self.login_dialog.show_error(message)
    
    def show_dashboard(self):
        """Show main dashboard window"""
        self.main_window = MainWindow(self.api, on_logout_callback=self.show_login)
        self.main_window.show()


def main():
    """Application entry point"""
    args = parse_arguments()
    
    # Set debug mode from command line
    if args.debug:
        os.environ["ORDER_COLLECTOR_DEBUG"] = "true"
    
    if args.headless or args.test_login:
        os.environ["ORDER_COLLECTOR_HEADLESS"] = "true"
    
    # Reinitialize logger with correct settings
    global app_logger
    app_logger = setup_logger('OrderCollector')
    
    if args.test_login:
        # Quick login test
        api = TistaAPI()
        if args.email and args.password:
            success, message = api.login(args.email, args.password)
            app_logger.info(f"Login test: {'SUCCESS' if success else 'FAILED'} - {message}")
        else:
            app_logger.error("Provide --email and --password for login test")
        return
    
    if args.headless:
        # Run headless test
        api = TistaAPI()
        success = run_headless_test(api, args)
        sys.exit(0 if success else 1)
    
    # Normal GUI mode
    app = Application()
    apply_theme(app.app, args.theme)
    app.run()


if __name__ == "__main__":
    main()
