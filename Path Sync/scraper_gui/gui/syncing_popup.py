"""Animated popup shown while Google Sheet sync is running."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsOpacityEffect,
    QProgressBar,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from config import THEME, APP_NAME


class SyncingPopup(QDialog):
    """Small animated popup that indicates sync is in progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fade_in = None
        self._fade_out = None
        self._move_anim = None
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(340, 140)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QWidget(self)
        panel.setObjectName("sync_panel")
        panel.setStyleSheet(f"""
            QWidget#sync_panel {{
                background: {THEME["surface"]};
                border: 1px solid {THEME["toast_border"]};
                border-radius: 10px;
            }}
        """)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 16)
        panel_layout.setSpacing(10)

        title = QLabel("Syncing to Google Sheet")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text"]};
                font-size: 16px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        panel_layout.addWidget(title)

        self.detail_label = QLabel("Uploading rows and appending them below the sheet.")
        self.detail_label.setAlignment(Qt.AlignCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text_muted"]};
                font-size: 12px;
                background: transparent;
            }}
        """)
        panel_layout.addWidget(self.detail_label)

        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setFixedHeight(10)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: {THEME["progress_track"]};
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                border-radius: 5px;
                background: {THEME["progress_running"]};
            }}
        """)
        panel_layout.addWidget(self.busy_bar)

        footer = QLabel(APP_NAME)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text_muted"]};
                font-size: 11px;
                background: transparent;
            }}
        """)
        panel_layout.addWidget(footer)

        outer.addWidget(panel)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)

    def set_detail(self, text: str):
        self.detail_label.setText(text)

    def show_animated(self):
        self.show()
        self.raise_()
        self.activateWindow()

        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
            start_rect = QRect(x, y + 14, self.width(), self.height())
            end_rect = QRect(x, y, self.width(), self.height())
            self.setGeometry(start_rect)

            self._move_anim = QPropertyAnimation(self, b"geometry", self)
            self._move_anim.setDuration(220)
            self._move_anim.setStartValue(start_rect)
            self._move_anim.setEndValue(end_rect)
            self._move_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._move_anim.start()

        self._fade_in = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_in.setDuration(220)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_in.start()

    def close_animated(self, on_finished=None):
        self._fade_out = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_out.setDuration(180)
        self._fade_out.setStartValue(self._opacity.opacity())
        self._fade_out.setEndValue(0.0)
        self._fade_out.setEasingCurve(QEasingCurve.Type.InCubic)

        def _finish():
            self.close()
            if on_finished:
                on_finished()

        self._fade_out.finished.connect(_finish)
        self._fade_out.start()
