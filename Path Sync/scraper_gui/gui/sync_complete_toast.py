"""Sync completion toast — centered modal popup shown after Google Sheet sync completes."""

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QApplication,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor

from config import THEME, APP_NAME
from gui.widgets import center_dialog_on_parent


class SyncCompleteToast(QDialog):
    """Centered modal popup notification shown after Google sync completes."""

    def __init__(self, parent, row_count, sheet_tab):
        super().__init__(parent)
        self._row_count = row_count
        self._sheet_tab = sheet_tab
        self._fade_in = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.setFixedSize(320, 130)
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet("")

        content_widget = QWidget(self)
        content_widget.setObjectName("popup_content")
        content_widget.setStyleSheet(f"""
            QWidget#popup_content {{
                background: {THEME["surface"]};
                border: 1px solid {THEME["success"]};
                border-radius: 6px;
            }}
        """)

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(12, 6, 12, 8)
        content_layout.setSpacing(6)

        check_label = QLabel("✔")
        check_label.setAlignment(Qt.AlignCenter)
        check_label.setStyleSheet(f"""
            QLabel {{
                font-size: 24px;
                color: {THEME["success"]};
                background: transparent;
            }}
        """)
        content_layout.addWidget(check_label)

        msg_label = QLabel(
            f"Appended {self._row_count} row(s) to "
            f"Google Sheet tab '{self._sheet_tab}'."
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

        ok_btn = QPushButton("OK")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setMinimumHeight(30)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["primary"]};
                color: {THEME["text"]};
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
        ok_btn.clicked.connect(self.accept)
        content_layout.addWidget(ok_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.addWidget(content_widget)

        center_dialog_on_parent(self, 320, 130)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

    def showEvent(self, event):
        super().showEvent(event)
        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(250)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(THEME["surface"]))
        super().paintEvent(event)
