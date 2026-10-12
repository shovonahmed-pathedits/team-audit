"""
Date range picker widget for PySide6 - Grid layout for perfect alignment
"""
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QFormLayout, QLabel, QDateEdit, QCalendarWidget
)
from PySide6.QtCore import QDate, Qt, QEvent

from gui.theme import get_theme_colors


class DatePickerWidget(QWidget):
    """Widget for selecting date range - grid layout for perfect alignment"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup the date picker UI - grid layout for perfect alignment"""
        # Main layout - grid for perfect alignment
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setHorizontalSpacing(12)
        main_layout.setVerticalSpacing(10)

        self.colors = get_theme_colors()
        self.setStyleSheet(f"""
            QLabel {{
                color: {self.colors['text_primary']};
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                max-width: 80px;
                min-height: 26px;
                max-height: 26px;
            }}
            QDateEdit {{
                background-color: {self.colors['bg_primary']};
                color: {self.colors['text_primary']};
                border: 2px solid {self.colors['border']};
                border-radius: 6px;
                padding: 2px 6px;
                font-size: 13px;
                min-width: 140px;
                max-width: 140px;
                min-height: 26px;
                max-height: 26px;
            }}
            QDateEdit:hover {{
                border-color: {self.colors['primary']};
            }}
            QDateEdit:focus {{
                border-color: {self.colors['primary']};
            }}
            QDateEdit::up-button, QDateEdit::down-button {{
                background-color: {self.colors['bg_secondary']};
                border: none;
                border-radius: 4px;
            }}
            QCalendarWidget QToolButton {{
                color: {self.colors['text_primary']};
                background-color: {self.colors['bg_secondary']};
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                padding: 4px 12px;
            }}
            QCalendarWidget QToolButton:hover {{
                background-color: {self.colors['bg_tertiary']};
            }}
            QCalendarWidget QMenu {{
                background-color: {self.colors['popup_bg']};
                color: {self.colors['text_primary']};
                border: 1px solid {self.colors['border']};
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background-color: {self.colors['bg_secondary']};
                border-bottom: 1px solid {self.colors['border']};
            }}
        """)

        # Start date row
        start_label = QLabel("Start Date:")
        start_label.setFixedSize(80, 26)
        start_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setCalendarWidget(QCalendarWidget())
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setDisplayFormat("dd/MM/yy")
        self.start_date.setFixedSize(140, 26)

        # End date row
        end_label = QLabel("End Date:")
        end_label.setFixedSize(80, 26)
        end_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setCalendarWidget(QCalendarWidget())
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setDisplayFormat("dd/MM/yy")
        self.end_date.setFixedSize(140, 26)

        # Add to grid
        main_layout.addWidget(start_label, 0, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.start_date, 0, 1)
        main_layout.addWidget(end_label, 1, 0, Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.end_date, 1, 1)

        # Add right stretch
        main_layout.setColumnStretch(2, 1)

        # Install event filter for click-to-open calendar on line edits
        self.start_date.lineEdit().installEventFilter(self)
        self.end_date.lineEdit().installEventFilter(self)

        self.setLayout(main_layout)

    def eventFilter(self, obj, event):
        """Handle click events on date inputs to show calendar popup"""
        if event.type() == QEvent.Type.MouseButtonPress:
            if obj == self.start_date.lineEdit():
                self.start_date.showCalendar()
                return True
            elif obj == self.end_date.lineEdit():
                self.end_date.showCalendar()
                return True
        return super().eventFilter(obj, event)

    def get_start_date_api_format(self) -> str:
        """Get start date in API format (DD/MM/YY)"""
        return self.start_date.date().toString("dd/MM/yy")
    
    def get_end_date_api_format(self) -> str:
        """Get end date in API format (DD/MM/YY)"""
        return self.end_date.date().toString("dd/MM/yy")
    
    def get_date_range_display(self) -> str:
        """Get date range as display string"""
        start = self.start_date.date().toString("dd/MM/yy")
        end = self.end_date.date().toString("dd/MM/yy")
        if start == end:
            return start
        return f"{start} - {end}"
    
    def set_date_range(self, start_date: QDate, end_date: QDate):
        """Set date range programmatically"""
        self.start_date.setDate(start_date)
        self.end_date.setDate(end_date)
