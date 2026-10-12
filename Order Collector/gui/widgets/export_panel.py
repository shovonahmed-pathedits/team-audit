"""
Export panel widget with Excel/CSV export buttons
"""
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QFileDialog
)
from PySide6.QtCore import Signal


class ExportPanel(QWidget):
    """Widget for exporting data to Excel/CSV"""
    
    excel_exported = Signal(str)  # Emitted with filepath when Excel export succeeds
    csv_exported = Signal(str)    # Emitted with filepath when CSV export succeeds
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._connect_signals()
    
    def setup_ui(self):
        """Setup the export panel UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        
        # Export label
        self.label = QLabel("Export:")
        self.label.setStyleSheet("color: #495057; font-size: 13px; font-weight: bold;")
        
        # Excel export button - teal color
        self.btn_excel = QPushButton("📊 Export to Excel")
        self.btn_excel.setStyleSheet("""
            QPushButton {
                background-color: #95e1d5;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #7dd3c7;
            }
            QPushButton:pressed {
                background-color: #6bc4b9;
            }
            QPushButton:disabled {
                background-color: #dee2e6;
                color: #adb5bd;
            }
        """)
        
        # CSV export button - blue color
        self.btn_csv = QPushButton("📄 Export to CSV")
        self.btn_csv.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #000000;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: bold;
                min-width: 150px;
            }
            QPushButton:hover {
                background-color: #7aa8f8;
            }
            QPushButton:pressed {
                background-color: #6b9af0;
            }
            QPushButton:disabled {
                background-color: #dee2e6;
                color: #adb5bd;
            }
        """)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #495057; font-size: 12px;")
        
        # Add widgets
        layout.addWidget(self.label)
        layout.addWidget(self.btn_excel)
        layout.addWidget(self.btn_csv)
        layout.addWidget(self.status_label)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def _connect_signals(self):
        """Connect button signals"""
        self.btn_excel.clicked.connect(self.on_excel_clicked)
        self.btn_csv.clicked.connect(self.on_csv_clicked)
    
    def on_excel_clicked(self):
        """Handle Excel export button click"""
        self.excel_exported.emit("xlsx")
    
    def on_csv_clicked(self):
        """Handle CSV export button click"""
        self.csv_exported.emit("csv")
    
    def set_status(self, message: str):
        """Set status message"""
        self.status_label.setText(message)
    
    def clear_status(self):
        """Clear status message"""
        self.status_label.setText("")
    
    def set_buttons_enabled(self, enabled: bool):
        """Enable/disable export buttons"""
        self.btn_excel.setEnabled(enabled)
        self.btn_csv.setEnabled(enabled)
