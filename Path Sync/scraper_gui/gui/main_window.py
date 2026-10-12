"""Main window — primary GUI application window with all scraping controls."""

import os
import re
import sys
import threading
from typing import Any, Dict, List, Tuple

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFrame,
    QMessageBox,
    QFileDialog,
    QDialog,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QTimer,
    QThread,
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
)
from PySide6.QtGui import (
    QKeySequence,
    QAction,
    QIcon,
    QPainter,
    QColor,
    QFontMetrics,
    QLinearGradient,
)

from config import (
    APP_NAME,
    THEME,
    DEFAULT_LOCATION_ID,
    OUTPUT_DIR,
    resolve_sm_display_name,
    sm_priority,
    safe_str,
    PARALLEL_CONFIG,
)
from config.google_sync import (
    is_google_sync_configured,
    load_google_sync_settings,
)
from google_sheets_sync import normalize_results_for_sheet, sync_rows_in_batches
from logger import logger
from scraper import AssignmentScraper
from gui.google_sync_dialog import GoogleSyncSetupDialog
from gui.syncing_popup import SyncingPopup

from gui.completion_toast import CompletionToast
from gui.success_toast import SuccessToast
from gui.sync_complete_toast import SyncCompleteToast

# Import credential and session managers (with fallback)
try:
    from credentials import CredentialManager
except Exception:
    CredentialManager = None

try:
    from session_manager import SessionManager
except Exception:
    SessionManager = None

# Import login window
from auth.login_window import LoginWindow


class ScraperThread(QThread):
    """Background thread for scraping."""

    finished = Signal()
    error_occurred = Signal(str)
    progress_updated = Signal(int, int)

    def __init__(
        self,
        urls: List[str],
        email: str,
        pwd: str,
        existing_session=None,
        pause_event=None,
    ):
        super().__init__()
        self.urls = urls
        self.email = email
        self.pwd = pwd
        self.pause_event = pause_event or threading.Event()
        self.pause_event.set()
        self.existing_session_cookies = None
        self.existing_session_headers = {}

        # FIX C1: Deep-copy session cookies preserving all attributes (domain, path, secure, etc.)
        if existing_session:
            try:
                import copy

                # Deep-copy the entire RequestsCookieJar — preserves domain, path, expires, secure flags
                self.existing_session_cookies = copy.deepcopy(existing_session.cookies)
                # Copy relevant headers
                self.existing_session_headers = {
                    k: v
                    for k, v in existing_session.headers.items()
                    if k
                    not in {
                        "User-Agent",
                        "Accept",
                        "Accept-Encoding",
                        "Accept-Language",
                        "Origin",
                        "Referer",
                        "Cache-Control",
                        "Pragma",
                    }
                }
                logger.info(
                    f"Session snapshot created ({len(self.existing_session_cookies)} cookies)"
                )
            except Exception as e:
                logger.warning(f"Failed to snapshot session: {e}")
                self.existing_session_cookies = None
                self.existing_session_headers = {}

        self.results = []
        self.error_msg = None

    def run(self):
        logger.info(f"Starting scrape for {len(self.urls)} URLs")
        logger.info(f"Thread URLs: {self.urls}")
        logger.info(f"Thread email: '{self.email}', has pwd: {bool(self.pwd)}")
        logger.info(
            f"Has session cookies snapshot: {self.existing_session_cookies is not None}"
        )
        if self.existing_session_cookies:
            logger.info(f"Session cookies count: {len(self.existing_session_cookies)}")
        try:
            scraper = AssignmentScraper()
            logger.info(
                f"Scraper created. Scraper stored email: '{scraper._stored_email}'"
            )

            # Try to reuse existing session to avoid redundant login
            if self.existing_session_cookies:
                logger.info(
                    "Attempting to reuse existing session (thread-safe deep copy)..."
                )
                try:
                    # Restore cookies using requests' built-in method (preserves all attributes from CookieJar)
                    scraper.session.cookies.update(self.existing_session_cookies)
                    # Restore headers from snapshot
                    scraper.session.headers.update(self.existing_session_headers)
                    logger.info(
                        f"Restored {len(self.existing_session_cookies)} cookies from snapshot"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to restore session from snapshot: {e}. Falling back to login."
                    )
                    self.existing_session_cookies = None

                # Quick validation only if clone succeeded
                if self.existing_session_cookies and scraper._is_session_valid():
                    logger.info("[OPTIMIZED] Session reuse successful - skipping login")
                    scraper.is_authenticated = True
                else:
                    if self.existing_session_cookies:
                        logger.info("Cloned session expired, falling back to login")
                    else:
                        logger.info("Proceeding with login (session clone failed)")
                    ok, msg = scraper.login(self.email, self.pwd)
                    if not ok:
                        self.error_msg = f"Login failed: {msg}"
                        logger.error(f"Login failed: {msg}")
                        self.error_occurred.emit(str(msg))
                        return
            else:
                # No existing session, must login
                logger.info("No existing session provided, logging in...")
                ok, msg = scraper.login(self.email, self.pwd)
                if not ok:
                    self.error_msg = f"Login failed: {msg}"
                    logger.error(f"Login failed: {msg}")
                    self.error_occurred.emit(str(msg))
                    return

            if SessionManager:
                try:
                    SessionManager.save_session(scraper.session)
                except Exception:
                    pass

            logger.info("Authenticated, starting bulk scrape")

            def progress_callback(current, total):
                self.progress_updated.emit(current, total)

            # Auto-detect workers based on URL count
            url_count = len(self.urls)
            max_workers = min(url_count, 5)  # 1-4 = use that many, 5+ = max 5

            stop_check = self.isInterruptionRequested

            if max_workers == 1:
                logger.info(f"Using single-worker mode for {url_count} URL(s)")
                self.results = scraper.scrape_bulk(
                    self.urls,
                    self.email,
                    self.pwd,
                    progress_callback,
                    pause_event=self.pause_event,
                    stop_check=stop_check,
                )
            else:
                logger.info(
                    f"Using PARALLEL mode with {max_workers} workers for {url_count} URLs"
                )
                self.results = scraper.scrape_bulk_parallel(
                    self.urls,
                    self.email,
                    self.pwd,
                    progress_callback,
                    max_workers,
                    pause_event=self.pause_event,
                    stop_check=stop_check,
                )
            logger.info(f"Scrape complete, got {len(self.results)} results")
            if self.results:
                logger.info(f"First result keys: {list(self.results[0].keys())}")
                if "error" in self.results[0]:
                    logger.warning(
                        f"First result is an ERROR: {self.results[0]['error']}"
                    )

            self.finished.emit()

        except Exception as e:
            import traceback

            self.error_msg = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"Error in scrape thread: {e}")
            logger.error(traceback.format_exc())
            self.error_occurred.emit(str(e))


