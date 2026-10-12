"""Completion toast — centered modal popup notification shown after scraping completes."""

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QColor

from config import THEME, APP_NAME
from config.google_sync import is_google_sync_configured
from gui.widgets import center_dialog_on_parent


class CompletionToast(QDialog):
    """Centered modal popup notification shown after scraping completes."""

    def __init__(self, parent, assignment_count, row_count):
        super().__init__(parent)
        self._parent_window = parent
        self._assignment_count = assignment_count
        self._row_count = row_count
        self._copy_timer = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(360, 130)
        self.setWindowTitle(APP_NAME)

        # No stylesheet needed - paintEvent handles the background
        self.setStyleSheet("")

        content_widget = QWidget(self)
        content_widget.setObjectName("popup_content")
        content_widget.setStyleSheet(f"""
            QWidget#popup_content {{
                background: {THEME["surface"]};
                border: 1px solid {THEME["toast_border"]};
                border-radius: 6px;
            }}
        """)

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 6, 12, 8)
        content_layout.setSpacing(6)

        msg_label = QLabel(
            f"Successfully fetched {self._assignment_count} assignment(s) "
            f"from {self._row_count} row(s)!"
        )
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignCenter)
        msg_label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                font-weight: bold;
                color: {THEME["text"]};
                background: transparent;
            }}
        """)
        content_layout.addWidget(msg_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        copy_btn = QPushButton("Copy Summary")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setMinimumHeight(30)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["secondary"]};
                color: {THEME["text"]};
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {THEME["secondary_hover"]};
            }}
            QPushButton:pressed {{
                background: {THEME["secondary_pressed"]};
            }}
        """)
        copy_btn.clicked.connect(self._on_copy_clicked)
        btn_row.addWidget(copy_btn)

        self._push_btn = QPushButton("Push to Sheet")
        self._push_btn.setCursor(Qt.PointingHandCursor)
        self._push_btn.setMinimumHeight(30)
        self._push_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["primary"]};
                color: {THEME["button_text"]};
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {THEME["primary_hover"]};
            }}
            QPushButton:pressed {{
                background: {THEME["primary_pressed"]};
            }}
        """)
        self._push_btn.clicked.connect(self._on_push_clicked)
        btn_row.addWidget(self._push_btn)

        sync_configured = is_google_sync_configured(
            getattr(self._parent_window, "google_sync_settings", None)
        )
        self._push_btn.setVisible(sync_configured)

        content_layout.addLayout(btn_row)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.addWidget(content_widget)

        center_dialog_on_parent(self, 360, 130)

    def paintEvent(self, event):
        """Override paint to fill the dialog background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(THEME["surface"]))
        super().paintEvent(event)

    def _on_copy_clicked(self):
        """Copy data without headers, hide toast, then close."""
        if self._parent_window and hasattr(self._parent_window, "copy_to_clipboard"):
            self._parent_window.copy_to_clipboard(
                include_headers=False, show_toast=False
            )

        copy_btn = self.sender()
        if not copy_btn:
            self.accept()
            return
        copy_btn.setText("Copied!")
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["copied_bg"]};
                color: {THEME["button_text"]};
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
        """)

        self._copy_timer = QTimer()
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(self.accept)
        self._copy_timer.start(800)

    def _on_push_clicked(self):
        if self._parent_window and hasattr(self._parent_window, "sync_to_google_sheet"):
            QTimer.singleShot(0, self._parent_window.sync_to_google_sheet)
        self.accept()

    def closeEvent(self, event):
        """Cancel the close timer if the dialog is closed."""
        if self._copy_timer and self._copy_timer.isActive():
            self._copy_timer.stop()
        super().closeEvent(event)


# Need QApplication for screen geometry
from PySide6.QtWidgets import QApplication
