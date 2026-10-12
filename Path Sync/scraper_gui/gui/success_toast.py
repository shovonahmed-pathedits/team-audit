"""Small auto-closing popup notification for quick app feedback."""

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor

from config import APP_NAME, THEME
from gui.widgets import center_dialog_on_parent


class SuccessToast(QDialog):
    """Small centered popup notification for copy and cancellation feedback."""

    def __init__(self, parent, message):
        super().__init__(parent)
        self._message = message
        self._auto_close_timer = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setModal(False)
        self.setFixedSize(320, 70)
        self.setWindowTitle(APP_NAME)
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

        msg_label = QLabel(self._message)
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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.addWidget(content_widget)

        center_dialog_on_parent(self, 320, 70)

    def paintEvent(self, event):
        """Fill the dialog background to match the completion popup shell."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(THEME["surface"]))
        super().paintEvent(event)

    def show_and_auto_close(self, duration_ms=2000):
        """Show the toast and auto-close after specified duration."""
        self.show()

        self._auto_close_timer = QTimer()
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.timeout.connect(self.close)
        self._auto_close_timer.start(duration_ms)

    def closeEvent(self, event):
        """Cancel the auto-close timer if manually closed."""
        if self._auto_close_timer and self._auto_close_timer.isActive():
            self._auto_close_timer.stop()
        super().closeEvent(event)