class GoogleSyncThread(QThread):
    """Background thread for Google Sheets sync."""

    finished_sync = Signal(int)
    error_occurred = Signal(str)
    retrying = Signal(int, int)

    def __init__(self, settings, rows: List[Dict[str, str]]):
        super().__init__()
        self.settings = settings
        self.rows = rows

    def run(self):
        try:

            def on_retry(attempt, max_attempts):
                self.retrying.emit(attempt, max_attempts)

            appended = sync_rows_in_batches(
                self.settings,
                self.rows,
                retry_callback=on_retry,
                cancel_check=self.isInterruptionRequested,
            )
            self.finished_sync.emit(appended)
        except Exception as e:
            logger.error(f"Google sync failed: {e}")
            self.error_occurred.emit(str(e))


class RoundedGradientProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._track_color = QColor("#29292d")
        self._chunk_start = QColor("#56c0b3")
        self._chunk_end = QColor("#4bb0a4")
        self._text_color = QColor("#ffffff")

    def setColors(
        self, track_color: str, chunk_start: str, chunk_end: str, text_color: str
    ):
        self._track_color = QColor(track_color)
        self._chunk_start = QColor(chunk_start)
        self._chunk_end = QColor(chunk_end)
        self._text_color = QColor(text_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar = self.rect()
        padding = 2
        track = bar.adjusted(padding, padding, -padding, -padding)

        painter.setBrush(self._track_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track, 4, 4)

        rng = self.maximum() - self.minimum()
        ratio = (self.value() - self.minimum()) / max(rng, 1)
        chunk_w = int(track.width() * ratio)
        if chunk_w > 0:
            chunk = QRectF(track.x(), track.y(), float(chunk_w), float(track.height()))
            grad = QLinearGradient(chunk.topLeft(), chunk.topRight())
            grad.setColorAt(0, self._chunk_start)
            grad.setColorAt(1, self._chunk_end)
            painter.setBrush(grad)
            painter.drawRoundedRect(chunk, 4, 4)

        if self.isTextVisible():
            painter.setPen(self._text_color)
            painter.setFont(self.font())
            painter.drawText(bar, Qt.AlignmentFlag.AlignCenter, self.text())

        painter.end()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, email: str = "", password: str = "", scraper=None):
        super().__init__()
        self.email = email
        self.password = password
        # Reuse passed scraper or create new one
        if scraper is not None:
            self.scraper = scraper
        else:
            self.scraper = AssignmentScraper()
        self.results = []
        self.urls = []
        self.thread = None
        self.progress_animation = None
        self._scrape_processing = False  # Guard flag to prevent double-finish
        self._pause_event = threading.Event()
        self._pause_event.set()
        self.progress_current = 0
        self.progress_total = 0
        self._cancelled_by_user = False
        self.active_assignment_count = 0
        self._completion_toast = None
        self._success_toast = None  # Success toast for copy feedback
        self._syncing_popup = None
        self.google_sync_settings = load_google_sync_settings()
        self.google_sync_thread = None

        # Set window icon - use bundled icon for frozen exe
        if getattr(sys, "frozen", False):
            self.setWindowIcon(QIcon(sys._MEIPASS + os.sep + "sync.ico"))

        self.setMinimumSize(500, 795)

        # FIX M1: Validate session on startup - but skip if already validated by main.py
        if not getattr(self.scraper, "is_authenticated", False):
            if self.scraper._is_session_valid():
                self.scraper.is_authenticated = True
                logger.info(
                    "MainWindow: Session validated on startup, session reuse enabled"
                )
        else:
            logger.info("MainWindow: Using session from main.py (already validated)")

        self.setup_ui()
        self.setup_styles()
        self._set_progress_state("idle", current=0, total=0, animate=False)
        self.setup_shortcuts()
        self.refresh_google_sync_status()
        self.status_text_label.setText("Ready to scrape")

    def setup_shortcuts(self):
        self.start_scraper_action = QAction(self)
        self.start_scraper_action.setShortcut(QKeySequence("Ctrl+Return"))
        self.start_scraper_action.triggered.connect(self.start_scrape)
        self.addAction(self.start_scraper_action)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def setup_ui(self):
        self.setWindowTitle(APP_NAME)
        self.resize(500, 795)
        self._center_on_screen()

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(24, 8, 24, 24)
        main_layout.setSpacing(8)

        header = self.create_header()
        main_layout.addWidget(header, 0)

        main_layout.addStretch(1)

        card_container = QFrame()
        card_container.setObjectName("card_container")
        card_container.setStyleSheet(
            "QFrame#card_container { background: transparent; }"
        )
        card_layout = QVBoxLayout(card_container)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(16)

        source_dest = self.create_source_dest_section()
        card_layout.addWidget(source_dest, 0)

        activity = self.create_activity_section()
        card_layout.addWidget(activity, 0)

        status_group = self.create_status_section()
        card_layout.addWidget(status_group, 0)

        main_layout.addWidget(card_container, 0)

        main_layout.addStretch(1)

        self.stop_btn = QPushButton("🛑  Stop Process")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setMinimumHeight(44)
        self.stop_btn.setObjectName("stop_btn")
        self.stop_btn.clicked.connect(self._toggle_stop_resume)
        self.stop_btn.setEnabled(False)

        self.cancel_btn = QPushButton("✕  Cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setMinimumHeight(44)
        self.cancel_btn.setObjectName("cancel_btn")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_scrape)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #E55050;
                color: #ffffff;
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #B33E3E;
            }
            QPushButton:disabled {
                background: #d0d0d0;
                color: #999999;
            }
        """)

        stop_row = QHBoxLayout()
        stop_row.setSpacing(8)
        stop_row.addWidget(self.stop_btn)
        stop_row.addWidget(self.cancel_btn)
        main_layout.addLayout(stop_row)

        sync_bar = self.create_sync_bar()
        main_layout.addWidget(sync_bar, 0)

        self.statusBar().showMessage("Ready  |  Press Ctrl+Enter to start scraping")

    def create_header(self) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.setCursor(Qt.PointingHandCursor)
        self.logout_btn.setMinimumHeight(28)
        self.logout_btn.setObjectName("danger_btn")
        self.logout_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["danger"]};
                color: {THEME["button_text"]};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {THEME["danger_hover"]};
            }}
        """)
        self.logout_btn.clicked.connect(self.logout)

        fm = QFontMetrics(self.logout_btn.font())
        btn_w = fm.horizontalAdvance("Logout") + 26
        left_spacer = QSpacerItem(btn_w, 0, QSizePolicy.Policy.Fixed)
        header_row.addItem(left_spacer)

        header_row.addStretch(1)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text"]};
                font-size: 28px;
                font-weight: bold;
                padding: 2px 0;
            }}
        """)
        header_row.addWidget(title)

        header_row.addStretch(1)
        header_row.addWidget(self.logout_btn)

        layout.addLayout(header_row)
        return frame

    def create_source_dest_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("source_dest_card")
        card.setStyleSheet(f"""
            QFrame#source_dest_card {{
                background: #262626;
                border: none;
                border-radius: 10px;
            }}
            QLabel {{
                color: #ffffff;
                background: transparent;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        card_title = QLabel("   Source & Destination")
        card_title.setStyleSheet("font-size: 16px; font-weight: 500; color: #ffffff;")
        layout.addWidget(card_title)

        self.url_status_label = QLabel(
            "   Click the 'Input Links' button to add order links."
        )
        self.url_status_label.setStyleSheet(
            "font-size: 13px; font-weight: 400; color: #B3B3B3;"
        )
        layout.addWidget(self.url_status_label)

        self.input_links_btn = QPushButton("Input Links")
        self.input_links_btn.setCursor(Qt.PointingHandCursor)
        self.input_links_btn.setMinimumHeight(44)
        self.input_links_btn.clicked.connect(self._open_link_input_dialog)
        self.input_links_btn.setStyleSheet(f"""
            QPushButton {{
                background: #ffffff;
                color: #000000;
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #cccccc;
            }}
        """)
        layout.addWidget(self.input_links_btn)

        return card

    def create_activity_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("activity_card")
        card.setStyleSheet(f"""
            QFrame#activity_card {{
                background: #262626;
                border: 1px solid #404040;
                border-radius: 10px;
            }}
            QLabel {{
                color: #ffffff;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        card_title = QLabel("   Activity")
        card_title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(card_title)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(12)

        self.scrape_btn = QPushButton("Start Scraping")
        self.scrape_btn.setCursor(Qt.PointingHandCursor)
        self.scrape_btn.setMinimumHeight(44)
        self.scrape_btn.setObjectName("scrape_btn")
        self.scrape_btn.clicked.connect(self.start_scrape)
        self.scrape_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["primary"]};
                color: {THEME["button_text"]};
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {THEME["primary_hover"]};
            }}
            QPushButton:disabled {{
                background: #d0d0d0;
                color: #999999;
            }}
        """)
        primary_row.addWidget(self.scrape_btn)

        self.google_sync_btn = QPushButton("Sync to Google Sheet")
        self.google_sync_btn.setCursor(Qt.PointingHandCursor)
        self.google_sync_btn.setMinimumHeight(44)
        self.google_sync_btn.setObjectName("google_sync_btn")
        self.google_sync_btn.clicked.connect(self.sync_to_google_sheet)
        self.google_sync_btn.setEnabled(False)
        primary_row.addWidget(self.google_sync_btn)

        layout.addLayout(primary_row)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(12)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.setMinimumHeight(44)
        self.copy_btn.setObjectName("copy_btn")
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.copy_btn.setEnabled(False)
        self.copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: #e8e8e8;
                color: {THEME["button_text"]};
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #cccccc;
            }}
            QPushButton:disabled {{
                background: {THEME["secondary"]};
                color: {THEME["text_muted"]};
            }}
        """)
        secondary_row.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setMinimumHeight(44)
        self.clear_btn.setObjectName("clear_btn")
        self.clear_btn.clicked.connect(self.clear_all)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: #e8e8e8;
                color: {THEME["button_text"]};
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #cccccc;
            }}
            QPushButton:disabled {{
                background: {THEME["secondary"]};
                color: {THEME["text_muted"]};
            }}
        """)
        secondary_row.addWidget(self.clear_btn)

        layout.addLayout(secondary_row)

        return card

    def create_status_section(self) -> QFrame:
        card = QFrame()
        card.setObjectName("status_card")
        card.setStyleSheet(f"""
            QFrame#status_card {{
                background: #262626;
                border: 1px solid #404040;
                border-radius: 10px;
            }}
            QLabel {{
                color: #ffffff;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        card_title = QLabel("Status")
        card_title.setStyleSheet("font-size: 16px; font-weight: 500;")
        layout.addWidget(card_title)

        self.status_text_label = QLabel("Ready to scrape")
        self.status_text_label.setStyleSheet("font-size: 14px; font-weight: 500;")
        layout.addWidget(self.status_text_label)

        self.last_scrape_label = QLabel("Last Scrape: Never")
        self.last_scrape_label.setStyleSheet(
            "font-size: 13px; font-weight: 400; color: #B3B3B3;"
        )
        layout.addWidget(self.last_scrape_label)

        self.progress_bar = RoundedGradientProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setFormat("0/0")
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                font-size: 11px;
                font-weight: 500;
                font-family: "JetBrains Mono", "SF Mono", monospace;
            }
        """)
        layout.addWidget(self.progress_bar)

        return card

    def create_sync_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sync_bar")
        bar.setStyleSheet(f"""
            QFrame#sync_bar {{
                background: {THEME["surface"]};
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
            }}
            QLabel {{
                color: {THEME["text"]};
                background: transparent;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        self.google_setup_btn = QPushButton("Google Sync Setup")
        self.google_setup_btn.setCursor(Qt.PointingHandCursor)
        self.google_setup_btn.setMinimumHeight(36)
        self.google_setup_btn.clicked.connect(self.open_google_sync_setup)
        self.google_setup_btn.setStyleSheet(f"""
            QPushButton {{
                background: #e8e8e8;
                color: {THEME["button_text"]};
                border: 1px solid {THEME["border"]};
                border-radius: 18px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: #cccccc;
            }}
        """)
        layout.addWidget(self.google_setup_btn)

        layout.addStretch()

        self.google_sync_status_label = QLabel("Google Sync: Not configured")
        self.google_sync_status_label.setStyleSheet(
            "font-size: 12px; font-weight: 500; color: #666666;"
        )
        layout.addWidget(self.google_sync_status_label)

        return bar

    def _open_link_input_dialog(self):
        class PlainTextPasteEdit(QTextEdit):
            def insertFromMimeData(self, source):
                if source.hasText():
                    self.insertPlainText(source.text())

        dialog = QDialog(self)
        dialog.setWindowTitle(APP_NAME)
        dialog.setMinimumSize(500, 500)
        dialog.resize(500, 520)

        pr = self.geometry()
        x = pr.x() + (pr.width() - 500) // 2
        y = pr.y() + (pr.height() - 520) // 2
        dialog.move(x, y)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel("Paste or type URLs below (one per line):")
        info.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(info)

        url_edit = PlainTextPasteEdit()
        url_edit.setAcceptRichText(False)
        url_edit.setPlaceholderText(
            "https://tista.app/team_coordinator/assignment_details/..."
        )
        url_edit.setStyleSheet(f"""
            QTextEdit {{
                padding: 6px;
                border: 1px solid {THEME["border"]};
                border-radius: 6px;
                font-size: 12px;
                font-family: 'Consolas', monospace;
                background: {THEME["input_bg"]};
            }}
            QTextEdit:focus {{
                border-color: {THEME["input_focus"]};
            }}
        """)
        layout.addWidget(url_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        paste_btn = QPushButton("Paste")
        paste_btn.setCursor(Qt.PointingHandCursor)
        paste_btn.setMinimumHeight(36)
        paste_btn.setStyleSheet("""
            QPushButton {
                background: #F07900;
                color: #000000;
                border: none;
                border-radius: 18px;
                padding: 6px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #B35900;
            }
        """)
        paste_btn.clicked.connect(
            lambda: url_edit.insertPlainText(QApplication.clipboard().text())
        )
        btn_row.addWidget(paste_btn)

        confirm_btn = QPushButton("Confirm")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setMinimumHeight(36)
        confirm_btn.setStyleSheet("""
            QPushButton {
                background: #000000;
                color: #ffffff;
                border: none;
                border-radius: 18px;
                padding: 6px 20px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #333333;
            }
        """)
        confirm_btn.clicked.connect(lambda: self._confirm_urls(dialog, url_edit))
        btn_row.addWidget(confirm_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        dialog.exec()

    def _confirm_urls(self, dialog, url_edit):
        urls_text = url_edit.toPlainText().strip()
        if not urls_text:
            QMessageBox.warning(dialog, APP_NAME, "Please enter at least one URL.")
            return

        valid_urls, invalid_entries = self.validate_assignment_urls(urls_text)

        if not valid_urls:
            QMessageBox.warning(
                dialog,
                APP_NAME,
                "No valid assignment-detail links were found.\n\n"
                + self.format_invalid_link_message(invalid_entries),
            )
            return

        if invalid_entries:
            QMessageBox.warning(
                dialog,
                APP_NAME,
                f"{len(invalid_entries)} invalid link(s) will be skipped.\n\n"
                + self.format_invalid_link_message(invalid_entries),
            )

        self.urls = valid_urls
        plural = "Orders" if len(valid_urls) > 1 else "Order"
        self.url_status_label.setText(
            f"   {len(valid_urls)} {plural} in queue for processing."
        )
        self.url_status_label.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #ffffff;"
        )
        self._update_start_button_state()

        dialog.accept()

    def _update_start_button_state(self):
        has_urls = len(self.urls) > 0
        self.scrape_btn.setEnabled(has_urls)
        color = THEME["button_text"] if has_urls else "#999999"
        bg = THEME["primary"] if has_urls else THEME["secondary"]
        self.scrape_btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {color};
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {THEME["primary_hover"] if has_urls else THEME["secondary_hover"]};
            }}
            QPushButton:disabled {{
                background: {THEME["secondary"]};
                color: {THEME["text_muted"]};
            }}
        """)

    def _toggle_stop_resume(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.stop_btn.setText("▶  Resume Process")
            self.stop_btn.setStyleSheet("""
                QPushButton {
                    background: #F07900;
                    color: #000000;
                    border: none;
                    border-radius: 22px;
                    padding: 10px 24px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #B35900;
                }
            """)
            self.cancel_btn.setVisible(True)
            self.cancel_btn.setEnabled(True)
            self.status_text_label.setText("Paused — click Resume to continue")
            self.statusBar().showMessage("Scraping paused")
        else:
            self._pause_event.set()
            self.stop_btn.setText("🛑  Stop Process")
            self.stop_btn.setStyleSheet("""
                QPushButton {
                    background: #E55050;
                    color: #ffffff;
                    border: none;
                    border-radius: 22px;
                    padding: 10px 24px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #B33E3E;
                }
                QPushButton:disabled {
                    background: #d0d0d0;
                    color: #999999;
                }
            """)
            self.cancel_btn.setVisible(False)
            self.cancel_btn.setEnabled(False)
            self.status_text_label.setText("Resuming...")
            self.statusBar().showMessage("Resuming scrape")

    def _cancel_scrape(self):
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            self._pause_event.set()
            self._cancelled_by_user = True
            self.cancel_btn.setVisible(False)
            self.cancel_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("⏹  Stopped")
            self.status_text_label.setText("Cancelling...")
            self.statusBar().showMessage("Cancelling scrape...")

    def setup_styles(self):
        """Apply global styles."""
        t = THEME
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {t["bg"]};
            }}
            QStatusBar {{
                background: {t["statusbar_bg"]};
                border-top: 1px solid {t["statusbar_border"]};
                padding: 4px;
                color: {t["text_muted"]};
                font-size: 12px;
            }}
            QPushButton {{
                background: {t["primary"]};
                color: {t["button_text"]};
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {t["primary_hover"]};
            }}
            QPushButton:pressed {{
                background: {t["primary_pressed"]};
            }}
            QPushButton:disabled {{
                background: #d0d0d0;
                color: #999;
            }}
            QPushButton#secondary_btn {{
                background: {t["secondary"]};
                color: {t["button_text"]};
            }}
            QPushButton#secondary_btn:hover {{
                background: {t["secondary_hover"]};
            }}
            QPushButton#danger_btn {{
                background: {t["danger"]};
                color: {t["button_text"]};
            }}
            QPushButton#danger_btn:hover {{
                background: {t["danger_hover"]};
                color: {t["button_text"]};
            }}
            QLineEdit, QTextEdit {{
                background: {t["input_bg"]};
                border: 1px solid {t["input_border"]};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                color: {t["text"]};
            }}
            QLineEdit:focus, QTextEdit:focus {{
                border: 2px solid {t["input_focus"]};
                background: {t["input_bg"]};
            }}
            QLabel {{
                color: {t["text"]};
                background: transparent;
            }}
        """)

    def _progress_theme(self, state: str) -> Dict[str, str]:
        t = THEME
        themes = {
            "idle": {
                "text": t["text"],
                "track": t["progress_track"],
                "border": t["progress_border"],
                "fill_start": t["progress_idle"],
                "fill_end": t["progress_idle_end"],
            },
            "running": {
                "text": t["text"],
                "track": t["progress_track"],
                "border": t["progress_border"],
                "fill_start": t["progress_running"],
                "fill_end": t["progress_running_end"],
            },
            "success": {
                "text": "#14532d",
                "track": "#ecfdf5",
                "border": "#bbf7d0",
                "fill_start": t["progress_success"],
                "fill_end": t["progress_success_end"],
            },
            "error": {
                "text": "#7f1d1d",
                "track": "#fff1f2",
                "border": "#fecaca",
                "fill_start": t["progress_error"],
                "fill_end": t["progress_error_end"],
            },
        }
        return themes.get(state, themes["idle"])

    def _build_progress_bar_stylesheet(self, state: str) -> str:
        theme = self._progress_theme(state)
        self.progress_bar.setColors(
            track_color=theme["track"],
            chunk_start=theme["fill_start"],
            chunk_end=theme["fill_end"],
            text_color=theme["text"],
        )
        return """
            QProgressBar {
                font-size: 11px;
                font-weight: 500;
                font-family: "JetBrains Mono", "SF Mono", monospace;
            }
        """

    def _animate_progress_bar(self, target_value: int):
        target_value = max(0, min(100, target_value))
        if self.progress_animation:
            self.progress_animation.stop()

        self.progress_animation = QPropertyAnimation(self.progress_bar, b"value", self)
        self.progress_animation.setStartValue(self.progress_bar.value())
        self.progress_animation.setEndValue(target_value)
        self.progress_animation.setDuration(360)
        self.progress_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.progress_animation.start()

    def _summarize_error(self, error_msg: str) -> str:
        summary = (
            safe_str(error_msg).strip().splitlines()[0]
            if error_msg
            else "Unknown error"
        )
        if len(summary) > 140:
            summary = summary[:137].rstrip() + "..."
        return summary

    def _set_progress_state(
        self,
        state: str,
        *,
        current: int,
        total: int,
        animate: bool = True,
        percent: int = None,
    ):
        self.progress_current = max(0, current)
        self.progress_total = max(0, total)
        if percent is None:
            percent = 0 if total <= 0 else round((current / total) * 100)
        percent = max(0, min(100, percent))

        progress_format = (
            f"{self.progress_current}/{self.progress_total}"
            if self.progress_total
            else "0/0"
        )
        self.progress_bar.setFormat(progress_format)
        self.progress_bar.setStyleSheet(self._build_progress_bar_stylesheet(state))

        if animate:
            self._animate_progress_bar(percent)
        else:
            if self.progress_animation:
                self.progress_animation.stop()
            self.progress_bar.setValue(percent)

    def refresh_google_sync_status(self):
        configured = is_google_sync_configured(self.google_sync_settings)
        tab_name = self.google_sync_settings.sheet_tab or "RawData"
        if configured:
            self.google_sync_status_label.setText(f"Google Sync: Ready ({tab_name})")
            self.google_sync_status_label.setStyleSheet(
                "color: #15803d; font-size: 12px; font-weight: 500; padding-left: 8px;"
            )
        else:
            self.google_sync_status_label.setText("Google Sync: Setup required")
            self.google_sync_status_label.setStyleSheet(
                "color: #b45309; font-size: 12px; font-weight: 500; padding-left: 8px;"
            )

        has_results = bool(self.results)
        syncing = (
            self.google_sync_thread is not None and self.google_sync_thread.isRunning()
        )
        enabled = has_results and configured and not syncing
        self.google_sync_btn.setEnabled(enabled)
        self.google_sync_btn.setStyleSheet(f"""
            QPushButton {{
                background: {THEME["primary"]};
                color: {THEME["button_text"]};
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {THEME["primary_hover"]};
            }}
            QPushButton:disabled {{
                background: {THEME["secondary"]};
                color: {THEME["text_muted"]};
            }}
        """)
        self.google_setup_btn.setEnabled(not syncing)

    def open_google_sync_setup(self):
        dialog = GoogleSyncSetupDialog(self.google_sync_settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.google_sync_settings = load_google_sync_settings()
            self.refresh_google_sync_status()

    def show_syncing_popup(self):
        if self._syncing_popup is not None:
            self._syncing_popup.close()
        self._syncing_popup = SyncingPopup(self)
        self._syncing_popup.show_animated()

    def hide_syncing_popup(self):
        if self._syncing_popup is None:
            return

        popup = self._syncing_popup
        self._syncing_popup = None
        popup.close_animated()

    def sync_to_google_sheet(self):
        if not self.results:
            return

        self.google_sync_settings = load_google_sync_settings()
        if not is_google_sync_configured(self.google_sync_settings):
            QMessageBox.warning(
                self,
                APP_NAME,
                "Complete Google Sync Setup before sending rows to Google Sheets.",
            )
            self.open_google_sync_setup()
            return

        rows = normalize_results_for_sheet(self.results)
        if not rows:
            QMessageBox.warning(self, APP_NAME, "There are no rows to sync.")
            return

        self.google_sync_btn.setEnabled(False)
        self.google_setup_btn.setEnabled(False)
        self.statusBar().showMessage(f"Syncing {len(rows)} row(s) to Google Sheet...")
        self.show_syncing_popup()

        self.google_sync_thread = GoogleSyncThread(self.google_sync_settings, rows)
        self.google_sync_thread.finished_sync.connect(self.google_sync_finished)
        self.google_sync_thread.error_occurred.connect(self.google_sync_error)
        self.google_sync_thread.retrying.connect(self._on_sync_retrying)
        self.google_sync_thread.start()

    def _on_sync_retrying(self, attempt: int, max_attempts: int):
        if self._syncing_popup is not None:
            self._syncing_popup.set_detail(
                f"Another user is currently syncing. "
                f"Auto-retrying... (attempt {attempt} of {max_attempts})"
            )
        self.statusBar().showMessage(
            f"Another user is syncing — retrying {attempt}/{max_attempts}..."
        )

    def google_sync_finished(self, appended: int):
        thread = self.sender()
        if thread:
            thread.wait(2000)
            try:
                thread.finished_sync.disconnect(self.google_sync_finished)
                thread.error_occurred.disconnect(self.google_sync_error)
                thread.retrying.disconnect(self._on_sync_retrying)
            except Exception:
                pass
        if self.google_sync_thread is thread:
            self.google_sync_thread = None

        self.google_setup_btn.setEnabled(True)
        self.hide_syncing_popup()
        self.refresh_google_sync_status()
        self.statusBar().showMessage(
            f"Google Sync complete | {appended} row(s) appended"
        )
        toast = SyncCompleteToast(self, appended, self.google_sync_settings.sheet_tab)
        toast.exec()

    def _friendly_sync_error(self, error_msg: str) -> str:
        msg = error_msg.lower()
        if "timed out" in msg or "timeout" in msg or "connection" in msg:
            return "Timed out. Check your connection and try again."
        if "denied access" in msg or "401" in msg or "403" in msg:
            return "Access denied. Redeploy the Apps Script."
        if "busy with another user" in msg:
            return "Sheet is busy. Try again in a moment."
        if "sync cancelled" in msg:
            return "Sync cancelled."
        return self._summarize_error(error_msg)

    def google_sync_error(self, error_msg: str):
        thread = self.sender()
        if thread:
            thread.wait(2000)
            try:
                thread.finished_sync.disconnect(self.google_sync_finished)
                thread.error_occurred.disconnect(self.google_sync_error)
                thread.retrying.disconnect(self._on_sync_retrying)
            except Exception:
                pass
        if self.google_sync_thread is thread:
            self.google_sync_thread = None

        self.google_setup_btn.setEnabled(True)
        self.hide_syncing_popup()
        self.refresh_google_sync_status()
        friendly = self._friendly_sync_error(error_msg)
        self.statusBar().showMessage(f"Google Sync failed | {friendly}")
        toast = SuccessToast(self, f"Google Sync failed — {friendly}")
        toast.show_and_auto_close(5000)

    def validate_assignment_urls(
        self, urls_text: str
    ) -> Tuple[List[str], List[Tuple[int, str]]]:
        valid_urls = []
        invalid_entries = []

        for line_number, raw_line in enumerate(urls_text.splitlines(), start=1):
            candidate = raw_line.strip()
            if not candidate:
                continue

            if AssignmentScraper.parse_url(candidate):
                valid_urls.append(candidate)
                continue

            # Extract raw URLs from text (may be inside HTML href attributes)
            found_urls = re.findall(r'https://[^\s<>"\']+', candidate)
            found_urls = [u.rstrip(".,;:!?)") for u in found_urls]

            if found_urls:
                matched = False
                for url in found_urls:
                    if AssignmentScraper.parse_url(url):
                        valid_urls.append(url)
                        matched = True
                if not matched:
                    for url in found_urls:
                        invalid_entries.append((line_number, url))
            else:
                invalid_entries.append((line_number, candidate))

        return valid_urls, invalid_entries

    def format_invalid_link_message(
        self, invalid_entries: List[Tuple[int, str]]
    ) -> str:
        preview_limit = 8
        preview_lines = [
            f"Line {line_number}: {url}"
            for line_number, url in invalid_entries[:preview_limit]
        ]
        remaining = len(invalid_entries) - preview_limit
        if remaining > 0:
            preview_lines.append(f"...and {remaining} more invalid link(s).")

        preview = "\n".join(preview_lines)
        expected = "Expected format:\nhttps://tista.app/team_coordinator/assignment_details/123456"
        return f"{preview}\n\n{expected}"

    def start_scrape(self):
        """Start scraping process."""
        logger.info("start_scrape() called")

        if self.thread is not None and self.thread.isRunning():
            QMessageBox.warning(
                self,
                APP_NAME,
                "A scrape operation is already running.\nPlease wait for it to finish.",
            )
            return

        email = self.email
        pwd = self.password

        if not self.urls:
            QMessageBox.warning(
                self, APP_NAME, "Please load URLs first using 'Input Links'"
            )
            return

        valid_urls = self.urls

        self.active_assignment_count = len(valid_urls)

        # CRITICAL FIX: Guard against double-start
        if self._scrape_processing:
            logger.warning("Scrape already in progress, ignoring duplicate start")
            QMessageBox.warning(
                self,
                APP_NAME,
                "A scrape operation is already running.\nPlease wait for it to finish.",
            )
            return

        self._cancelled_by_user = False
        self._scrape_processing = True

        self.scrape_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        self.input_links_btn.setEnabled(False)
        self.google_sync_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("🛑  Stop Process")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background: #E55050;
                color: #ffffff;
                border: none;
                border-radius: 22px;
                padding: 10px 24px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #B33E3E;
            }
            QPushButton:disabled {
                background: #d0d0d0;
                color: #999999;
            }
        """)
        self._set_progress_state(
            "running", current=0, total=self.active_assignment_count, animate=False
        )
        self.status_text_label.setText(
            f"Scraping {self.active_assignment_count} assignments..."
        )
        self.statusBar().showMessage(
            f"Scraping {self.active_assignment_count} assignment{'s' if self.active_assignment_count != 1 else ''}..."
        )

        # Pass existing session to thread for reuse (avoids redundant login)
        existing_session = None
        if (
            self.scraper
            and hasattr(self.scraper, "session")
            and self.scraper.is_authenticated
        ):
            existing_session = self.scraper.session
            logger.info("Passing existing session to scraper thread for reuse")
        else:
            logger.info("No authenticated session available, thread will perform login")

        self.thread = ScraperThread(
            valid_urls,
            email,
            pwd,
            existing_session,
            pause_event=self._pause_event,
        )

        # CRITICAL FIX: Disconnect ALL stale signals BEFORE connecting new ones
        # This prevents scrape_finished from being called multiple times
        try:
            self.thread.finished.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            self.thread.error_occurred.disconnect()
        except (TypeError, RuntimeError):
            pass
        try:
            self.thread.progress_updated.disconnect()
        except (TypeError, RuntimeError):
            pass

        self.thread.finished.connect(self.scrape_finished)
        self.thread.error_occurred.connect(self.scrape_error)
        self.thread.progress_updated.connect(self.update_progress_button)
        self.thread.start()

    def update_progress_button(self, current, total):
        self._set_progress_state("running", current=current, total=total)
        self.status_text_label.setText(f"Scraping: {current} of {total}")
        self.statusBar().showMessage(f"Scraping assignment {current} of {total}")

    def scrape_finished(self):
        # CRITICAL FIX: Idempotency guard — prevent double execution
        if not self._scrape_processing:
            logger.warning(
                "scrape_finished called but _scrape_processing is False, ignoring stale signal"
            )
            return

        finished_thread = self.sender()
        thread_error_msg = finished_thread.error_msg if finished_thread else None

        # FIX #6: Wait for thread to fully terminate BEFORE reading results
        if finished_thread:
            finished_thread.wait(5000)

        # CRITICAL FIX: Disconnect signals and clear thread reference IMMEDIATELY
        # to prevent any stale signals from re-triggering this method
        if finished_thread:
            try:
                finished_thread.finished.disconnect(self.scrape_finished)
                finished_thread.error_occurred.disconnect(self.scrape_error)
                finished_thread.progress_updated.disconnect(self.update_progress_button)
            except Exception:
                pass

        # Now safely read results from terminated thread
        thread_results = finished_thread.results if finished_thread else []
        logger.info(f"scrape_finished: thread returned {len(thread_results)} results")
        if thread_results:
            logger.info(
                f"scrape_finished: first result keys: {list(thread_results[0].keys())}"
            )
            if "error" in thread_results[0]:
                logger.warning(
                    f"scrape_finished: first result is ERROR: {thread_results[0].get('error')}"
                )

        # Clear thread reference so stale signals can't re-trigger
        if self.thread is finished_thread:
            self.thread = None

        # Reset guard flag BEFORE processing results
        self._scrape_processing = False

        if hasattr(self, "_completion_toast") and self._completion_toast is not None:
            if self._completion_toast.isVisible():
                self._completion_toast.close()
            self._completion_toast = None

        self.clear_btn.setEnabled(True)
        self.input_links_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(False)

        if thread_error_msg:
            logger.error(f"Error: {thread_error_msg}")
            self.status_text_label.setText("Scrape failed")
            self._set_progress_state(
                "error",
                current=self.progress_current,
                total=self.progress_total,
                animate=False,
            )
            QMessageBox.critical(self, APP_NAME, f"Scraping failed: {thread_error_msg}")
            return

        self.results = thread_results

        if self._cancelled_by_user:
            self._cancelled_by_user = False
            logger.info("Scrape was cancelled by user")
            urls_done = max(0, self.progress_current - 1)
            remaining = max(0, self.progress_total - urls_done)
            self.results = []
            self.status_text_label.setText("Scraping cancelled")
            self.statusBar().showMessage(
                f"Scraping cancelled — {urls_done} of {self.progress_total} completed, "
                f"{remaining} incomplete | Links are still loaded"
            )
            self._set_progress_state("idle", current=0, total=0, animate=False)
            self.copy_btn.setEnabled(False)
            self.google_sync_btn.setEnabled(False)
            self._update_start_button_state()
            self.refresh_google_sync_status()
            if self._success_toast is not None:
                self._success_toast.close()
            self._success_toast = SuccessToast(self, "Scraping cancelled")
            self._success_toast.show_and_auto_close(2000)
            return

        logger.info(f"Completed! Scraped {self.active_assignment_count} assignments")

        # Count successes and errors
        error_count = sum(1 for item in self.results if "error" in item)
        success_count = len(self.results) - error_count

        self.copy_btn.setEnabled(True)
        self.refresh_google_sync_status()

        self._set_progress_state(
            "success",
            current=self.active_assignment_count,
            total=self.active_assignment_count,
            percent=100,
        )
        status_msg = (
            f"Completed {self.active_assignment_count} assignment{'s' if self.active_assignment_count != 1 else ''} | "
            f"{success_count} succeeded, {error_count} failed | "
            f"{len(self.results)} row{'s' if len(self.results) != 1 else ''} ready"
        )
        self.status_text_label.setText("Scrape complete")
        self.statusBar().showMessage(status_msg)

        # FIX C2: Show error dialog when ALL assignments failed, otherwise show completion toast
        if success_count == 0 and error_count > 0:
            # All assignments failed — show error dialog instead of success toast
            error_urls = "\n".join(
                [
                    f"• {item.get('url', 'Unknown')}"
                    for item in self.results
                    if "error" in item
                ][:5]
            )  # Show max 5 errors
            if error_count > 5:
                error_urls += f"\n...and {error_count - 5} more"

            QMessageBox.critical(
                self,
                APP_NAME,
                f"None of the {error_count} assignment(s) could be scraped.\n\n"
                f"Errors:\n{error_urls}\n\n"
                f"Possible causes:\n"
                f"• Session expired and auto-relogin failed\n"
                f"• Invalid or inaccessible assignment URLs\n"
                f"• Network connectivity issues",
            )
        else:
            # At least some succeeded — show normal completion toast
            self._completion_toast = CompletionToast(
                self, self.active_assignment_count, len(self.results)
            )
            self._completion_toast.raise_()
            self._completion_toast.activateWindow()
            self._completion_toast.exec()

    def scrape_error(self, error_msg: str):
        # CRITICAL FIX: Idempotency guard — prevent double execution
        if not self._scrape_processing:
            logger.warning(
                "scrape_error called but _scrape_processing is False, ignoring stale signal"
            )
            return

        errored_thread = self.sender()

        if errored_thread:
            try:
                errored_thread.finished.disconnect(self.scrape_finished)
                errored_thread.error_occurred.disconnect(self.scrape_error)
                errored_thread.progress_updated.disconnect(self.update_progress_button)
            except Exception:
                pass
            errored_thread.wait(2000)
            if self.thread is errored_thread:
                self.thread = None

        # Reset guard flag
        self._scrape_processing = False

        if self._completion_toast is not None:
            if self._completion_toast.isVisible():
                self._completion_toast.close()
            self._completion_toast = None

        self.clear_btn.setEnabled(True)
        self.input_links_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setEnabled(False)
        self.refresh_google_sync_status()

        logger.error(f"Error: {error_msg}")
        self.status_text_label.setText("Scrape failed")
        self._set_progress_state(
            "error",
            current=self.progress_current,
            total=self.progress_total,
            animate=False,
        )
        self.statusBar().showMessage(
            f"Scraping failed | {self._summarize_error(error_msg)}"
        )
        QMessageBox.critical(self, APP_NAME, f"Scraping failed: {error_msg}")

    def _format_category_level(self, item: Dict[str, Any]) -> str:
        raw_level = safe_str(item.get("category_level", "")).strip()
        if not raw_level:
            return ""
        if raw_level == "-":
            return "-"

        normalized = re.sub(r"^category\s*", "", raw_level, flags=re.IGNORECASE).strip()
        return f"Category {normalized}" if normalized else ""

    def export_json(self):
        if not self.results:
            return

        fname, _ = QFileDialog.getSaveFileName(
            self, APP_NAME, "assignments.json", "JSON Files (*.json)"
        )

        if fname:
            path = self.scraper.save_json(self.results, os.path.basename(fname))
            count = len(self.results)
            QMessageBox.information(
                self,
                APP_NAME,
                f"[OK] Exported {count} records to:\n{path}\n\nFile saved successfully!",
            )

    def export_csv(self):
        if not self.results:
            return

        fname, _ = QFileDialog.getSaveFileName(
            self, APP_NAME, "assignments.csv", "CSV Files (*.csv)"
        )

        if fname:
            path = self.scraper.save_csv(self.results, os.path.basename(fname))
            count = len(self.results)
            QMessageBox.information(
                self,
                APP_NAME,
                f"[OK] Exported {count} records to:\n{path}\n\nFile saved successfully!",
            )

    def copy_to_clipboard(self, include_headers: bool = False, show_toast: bool = True):
        if not self.results:
            return

        headers = [
            "Date",
            "Auditor",
            "Week",
            "Subcontractor",
            "Order #",
            "Service Type",
            "Match",
            "Image Count",
            "SM Name",
            "Category Level",
            "Return Format",
            "Comments",
            "Notes",
        ]

        rows = []
        error_row_count = 0
        # FIX H1: Include error rows in clipboard (matching table behavior) with ERROR marker
        sorted_results = sorted(
            self.results,
            key=lambda item: (
                999 if "error" in item else sm_priority(item.get("sm_name", "")),
                item.get("url", ""),
            ),
        )
        for item in sorted_results:
            if "error" in item:
                # Include error row with ERROR marker (consistent with table display)
                error_row_count += 1
                error_url = item.get("url", "Unknown")
                error_msg = item.get("error", "Unknown error")
                row = [
                    "ERROR",
                    "",
                    "",
                    "",
                    "",
                    f"ERROR: {error_msg[:60]}{'...' if len(error_msg) > 60 else ''}",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
                rows.append("\t".join(row))
                continue

            sm_display = resolve_sm_display_name(item.get("sm_name", ""))
            row = [
                self._sanitize_clipboard_cell(item.get("date", "")),
                self._sanitize_clipboard_cell(item.get("auditor", "")),
                self._sanitize_clipboard_cell(item.get("week", "")),
                self._sanitize_clipboard_cell(
                    item.get("subcontractor", "").replace("ClippingPix", "Clipping Pix")
                ),
                self._sanitize_clipboard_cell(item.get("order_number", "")),
                self._sanitize_clipboard_cell(item.get("service_type", "")),
                "Yes",
                self._sanitize_clipboard_cell(item.get("image_count", "")),
                self._sanitize_clipboard_cell(sm_display),
                self._sanitize_clipboard_cell(self._format_category_level(item)),
                self._sanitize_clipboard_cell(item.get("return_format", "")),
                self._sanitize_clipboard_cell(item.get("comments", "")),
                self._sanitize_clipboard_cell(item.get("notes", "")),
            ]
            rows.append("\t".join(row))

        if include_headers:
            header_line = "\t".join(headers)
            clipboard_text = header_line + "\n" + "\n".join(rows)
        else:
            clipboard_text = "\n".join(rows)

        clipboard = QApplication.clipboard()
        clipboard.setText(clipboard_text)

        if show_toast:
            total_count = len(rows)
            success_count = total_count - error_row_count
            if error_row_count > 0:
                msg = f"Copied {success_count} record(s) + {error_row_count} error row(s)!"
            else:
                msg = (
                    f"Copied {success_count} record{'s' if success_count != 1 else ''}!"
                )

            if self._success_toast is not None:
                self._success_toast.close()
            self._success_toast = SuccessToast(self, msg)
            self._success_toast.show_and_auto_close(2000)

    def _sanitize_clipboard_cell(self, value: Any) -> str:
        text = safe_str(value)
        text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        text = text.replace("\t", " ")
        return re.sub(r"\s{2,}", " ", text).strip()

    def clear_all(self):
        self._pause_event.set()
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()

        if self._completion_toast is not None:
            if self._completion_toast.isVisible():
                self._completion_toast.close()
            self._completion_toast = None

        if self._success_toast is not None:
            if self._success_toast.isVisible():
                self._success_toast.close()
            self._success_toast = None

        self.urls = []
        self.results = []
        self.active_assignment_count = 0
        self.copy_btn.setEnabled(False)
        self.google_sync_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.url_status_label.setText(
            "   Click the 'Input Links' button to add order links."
        )
        self.url_status_label.setStyleSheet("font-size: 12px; color: #cccccc;")
        self._update_start_button_state()
        self.refresh_google_sync_status()
        self._set_progress_state("idle", current=0, total=0, animate=False)
        self.statusBar().showMessage("Cleared  |  Press Ctrl+Enter to start scraping")

    def logout(self):
        if self._completion_toast is not None:
            if self._completion_toast.isVisible():
                self._completion_toast.close()
            self._completion_toast = None

        if self._success_toast is not None:
            if self._success_toast.isVisible():
                self._success_toast.close()
            self._success_toast = None

        self.hide_syncing_popup()

        # FIX M4: Clear session cookies from memory before logout
        if hasattr(self.scraper, "session"):
            self.scraper.session.cookies.clear()
        self.scraper.is_authenticated = False
        logger.info("Logout: Session cookies cleared from memory")

        if SessionManager:
            SessionManager.clear_all()

        if CredentialManager:
            CredentialManager.delete()

        self.close()

        login_dlg = LoginWindow()
        if login_dlg.exec() == QDialog.DialogCode.Accepted:
            email = login_dlg.email_input.text().strip()
            password = login_dlg.password_input.text()
            new_window = MainWindow(email, password)
            new_window.show()
        else:
            sys.exit(0)

    def closeEvent(self, event):
        if self._completion_toast is not None:
            if self._completion_toast.isVisible():
                self._completion_toast.close()
            self._completion_toast = None

        self.hide_syncing_popup()

        if self.thread and self.thread.isRunning():
            self._pause_event.set()
            try:
                self.thread.finished.disconnect()
                self.thread.error_occurred.disconnect()
                self.thread.progress_updated.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.thread.requestInterruption()
            self.thread.wait(2000)

        self._scrape_processing = False

        if self.google_sync_thread and self.google_sync_thread.isRunning():
            try:
                self.google_sync_thread.finished_sync.disconnect()
                self.google_sync_thread.error_occurred.disconnect()
                self.google_sync_thread.retrying.disconnect()
            except (TypeError, RuntimeError):
                pass
            self.google_sync_thread.requestInterruption()
            self.google_sync_thread.wait(2000)

        event.accept()
