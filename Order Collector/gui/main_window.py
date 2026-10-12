"""
Main dashboard window
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QProgressBar,
    QMessageBox,
    QFileDialog,
    QScrollArea,
    QDialog,
    QApplication,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QClipboard

from gui.theme import get_theme_colors
from gui.widgets.date_picker import DatePickerWidget
from gui.widgets.data_table import DataTableWidget
from services.data_fetcher import DataFetcher
from services.data_processor import DataProcessor


class FetchWorker(QThread):
    """Worker thread for fetching data without blocking UI"""

    progress = Signal(str, int)
    finished = Signal(bool, list, dict, str)

    def __init__(self, data_fetcher, start_date, end_date):
        super().__init__()
        self.data_fetcher = data_fetcher
        self.start_date = start_date
        self.end_date = end_date
        self._cancel_requested = False

    def cancel(self):
        """Request cancellation of the worker"""
        self._cancel_requested = True

    def run(self):
        """Run the fetch operation"""
        # Connect progress callback
        self.data_fetcher.set_progress_callback(
            lambda msg, val: (
                self.progress.emit(msg, val) if not self._cancel_requested else None
            )
        )

        # Check if already cancelled
        if self._cancel_requested:
            self.finished.emit(False, [], {}, "Fetch cancelled")
            return

        # Fetch orders - no location filter
        success, orders, meta, error = self.data_fetcher.fetch_orders_with_progress(
            location_id=None, start_date=self.start_date, end_date=self.end_date
        )

        # Don't emit finished if cancelled
        if not self._cancel_requested:
            self.finished.emit(success, orders, meta, error)


class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, api_client, on_logout_callback=None):
        super().__init__()
        self.api = api_client
        self.on_logout_callback = on_logout_callback  # Callback function for logout
        self.colors = get_theme_colors()
        self.data_fetcher = DataFetcher(api_client)
        self.current_data = []
        self.current_meta = {}
        self.start_date = None
        self.end_date = None

        # Set Window Icon (Fixes Taskbar Icon)
        try:
            import sys
            import os

            base_path = getattr(
                sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))
            )
            icon_path = os.path.join(base_path, "..", "Logo.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(base_path, "Logo.ico")
            if os.path.exists(icon_path):
                from PySide6.QtGui import QIcon

                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        """Setup the main window UI"""
        self.setWindowTitle("Order Collector - Dashboard")
        self.setMinimumSize(500, 795)

        # Central widget
        central_widget = QWidget()
        central_widget.setStyleSheet(f"background-color: {self.colors['bg_primary']};")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # Header - centered title with logout button
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("Order Collector")
        title_label.setObjectName("TitleLabel")
        title_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {self.colors['text_primary']};"
        )

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.colors["danger"]};
                color: {self.colors["button_text"]};
                border: none;
                border-radius: 6px;
                padding: 6px 11px;
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {self.colors["danger_hover"]};
            }}
        """)
        self.btn_logout.setMaximumWidth(70)

        header_layout.addStretch(2)
        header_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        header_layout.addStretch(1)
        header_layout.addWidget(self.btn_logout)

        main_layout.addWidget(header_widget)

        # Filter section - Date picker only (no location filter)
        filter_group = QWidget()
        filter_group.setStyleSheet(f"""
            QWidget {{
                background-color: {self.colors["bg_secondary"]};
                border: 2px solid {self.colors["border"]};
                border-radius: 8px;
            }}
        """)
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(20, 15, 20, 15)
        filter_layout.setSpacing(12)

        # Date picker - centered
        self.date_picker = DatePickerWidget()
        filter_layout.addWidget(
            self.date_picker, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # Fetch button - centered
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.btn_fetch = QPushButton("🔍 Fetch Orders")
        self.btn_fetch.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.colors["primary"]};
                color: {self.colors["button_text"]};
                border: none;
                border-radius: 8px;
                padding: 8px 30px;
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
        self.btn_fetch.setMinimumHeight(35)

        button_layout.addWidget(self.btn_fetch)
        button_layout.addStretch()

        filter_layout.addLayout(button_layout)

        main_layout.addWidget(filter_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(10)
        main_layout.addWidget(self.progress_bar)

        # Progress label
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("SubtitleLabel")
        self.progress_label.setVisible(False)
        main_layout.addWidget(self.progress_label)

        # Data table - wrapped in scroll area for clean scrolling
        self.data_table = DataTableWidget()
        self.data_table.verticalHeader().setVisible(False)
        self.data_table.setShowGrid(True)

        # Wrap table in scroll area (table's own scrollbar hidden)
        table_scroll = QScrollArea()
        table_scroll.setWidget(self.data_table)
        table_scroll.setWidgetResizable(True)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setStyleSheet(
            "QScrollArea { border: none; background-color: transparent; }"
        )
        main_layout.addWidget(table_scroll, stretch=1)

        # Copy buttons are now embedded in the table as the last row
        # (No separate copy buttons needed - handled by DataTableWidget)

        # Summary label
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("SubtitleLabel")
        main_layout.addWidget(self.summary_label)

    def connect_signals(self):
        """Connect widget signals"""
        self.btn_fetch.clicked.connect(self.on_fetch_clicked)
        self.btn_logout.clicked.connect(self.on_logout_clicked)

    def showEvent(self, event):
        """Called when window is shown"""
        super().showEvent(event)
        # No location loading needed - fetch all locations

    def on_fetch_clicked(self):
        """Handle fetch button click"""
        # Get filter values - no location filter, always fetch all
        self.start_date = self.date_picker.get_start_date_api_format()
        self.end_date = self.date_picker.get_end_date_api_format()

        # Validate date range
        from datetime import datetime

        try:
            start_dt = datetime.strptime(self.start_date, "%d/%m/%y")
            end_dt = datetime.strptime(self.end_date, "%d/%m/%y")

            if start_dt > end_dt:
                QMessageBox.warning(
                    self,
                    "Invalid Date Range",
                    "Start date cannot be after end date.\n\n"
                    "Please select a valid date range.",
                )
                return  # Stop execution
        except ValueError as e:
            QMessageBox.warning(
                self,
                "Invalid Date Format",
                f"Invalid date format: {str(e)}\n\nPlease select valid dates.",
            )
            return  # Stop execution

        # Disable UI during fetch
        self.set_ui_enabled(False)

        # Clear table and previous data
        self.data_table.clear_table()
        self.summary_label.setText("")
        self.current_data = []
        self.current_meta = {}

        # Stop any existing worker thread safely
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(3000):
                self.worker.terminate()
                self.worker.wait(1000)

        # Show progress
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(True)
        self.progress_label.setText("Initializing...")

        # Start worker thread - no location filter
        self.worker = FetchWorker(self.data_fetcher, self.start_date, self.end_date)
        self.worker.progress.connect(self.on_fetch_progress)
        self.worker.finished.connect(self.on_fetch_finished)
        self.worker.start()

    def on_fetch_progress(self, message: str, value: int):
        """Handle fetch progress updates"""
        self.progress_label.setText(message)
        if value >= 0:
            self.progress_bar.setValue(value)

    def on_fetch_finished(self, success: bool, orders: list, meta: dict, error: str):
        """Handle fetch completion"""
        try:
            # Hide progress
            self.progress_bar.setVisible(False)
            self.progress_label.setVisible(False)

            if success:
                # Process data
                self.current_data = orders
                self.current_meta = meta

                # Group by location
                processor = DataProcessor()
                grouped_data = processor.group_orders_by_location(orders)

                # Get API total_records from meta (unique order count)
                api_total_records = self.current_meta.get("api_total_records", 0)
                summary = processor.get_total_summary(orders, api_total_records)

                # Display in table (load_data already clears the table first)
                table_data = processor.format_for_display(grouped_data)

                # load_data() handles clearing, no need to call clear_table()
                self.data_table.load_data(table_data)

                # Add API total row with cancelled count
                self.data_table.set_api_total(api_total_records, summary["cancelled"])

                # Force UI update (repaint is sufficient)
                self.data_table.repaint()

                # Update summary - use API unique order count
                total_orders = summary["unique_orders"]
                total_locations = len(grouped_data)
                date_range = self.date_picker.get_date_range_display()

                self.summary_label.setText(
                    f"Date: {date_range} | {total_locations} vendors"
                )

                # Check for failed dates/pages from parallel fetch
                failed_dates = meta.get("failed_dates", [])
                failed_pages = meta.get("failed_pages", [])

                # Show warning if any failures
                if failed_dates or failed_pages:
                    warning_msg = "Warning: Some data could not be fetched:\n"
                    if failed_dates:
                        warning_msg += f"• Failed dates: {', '.join(failed_dates)}\n"
                    if failed_pages:
                        warning_msg += f"• Failed pages: {', '.join(failed_pages)}\n"
                    warning_msg += "\nPlease retry manually."

                    QMessageBox.warning(self, "Partial Fetch Complete", warning_msg)

                # Custom Success Dialog with Always On Top and Copy Button
                success_dialog = QDialog(self)
                success_dialog.setWindowTitle("Order Collector")
                # Force window to stay on top of all other apps
                success_dialog.setWindowFlags(
                    success_dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
                )
                success_dialog.setStyleSheet(f"""
                    QDialog {{ background-color: {self.colors["popup_bg"]}; border-radius: 8px; border: 2px solid {self.colors["primary"]}; }}
                    QLabel {{ color: {self.colors["text_primary"]}; font-size: 14px; font-weight: bold; }}
                    QPushButton {{ background-color: {self.colors["primary"]}; color: {self.colors["button_text"]}; border: none; border-radius: 6px; padding: 6px 12px; font-weight: bold; }}
                    QPushButton:hover {{ background-color: {self.colors["primary_hover"]}; }}
                """)

                dialog_layout = QVBoxLayout(success_dialog)
                dialog_layout.setSpacing(15)
                dialog_layout.setContentsMargins(20, 20, 20, 20)

                msg_label = QLabel(
                    f"Successfully fetched {total_orders} orders from {total_locations} vendors!"
                )
                msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                dialog_layout.addWidget(msg_label)

                btn_copy = QPushButton("Copy Summary")
                btn_copy.clicked.connect(
                    lambda: (
                        QApplication.clipboard().setText(
                            self.data_table.copy_total_column()
                        ),
                        success_dialog.accept(),  # Close dialog immediately after copy
                    )
                )
                dialog_layout.addWidget(btn_copy)

                success_dialog.exec()

            else:
                QMessageBox.critical(self, "Error", f"Failed to fetch orders:\n{error}")
                self.summary_label.setText("")

        except Exception as e:
            import traceback

            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error processing data:\n{str(e)}")

        # Re-enable UI
        self.set_ui_enabled(True)

    def set_ui_enabled(self, enabled: bool):
        """Enable/disable UI controls"""
        self.btn_fetch.setEnabled(enabled)
        self.date_picker.setEnabled(enabled)

    def on_logout_clicked(self):
        """Handle logout - clear session AND credentials"""
        reply = QMessageBox.question(
            self,
            "Confirm Logout",
            "Are you sure you want to logout?\n\n"
            "Note: Your saved credentials will be deleted.\n"
            "You will need to log in again next time.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from utils.credential_manager import CredentialManager

            # Get saved email
            email = CredentialManager.get_saved_email()

            # Clear session file
            if email:
                self.api.clear_session(email)

                # DELETE credentials from Windows Vault
                CredentialManager.delete_credentials(email)
                CredentialManager.clear_email()

            # Logout API
            self.api.logout()

            # Close dashboard
            self.close()

            # Call logout callback to show login screen
            if self.on_logout_callback:
                self.on_logout_callback()
