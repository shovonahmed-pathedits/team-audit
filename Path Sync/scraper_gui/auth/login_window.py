"""Login window — authentication dialog for Tista."""

import os
import re
import sys

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QCheckBox,
    QWidget,
    QSizePolicy,
    QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

from config import APP_NAME, THEME

# Import credential and session managers (with fallback)
try:
    from credentials import CredentialManager
except Exception:
    CredentialManager = None

try:
    from session_manager import SessionManager
except Exception:
    SessionManager = None

# Import scraper for login validation
from scraper import AssignmentScraper


class LoginWindow(QDialog):
    """Separate login dialog window."""

    login_successful = Signal(str, str)  # email, password

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        self.setFixedSize(450, 400)
        self.setModal(True)

        # Set window icon - use bundled icon for frozen exe
        if getattr(sys, "frozen", False):
            self.setWindowIcon(QIcon(sys._MEIPASS + os.sep + "sync.ico"))

        self.setup_ui()
        self.load_saved_credentials()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 25, 30, 25)
        layout.setSpacing(12)

        title = QLabel("Tista Login")
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 28px;
                font-weight: bold;
                color: {THEME["text"]};
                padding-bottom: 8px;
            }}
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Enter your credentials to continue")
        subtitle.setStyleSheet(f"font-size: 13px; color: {THEME['text_muted']};")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(15)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Email")
        self.email_input.setMinimumHeight(42)
        self.email_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.email_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                font-size: 14px;
                background: {THEME["input_bg"]};
            }}
            QLineEdit:focus {{
                border-color: {THEME["input_focus"]};
                border-width: 2px;
            }}
        """)
        self.email_input.setFocus()
        layout.addWidget(self.email_input)

        pwd_container = QWidget()
        pwd_layout = QHBoxLayout(pwd_container)
        pwd_layout.setContentsMargins(0, 0, 0, 0)
        pwd_layout.setSpacing(8)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(42)
        self.password_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                font-size: 14px;
                background: {THEME["input_bg"]};
            }}
            QLineEdit:focus {{
                border-color: {THEME["input_focus"]};
                border-width: 2px;
            }}
        """)
        pwd_layout.addWidget(self.password_input)

        self.toggle_pwd_btn = QPushButton()
        self.toggle_pwd_btn.setFixedSize(42, 42)
        self.toggle_pwd_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_pwd_btn.setCheckable(True)
        self.toggle_pwd_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                border-color: {THEME["input_focus"]};
                background: {THEME["alt_row"]};
            }}
        """)
        self.toggle_pwd_btn.setText("\U0001f441")
        self.toggle_pwd_btn.setToolTip("Show password")
        self.toggle_pwd_btn.toggled.connect(self.toggle_password_visibility)
        pwd_layout.addWidget(self.toggle_pwd_btn)

        layout.addWidget(pwd_container)

        self.remember_me_checkbox = QCheckBox("Remember me")
        self.remember_me_checkbox.setChecked(True)
        self.remember_me_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {THEME["text_muted"]};
            }}
        """)
        layout.addWidget(self.remember_me_checkbox)

        layout.addSpacing(10)

        self.login_btn = QPushButton("Login")
        self.login_btn.setCursor(Qt.PointingHandCursor)
        self.login_btn.setMinimumHeight(46)
        self.login_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["primary"]};
                color: {THEME["text"]};
                border: none;
                border-radius: 10px;
                padding: 12px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {THEME["primary_hover"]};
            }}
            QPushButton:pressed {{
                background: {THEME["primary_pressed"]};
            }}
            QPushButton:disabled {{
                background: #b8b8b8;
                color: #888888;
            }}
        """)
        self.login_btn.clicked.connect(self.do_login)
        layout.addWidget(self.login_btn)

        self.email_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.do_login)

    def toggle_password_visibility(self, checked):
        if checked:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_pwd_btn.setText("\U0001f648")
            self.toggle_pwd_btn.setToolTip("Hide password")
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_pwd_btn.setText("\U0001f441")
            self.toggle_pwd_btn.setToolTip("Show password")

    def validate_email(self, email: str) -> bool:
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None

    def load_saved_credentials(self):
        if CredentialManager and CredentialManager.has_credentials():
            email = CredentialManager.get_email()
            password = CredentialManager.get_password()
            if email and password:
                self.email_input.setText(email)
                self.password_input.setText(password)
                self.remember_me_checkbox.setChecked(True)

    def do_login(self):
        email = self.email_input.text().strip()
        password = self.password_input.text()

        if not email:
            self.email_input.setFocus()
            QMessageBox.warning(self, APP_NAME, "Please enter your email")
            return

        if not self.validate_email(email):
            self.email_input.setFocus()
            QMessageBox.warning(self, APP_NAME, "Please enter a valid email address")
            return

        if not password:
            self.password_input.setFocus()
            QMessageBox.warning(self, APP_NAME, "Please enter your password")
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("Logging in...")
        QApplication.processEvents()

        try:
            test_scraper = AssignmentScraper()
            success, message = test_scraper.login(email, password)

            if not success:
                self.login_btn.setEnabled(True)
                self.login_btn.setText("Login")
                QMessageBox.warning(
                    self, APP_NAME, f"Could not login to Tista:\n{message}"
                )
                return
        except Exception as e:
            self.login_btn.setEnabled(True)
            self.login_btn.setText("Login")
            QMessageBox.warning(
                self, APP_NAME, f"Could not connect to Tista:\n{str(e)}"
            )
            return

        if self.remember_me_checkbox.isChecked():
            if CredentialManager:
                try:
                    CredentialManager.save(email, password)
                except Exception as e:
                    pass

        self.login_btn.setText("Success!")
        self.login_successful.emit(email, password)
        self.accept()
