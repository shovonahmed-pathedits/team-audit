"""
Data table widget for displaying order results
"""
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush

from gui.theme import get_theme_colors


class DataTableWidget(QTableWidget):
    """Table widget for displaying order data by location"""
    
    COLUMNS = [
        "Location / Vendor",
        "Total Orders",
        "Cancelled",
        "Total Fulfilled"
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = get_theme_colors()
        self.api_total_orders = 0
        self.api_total_cancelled = 0
        self.vendor_data = []  # Store data for copy buttons
        self.btn_copy_total = None
        self.btn_copy_fulfilled = None
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the table UI"""
        # Set columns
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        
        # Configure columns
        header = self.horizontalHeader()
        # Column 0 (Location) stretches to fill remaining space
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Columns 1-3 (numeric) size to content
        for i in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        # Disable sorting - preserves vendor order from data processor
        self.setSortingEnabled(False)
        
        # Hide Cancelled column (index 2) - data still used for calculations
        self.setColumnHidden(2, True)
        
        # Selection behavior
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        
        # Alternating row colors
        self.setAlternatingRowColors(True)
        
        # Hide vertical header (row numbers)
        self.verticalHeader().setVisible(False)

        # Hide vertical scrollbar (scroll handled by parent QScrollArea)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Grid style
        self.setGridStyle(Qt.PenStyle.SolidLine)
        
        self.setStyleSheet(f"""
            QTableWidget {{
                color: {self.colors['text_primary']};
                gridline-color: {self.colors['border']};
                background-color: {self.colors['bg_primary']};
                border: 2px solid {self.colors['border']};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                color: {self.colors['text_primary']};
                padding: 8px;
                background-color: {self.colors['bg_primary']};
            }}
            QTableWidget::item:selected {{
                color: {self.colors['button_text']};
                background-color: {self.colors['primary']};
            }}
            QTableWidget::item:alternate {{
                background-color: {self.colors['table_alt_bg']};
            }}
            QHeaderView::section {{
                background-color: {self.colors['bg_secondary']};
                color: {self.colors['text_primary']};
                padding: 10px;
                font-weight: bold;
                border: none;
                border-bottom: 2px solid {self.colors['border']};
            }}
        """)
    
    def clear_table(self):
        """Clear all data from the table - completely removes all rows"""
        # Remove all rows one by one (most reliable method in PySide6)
        while self.rowCount() > 0:
            self.removeRow(0)
        # Don't toggle sorting here - it causes issues with empty table
    
    def load_data(self, data: list):
        """
        Load data into the table

        Args:
            data: List of rows
        """
        # Disable sorting before making changes
        self.setSortingEnabled(False)

        # Clear all existing rows completely
        while self.rowCount() > 0:
            self.removeRow(0)

        # Store vendor data for copy buttons (exclude summary row later)
        self.vendor_data = []

        for row_idx, row_data in enumerate(data):
            # Store vendor data for copy functionality
            if len(row_data) >= 4:
                self.vendor_data.append({
                    'vendor': str(row_data[0]),
                    'total': str(row_data[1]),
                    'cancelled': str(row_data[2]),
                    'fulfilled': str(row_data[3])
                })

            # Insert new row (don't use setRowCount to avoid caching issues)
            self.insertRow(row_idx)

            for col_idx, value in enumerate(row_data):
                # Ensure value is not None or empty
                display_value = str(value) if value is not None else "0"

                item = QTableWidgetItem(display_value)

                # Set text color for all cells
                item.setForeground(QBrush(QColor(self.colors['text_primary'])))

                # Center align numeric columns
                if col_idx > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    # Make location name bold
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor(self.colors['text_primary'])))

                self.setItem(row_idx, col_idx, item)

        # Force table to update display
        self.viewport().update()
        self.repaint()

        # Keep sorting disabled to preserve vendor order
        self.setSortingEnabled(False)
    
    def get_row_count(self) -> int:
        """Get number of data rows (excluding summary row)"""
        return self.rowCount() - 1 if self.api_total_orders > 0 else self.rowCount()

    def set_api_total(self, total: int, total_cancelled: int = 0):
        """Set API pagination total, cancelled count, and add summary + button rows"""
        self.api_total_orders = total
        self.api_total_cancelled = total_cancelled
        self._add_summary_row()
        self._add_button_row()

    def _add_summary_row(self):
        """Add a summary row: Total | API Total | - | (API Total - API Cancelled)"""
        if self.api_total_orders == 0 or self.rowCount() == 0:
            return

        # Calculate fulfilled: API total - API total cancelled (ALL cancelled orders)
        total_fulfilled = self.api_total_orders - self.api_total_cancelled

        # Insert summary row at the end
        summary_row = self.rowCount()
        self.insertRow(summary_row)

        summary_bg = QColor(self.colors['bg_secondary'])
        summary_text = QColor(self.colors['text_primary'])
        summary_subtle = QColor(self.colors['text_secondary'])

        # Column 0: "All"
        label_item = QTableWidgetItem("All")
        font = label_item.font()
        font.setBold(True)
        font.setPointSize(11)
        label_item.setFont(font)
        label_item.setForeground(QBrush(summary_text))
        label_item.setBackground(QBrush(summary_bg))
        self.setItem(summary_row, 0, label_item)

        # Column 1: API total (unique orders)
        total_item = QTableWidgetItem(str(self.api_total_orders))
        font = total_item.font()
        font.setBold(True)
        font.setPointSize(11)
        total_item.setFont(font)
        total_item.setForeground(QBrush(summary_text))
        total_item.setBackground(QBrush(summary_bg))
        total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(summary_row, 1, total_item)

        # Column 2: Dash
        dash_item = QTableWidgetItem("-")
        dash_item.setForeground(QBrush(summary_subtle))
        dash_item.setBackground(QBrush(summary_bg))
        dash_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(summary_row, 2, dash_item)

        # Column 3: Total fulfilled (sum)
        fulfilled_item = QTableWidgetItem(str(total_fulfilled))
        font = fulfilled_item.font()
        font.setBold(True)
        font.setPointSize(11)
        fulfilled_item.setFont(font)
        fulfilled_item.setForeground(QBrush(summary_text))
        fulfilled_item.setBackground(QBrush(summary_bg))
        fulfilled_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(summary_row, 3, fulfilled_item)

    def _add_button_row(self):
        """Add a row with copy buttons embedded in the table"""
        from PySide6.QtWidgets import QPushButton, QWidget, QHBoxLayout

        button_row = self.rowCount()
        self.insertRow(button_row)

        # Set row height for compact buttons with centering space
        self.setRowHeight(button_row, 50)

        # Column 0: Empty
        empty_item = QTableWidgetItem("")
        empty_item.setBackground(QBrush(QColor("#f8f9fa")))
        self.setItem(button_row, 0, empty_item)

        # Column 1: Copy Total button (centered in cell)
        container1 = QWidget()
        layout1 = QHBoxLayout(container1)
        layout1.setContentsMargins(0, 0, 0, 0)
        layout1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_copy_total = QPushButton("Copy")
        self.btn_copy_total.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7aa8f8;
            }
            QPushButton:pressed {
                background-color: #6b9af0;
            }
        """)
        self.btn_copy_total.setMinimumHeight(28)
        self.btn_copy_total.clicked.connect(self._on_copy_total_clicked)
        layout1.addWidget(self.btn_copy_total)
        self.setCellWidget(button_row, 1, container1)

        # Column 2: Empty
        empty_item2 = QTableWidgetItem("")
        empty_item2.setBackground(QBrush(QColor("#f8f9fa")))
        self.setItem(button_row, 2, empty_item2)

        # Column 3: Copy Fulfilled button (centered in cell)
        container2 = QWidget()
        layout2 = QHBoxLayout(container2)
        layout2.setContentsMargins(0, 0, 0, 0)
        layout2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.btn_copy_fulfilled = QPushButton("Copy")
        self.btn_copy_fulfilled.setStyleSheet("""
            QPushButton {
                background-color: #95e1d5;
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #7dd3c7;
            }
            QPushButton:pressed {
                background-color: #6bc4b9;
            }
        """)
        self.btn_copy_fulfilled.setMinimumHeight(28)
        self.btn_copy_fulfilled.clicked.connect(self._on_copy_fulfilled_clicked)
        layout2.addWidget(self.btn_copy_fulfilled)
        self.setCellWidget(button_row, 3, container2)

    def copy_total_column(self) -> str:
        """Copy vendor name + total orders to clipboard"""
        if not self.vendor_data:
            return ""

        lines = []
        for data in self.vendor_data:
            lines.append(f"{data['vendor']}\t{data['total']}")

        # Add API total at bottom
        if self.api_total_orders > 0:
            lines.append(f"Total Unique Orders\t{self.api_total_orders}")

        return "\n".join(lines)

    def copy_fulfilled_column(self) -> str:
        """Copy vendor name + fulfilled to clipboard"""
        if not self.vendor_data:
            return ""

        lines = []
        for data in self.vendor_data:
            lines.append(f"{data['vendor']}\t{data['fulfilled']}")

        # Add total at bottom (API total - API total cancelled)
        total_fulfilled = self.api_total_orders - self.api_total_cancelled
        lines.append(f"Total Fulfilled\t{total_fulfilled}")

        return "\n".join(lines)

    def _on_copy_total_clicked(self):
        """Handle Copy Total button click"""
        from PySide6.QtWidgets import QApplication, QMessageBox

        text = self.copy_total_column()
        if not text:
            QMessageBox.information(self, "Copy Total", "No data to copy. Fetch orders first.")
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        QMessageBox.information(self, "Copy Total Orders",
            f"Copied {len(self.vendor_data)} vendor and total to clipboard!\n\n"
            f"You can now paste into Excel or other spreadsheet apps.")

    def _on_copy_fulfilled_clicked(self):
        """Handle Copy Fulfilled button click"""
        from PySide6.QtWidgets import QApplication, QMessageBox

        text = self.copy_fulfilled_column()
        if not text:
            QMessageBox.information(self, "Copy Fulfilled", "No data to copy. Fetch orders first.")
            return

        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        QMessageBox.information(self, "Copy Fulfilled",
            f"Copied {len(self.vendor_data)} vendors to clipboard!\n\n"
            f"You can now paste into Excel or other spreadsheet apps.")
