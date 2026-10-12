"""
Tista Bulk Assignment Scraper - GUI Application
Entry point — bootstrates the application.
"""

import sys
import os

# Ensure the scraper_gui directory is in the path (important for PyInstaller)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtGui import QPalette, QColor, QFontDatabase, QFont
from PySide6.QtWidgets import QApplication, QDialog

from config import APP_NAME, THEME
from logger import logger

# Import credential and session managers (with fallback)
try:
    from credentials import CredentialManager
except Exception:
    CredentialManager = None

try:
    from session_manager import SessionManager
except Exception:
    SessionManager = None

from scraper import AssignmentScraper
from auth.login_window import LoginWindow
from gui.main_window import MainWindow
from config.theme import SYSTEM_THEME


def _load_livvic_font() -> None:
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    variants = [
        "Livvic-Regular.ttf",
        "Livvic-Medium.ttf",
        "Livvic-SemiBold.ttf",
        "Livvic-Bold.ttf",
    ]
    for fname in variants:
        path = os.path.join(fonts_dir, fname)
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)


def _apply_qt_palette(app: QApplication) -> None:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(THEME["bg"]))
    palette.setColor(QPalette.WindowText, QColor(THEME["text"]))
    palette.setColor(QPalette.Base, QColor(THEME["surface"]))
    palette.setColor(QPalette.AlternateBase, QColor(THEME["alt_row"]))
    palette.setColor(QPalette.ToolTipBase, QColor(THEME["surface"]))
    palette.setColor(QPalette.ToolTipText, QColor(THEME["text"]))
    palette.setColor(QPalette.Text, QColor(THEME["text"]))
    palette.setColor(QPalette.Button, QColor(THEME["surface"]))
    palette.setColor(QPalette.ButtonText, QColor(THEME["text"]))
    palette.setColor(QPalette.Highlight, QColor(THEME["selection"]))
    palette.setColor(QPalette.HighlightedText, QColor(THEME["selection_fg"]))
    palette.setColor(QPalette.PlaceholderText, QColor(THEME["text_muted"]))

    if SYSTEM_THEME == "dark":
        palette.setColor(QPalette.BrightText, QColor("#ffffff"))
    app.setPalette(palette)


def main():
    """Application entry point with session restore and auto-login."""
    logger.info("Application starting...")
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        _load_livvic_font()
        app.setFont(QFont("Livvic", 13))
        _apply_qt_palette(app)

        # STEP 1: Try to restore saved session cookies
        scraper = AssignmentScraper()  # Create scraper instance first
        if SessionManager and SessionManager.has_session():
            logger.info("Found saved session, attempting to restore...")
            cookies_list = SessionManager.load_session()
            if cookies_list:
                logger.info(f"Loaded {len(cookies_list)} cookies from cache")
                # Restore cookies to scraper session
                SessionManager.restore_cookies_to_session(scraper.session, cookies_list)
                # FIX M8: Use public validate_session() instead of private _is_session_valid()
                is_valid, msg = scraper.validate_session()
                if is_valid:
                    logger.info(f"Session valid ({msg}), showing MainWindow directly")
                    SessionManager.save_session(scraper.session)  # Refresh cache
                    scraper.is_authenticated = True
                    # CRITICAL FIX: Always pass actual credentials to MainWindow
                    # so ScraperThread can re-login if session expires mid-scrape
                    email = ""
                    password = ""
                    if CredentialManager and CredentialManager.has_credentials():
                        email = CredentialManager.get_email()
                        password = CredentialManager.get_password()
                        logger.info(
                            f"Loaded stored credentials for session restore: {email}"
                        )
                    window = MainWindow(email, password, scraper)
                    window.show()
                    sys.exit(app.exec())
                else:
                    logger.info(f"Saved session invalid ({msg}), clearing cache")
                    SessionManager.clear_all()  # Clear invalid session
            else:
                logger.info("Failed to load session cookies from cache")

        # STEP 2: Session expired/missing — try auto-relogin
        if CredentialManager and CredentialManager.has_credentials():
            email = CredentialManager.get_email()
            password = CredentialManager.get_password()
            logger.info(f"Auto-relogin with stored credentials: {email}")
            scraper = AssignmentScraper()
            ok, msg = scraper.login(email, password)
            if ok:
                logger.info("Auto-relogin successful, showing MainWindow")
                SessionManager.save_session(scraper.session)
                window = MainWindow(email, password, scraper)
                window.show()
                sys.exit(app.exec())
            else:
                logger.info(f"Auto-relogin failed: {msg}")

        # STEP 3: No session and no credentials — show login dialog
        logger.info("No valid session or credentials, showing LoginWindow")
        login_dlg = LoginWindow()
        if login_dlg.exec() != QDialog.DialogCode.Accepted:
            logger.info("Login cancelled, exiting")
            sys.exit(0)

        email = login_dlg.email_input.text().strip()
        password = login_dlg.password_input.text()
        scraper = AssignmentScraper()  # Create new scraper for logged in user
        window = MainWindow(email, password, scraper)
        window.show()

        sys.exit(app.exec())

    except Exception as e:
        logger.critical(f"Application crash: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
