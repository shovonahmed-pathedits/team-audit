"""
Login dialog for authentication
"""

import os
import json
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QMessageBox,
    QFrame,
    QWidget,
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QFont, QMouseEvent

from gui.theme import get_theme_colors
from utils.credential_manager import CredentialManager

# Unicode bitcode for emojis (prevents font/style changes)
EYE_OPEN = "\U0001f441"  # 👁 (show password)
EYE_CLOSED = "\U0001f648"  # 🙈 (hide password)
CHECK_EMPTY = "\u2610"  # ☐ (unchecked)
CHECK_FILLED = "\u2611"  # ☑ (checked)


class LoginDialog(QDialog):
    """Login dialog for user authentication"""

    login_successful = Signal(str, str)  # Emits email, password on successful login

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)

        # Set Window Icon (Fixes Taskbar Icon)
        try:
            import sys
            import os

            base_path = getattr(
                sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))
            )
            icon_path = os.path.join(
                base_path, "..", "Logo.ico"
            )  # Adjust for widget location
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_path, "Logo.ico")
            if os.path.exists(icon_path):
                from PySide6.QtGui import QIcon

                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        self.setup_ui()
        self.load_saved_credentials()

    def setup_ui(self):
        """Setup the login dialog UI"""
        # Main layout with light background
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.colors = get_theme_colors()

        # Main container frame
        main_container = QFrame(self)
        main_container.setStyleSheet(f"""
            QFrame#MainContainer {{
                background-color: {self.colors["popup_bg"]};
                border-radius: 12px;
                padding: 40px;
                border: 2px solid {self.colors["border"]};
            }}
        """)
        main_container.setObjectName("MainContainer")

        container_layout = QVBoxLayout(main_container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(20)

        # Title
        title_layout = QVBoxLayout()
        title_layout.setSpacing(5)

        self.title_label = QLabel("Order Collector")
        self.title_label.setStyleSheet(f"""
            QLabel {{
                color: {self.colors["text_primary"]};
                font-size: 28px;
                font-weight: bold;
            }}
        """)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitle_label = QLabel("Login to Tista Dashboard")
        self.subtitle_label.setStyleSheet(f"""
            QLabel {{
                color: {self.colors["text_secondary"]};
                font-size: 13px;
            }}
        """)
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.subtitle_label)
        container_layout.addLayout(title_layout)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet(f"background-color: {self.colors['border']};")
        separator.setFixedHeight(2)
        container_layout.addWidget(separator)

        # Form layout
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        # Email field
        email_layout = QVBoxLayout()
        email_layout.setSpacing(5)
        self.email_label = QLabel("Email Address")
        self.email_label.setStyleSheet(
            f"color: {self.colors['text_secondary']}; font-size: 13px;"
        )
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email")
        self.email_input.setMinimumHeight(45)
        self.email_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {self.colors["bg_secondary"]};
                color: {self.colors["text_primary"]};
                border: 2px solid {self.colors["border"]};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {self.colors["primary"]};
                background-color: {self.colors["bg_primary"]};
            }}
        """)
        email_layout.addWidget(self.email_label)
        email_layout.addWidget(self.email_input)
        form_layout.addLayout(email_layout)

        # Password field with toggle button - Unified seamless box
        password_layout = QVBoxLayout()
        password_layout.setSpacing(5)
        self.password_label = QLabel("Password")
        self.password_label.setStyleSheet("color: #495057; font-size: 13px;")

        # Unified password frame (single box with border)
        password_frame = QFrame()
        password_frame.setObjectName("PasswordFrame")
        password_frame.setMinimumHeight(45)
        password_frame.setStyleSheet(f"""
            QFrame#PasswordFrame {{
                background-color: {self.colors["bg_secondary"]};
                border: 2px solid {self.colors["border"]};
                border-radius: 8px;
            }}
            QFrame#PasswordFrame:hover {{
                border-color: {self.colors["primary"]};
            }}
            QFrame#PasswordFrame:focus-within {{
                border-color: {self.colors["primary"]};
                background-color: {self.colors["bg_primary"]};
            }}
        """)

        # Horizontal layout inside the frame
        password_inner = QHBoxLayout(password_frame)
        password_inner.setContentsMargins(0, 0, 0, 0)
        password_inner.setSpacing(0)

        # Password input (no border, blends into frame)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                color: {self.colors["text_primary"]};
                border: none;
                padding: 10px 12px;
                font-size: 13px;
            }}
        """)
        password_inner.addWidget(self.password_input)

        # Toggle button (transparent, seamless inside frame)
        self.toggle_password_btn = QPushButton(EYE_OPEN)
        self.toggle_password_btn.setFixedSize(35, 35)
        self.toggle_password_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_password_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {self.colors["text_primary"]};
                border: none;
                border-radius: 17px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.08);
            }}
            QPushButton:pressed {{
                background-color: rgba(255, 255, 255, 0.12);
            }}
        """)
        self.toggle_password_btn.clicked.connect(self._toggle_password_visibility)
        password_inner.addWidget(self.toggle_password_btn)

        self.password_visible = False  # Track password visibility state

        password_layout.addWidget(self.password_label)
        password_layout.addWidget(password_frame)
        form_layout.addLayout(password_layout)

        # Remember me - custom clickable label with emoji (50% larger)
        self.remember_checked = False
        self.remember_check = QLabel(f"{CHECK_EMPTY} Remember credentials")
        self.remember_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remember_check.setStyleSheet(f"""
            QLabel {{
                color: {self.colors["text_secondary"]};
                font-size: 20px;
                padding: 8px 0px;
            }}
            QLabel:hover {{
                color: {self.colors["text_primary"]};
            }}
        """)
        self.remember_check.mousePressEvent = self._toggle_remember_check

        form_layout.addWidget(self.remember_check)

        container_layout.addLayout(form_layout)

        # Error message
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        self.error_label.setWordWrap(True)
        container_layout.addWidget(self.error_label)

        # Login button - teal color
        self.login_button = QPushButton("Login")
        self.login_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.colors["primary"]};
                color: {self.colors["button_text"]};
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.colors["primary_hover"]};
            }}
            QPushButton:pressed {{
                background-color: {self.colors["primary_pressed"]};
            }}
            QPushButton:disabled {{
                background-color: {self.colors["button_disabled_bg"]};
                color: {self.colors["button_disabled"]};
            }}
        """)
        self.login_button.setMinimumHeight(50)
        self.login_button.clicked.connect(self.on_login_clicked)
        container_layout.addWidget(self.login_button)

        main_layout.addWidget(main_container)

        # Set dialog properties
        self.setWindowTitle("Login - Order Collector")
        self.setMinimumWidth(420)
        self.setFixedWidth(420)

    def _toggle_password_visibility(self):
        """Toggle password visibility between hidden and visible"""
        self.password_visible = not self.password_visible
        if self.password_visible:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_password_btn.setText(EYE_CLOSED)  # 🙈
        else:
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_password_btn.setText(EYE_OPEN)  # 👁

    def _toggle_remember_check(self, event):
        """Toggle remember checkbox emoji"""
        self.remember_checked = not self.remember_checked
        if self.remember_checked:
            self.remember_check.setText(f"{CHECK_FILLED} Remember credentials")
        else:
            self.remember_check.setText(f"{CHECK_EMPTY} Remember credentials")

    def load_saved_credentials(self):
        """Load saved credentials from Windows Credential Manager"""
        try:
            # Get saved email from Windows Registry
            email = CredentialManager.get_saved_email()
            if not email:
                return

            # Get password from Windows Vault
            password = CredentialManager.get_password(email)
            if not password:
                return

            # Auto-fill credentials
            self.email_input.setText(email)
            self.password_input.setText(password)
            self.remember_checked = True
            self.remember_check.setText(f"{CHECK_FILLED} Remember credentials")

        except Exception as e:
            pass  # Silent fail, user types manually

    def save_credentials(self, email: str, password: str):
        """Save credentials to Windows Credential Manager"""
        try:
            CredentialManager.save_credentials(email, password)
            CredentialManager.save_email(email)
        except Exception as e:
            pass  # Silent fail

    def clear_credentials(self):
        """Clear saved credentials from Windows Credential Manager"""
        try:
            email = CredentialManager.get_saved_email()
            if email:
                CredentialManager.delete_credentials(email)
                CredentialManager.clear_email()
        except Exception:
            pass

    def on_login_clicked(self):
        """Handle login button click"""
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()

        # Validate inputs
        if not email or not password:
            self.error_label.setText("Please enter both email and password")
            return

        self.error_label.setText("")

        # Emit signal with credentials
        self.login_successful.emit(email, password)

        # Save credentials if requested
        if self.remember_checked:
            self.save_credentials(email, password)
        else:
            self.clear_credentials()

    def show_error(self, message: str):
        """Show error message"""
        self.error_label.setText(message)

    def set_loading(self, loading: bool):
        """Set loading state"""
        self.login_button.setEnabled(not loading)
        self.login_button.setText("Logging in..." if loading else "Login")
        self.email_input.setEnabled(not loading)
        self.password_input.setEnabled(not loading)
