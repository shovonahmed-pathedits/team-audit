"""Google Sheets sync setup wizard."""

import secrets
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
)

from config import APP_NAME, THEME
from config.google_sync import (
    APP_SCRIPT_PROJECT_NAME,
    DEFAULT_SHEET_TAB,
    GoogleSyncSettings,
    extract_spreadsheet_id,
    save_google_sync_settings,
    validate_settings,
)
from google_sheets_sync import post_to_apps_script
from logger import logger


APPS_SCRIPT_TEMPLATE = r"""const EXPECTED_TOKEN = "REPLACE_WITH_YOUR_SECRET_TOKEN";

/* ---- Cell-targeted layout config (hardcoded — edit here if columns change) ---- */
const COLUMN_LAYOUT = {
  "A": "Date", "B": "Auditor", "C": "Week", "D": "Subcontractor",
  "E": "Order #", "F": "Service Type", "G": "Match", "H": "Image Count",
  "Y": "SM Name", "AA": "Category Level", "AB": "Category Level",
  "AF": "Return Format", "AG": "Comments", "AH": "Notes"
};
const STATIC_VALUES = {"AC": "Correct"};
/* ---------------------------------------------------------------------------- */

function doPost(e) {
  try {
    const payload = JSON.parse((e.postData && e.postData.contents) || "{}");

    if (!payload.token || payload.token !== EXPECTED_TOKEN) {
      return jsonResponse({ ok: false, appended: 0, message: "Unauthorized token" });
    }

    const spreadsheetId = String(payload.spreadsheetId || "").trim();
    const sheetTab = String(payload.sheetTab || "RawData").trim();
    const rows = Array.isArray(payload.rows) ? payload.rows : [];

    if (!spreadsheetId) {
      return jsonResponse({ ok: false, appended: 0, message: "Missing spreadsheetId" });
    }

    const ss = SpreadsheetApp.openById(spreadsheetId);
    let sh = ss.getSheetByName(sheetTab);
    if (!sh) {
      sh = ss.insertSheet(sheetTab);
    }

    const hasCustomLayout = Object.keys(COLUMN_LAYOUT).length > 0;

    /* ---- Legacy contiguous append path (backward compatible) ---- */
    if (!hasCustomLayout) {
      const headers = [
        "Date", "Auditor", "Week", "Subcontractor", "Order #", "Service Type",
        "Match", "Image Count", "SM Name", "Category Level", "Return Format",
        "Comments", "Notes", "Synced At"
      ];

      if (sh.getLastRow() === 0) {
        sh.getRange(1, 1, 1, headers.length).setValues([headers]);
      }

      if (payload.test === true) {
        return jsonResponse({
          ok: true,
          appended: 0,
          message: "Connection ready for " + ss.getName() + " / " + sheetTab
        });
      }

      var lock = LockService.getScriptLock();
      if (!lock.tryLock(0)) {
        return jsonResponse({
          ok: false,
          retryable: true,
          appended: 0,
          message: "Another user is currently syncing. Auto-retrying..."
        });
      }

      try {
        const now = Utilities.formatDate(
          new Date(),
          Session.getScriptTimeZone(),
          "yyyy-MM-dd HH:mm:ss"
        );

        const values = rows.map(function(r) {
          return [
            r["Date"] || "",
            r["Auditor"] || "",
            r["Week"] || "",
            r["Subcontractor"] || "",
            r["Order #"] || "",
            r["Service Type"] || "",
            r["Match"] || "",
            r["Image Count"] || "",
            r["SM Name"] || "",
            r["Category Level"] || "",
            r["Return Format"] || "",
            r["Comments"] || "",
            r["Notes"] || "",
            now
          ];
        });

        if (values.length > 0) {
          sh.getRange(sh.getLastRow() + 1, 1, values.length, headers.length)
            .setValues(values);
        }

        return jsonResponse({
          ok: true,
          appended: values.length,
          message: "Rows appended"
        });
      } finally {
        lock.releaseLock();
      }
    }

    /* ---- Custom cell-targeted layout path ---- */

    if (payload.test === true) {
      return jsonResponse({
        ok: true,
        appended: 0,
        message: "Connection ready for " + ss.getName() + " / " + sheetTab
      });
    }

    var lock = LockService.getScriptLock();
    if (!lock.tryLock(0)) {
      return jsonResponse({
        ok: false,
        retryable: true,
        appended: 0,
        message: "Another user is currently syncing. Auto-retrying..."
      });
    }

    try {
      const startRow = getLastDataRow_(sh) + 1;

      const colKeys = Object.keys(COLUMN_LAYOUT);
      const dynBlocks = groupContiguousCols_(colKeys);
      const numRows = rows.length;
      const now = Utilities.formatDate(
        new Date(),
        Session.getScriptTimeZone(),
        "yyyy-MM-dd HH:mm:ss"
      );

      /* Write each contiguous block of dynamic data */
      dynBlocks.forEach(function(block) {
        var blockValues = rows.map(function(r) {
          var rowArr = [];
          block.cols.forEach(function(col) {
            var field = COLUMN_LAYOUT[col];
            var val = r[field] || "";
            rowArr.push(val);
          });
          return rowArr;
        });
        if (blockValues.length > 0) {
          sh.getRange(startRow, block.start, blockValues.length, block.end - block.start + 1)
            .setValues(blockValues);
        }
      });

      /* Apply static values (e.g. AC = "Correct") for all written rows */
      var staticColKeys = Object.keys(STATIC_VALUES);
      if (staticColKeys.length > 0 && numRows > 0) {
        var staticBlocks = groupContiguousCols_(staticColKeys);
        staticBlocks.forEach(function(block) {
          var fillArr = [];
          for (var r = 0; r < numRows; r++) {
            var rowArr = [];
            block.cols.forEach(function(col) {
              rowArr.push(String(STATIC_VALUES[col]));
            });
            fillArr.push(rowArr);
          }
          sh.getRange(startRow, block.start, fillArr.length, block.end - block.start + 1)
            .setValues(fillArr);
        });
      }

      return jsonResponse({
        ok: true,
        appended: numRows,
        message: "Rows written (custom layout)"
      });
    } finally {
      lock.releaseLock();
    }
  } catch (err) {
    return jsonResponse({ ok: false, appended: 0, message: String(err) });
  }
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function colNameToIndex_(col) {
  var result = 0;
  for (var i = 0; i < col.length; i++) {
    result = result * 26 + (col.charCodeAt(i) - 64);
  }
  return result;
}

function colIndexToName_(idx) {
  var name = "";
  while (idx > 0) {
    idx--;
    name = String.fromCharCode(65 + (idx % 26)) + name;
    idx = Math.floor(idx / 26);
  }
  return name;
}

function groupContiguousCols_(cols) {
  var sorted = cols.slice().sort(function(a, b) {
    return colNameToIndex_(a) - colNameToIndex_(b);
  });
  var blocks = [];
  var cur = null;
  sorted.forEach(function(c) {
    var idx = colNameToIndex_(c);
    if (cur && idx === cur.end + 1) {
      cur.end = idx;
      cur.cols.push(c);
    } else {
      if (cur) blocks.push(cur);
      cur = { start: idx, end: idx, cols: [c] };
    }
  });
  if (cur) blocks.push(cur);
  return blocks;
}

function getLastDataRow_(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow === 0) return 0;
  var values = sheet.getRange(1, 1, lastRow, 1).getValues();
  for (var r = lastRow - 1; r >= 0; r--) {
    if (values[r][0] !== "") return r + 1;
  }
  return 0;
}"""


class GoogleSyncSetupDialog(QDialog):
    """Guided setup dialog for Google Sheets sync."""

    def __init__(self, settings: GoogleSyncSettings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 680)
        self.setModal(True)
        self.setup_ui()
        self.setup_styles()
        self.load_settings()
        self.refresh_status()

    def setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel(f"Google Sync Setup - {APP_SCRIPT_PROJECT_NAME}")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {THEME['text']};"
        )
        root.addWidget(title)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_sheet_tab(), "1. Sheet")
        self.tabs.addTab(self._build_script_tab(), "2. Apps Script")
        self.tabs.addTab(self._build_deploy_tab(), "3. Deploy & Test")
        root.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        self.copy_script_btn = QPushButton("Copy Apps Script")
        self.copy_script_btn.clicked.connect(self.copy_script)
        buttons.addWidget(self.copy_script_btn)

        buttons.addStretch()

        self.save_draft_btn = QPushButton("Save Draft")
        self.save_draft_btn.clicked.connect(self.save_draft)
        buttons.addWidget(self.save_draft_btn)

        self.test_save_btn = QPushButton("Test and Save")
        self.test_save_btn.clicked.connect(self.test_and_save)
        buttons.addWidget(self.test_save_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.reject)
        buttons.addWidget(self.close_btn)

        root.addLayout(buttons)

    def setup_styles(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {THEME["bg"]};
                color: {THEME["text"]};
                font-size: 13px;
            }}
            QLabel {{
                color: {THEME["text"]};
                font-size: 13px;
            }}
            QCheckBox {{
                color: {THEME["text"]};
                font-size: 13px;
            }}
            QGroupBox {{
                color: {THEME["text"]};
                font-size: 13px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
                font-size: 13px;
                font-weight: 600;
            }}
            QTabWidget::pane {{
                border: 1px solid {THEME["border"]};
                border-radius: 8px;
            }}
            QTabBar::tab {{
                font-size: 13px;
                font-weight: 600;
                padding: 8px 12px;
            }}
            QLineEdit, QTextEdit {{
                font-size: 13px;
                color: {THEME["text"]};
            }}
            QPushButton {{
                font-size: 13px;
                font-weight: 600;
            }}
        """)

    def _build_sheet_tab(self) -> QGroupBox:
        box = QGroupBox("Choose the spreadsheet")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignRight)

        self.sheet_link_input = QLineEdit()
        self.sheet_link_input.setPlaceholderText(
            "https://docs.google.com/spreadsheets/d/.../edit"
        )
        self.sheet_link_input.textChanged.connect(self.refresh_status)
        layout.addRow("Google Sheet Link", self.sheet_link_input)

        self.sheet_tab_input = QLineEdit(DEFAULT_SHEET_TAB)
        self.sheet_tab_input.textChanged.connect(self.refresh_status)
        layout.addRow("Sheet Tab", self.sheet_tab_input)

        self.spreadsheet_id_label = QLabel("")
        self.spreadsheet_id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addRow("Detected Sheet ID", self.spreadsheet_id_label)

        note = QLabel(
            "The app sends the selected spreadsheet ID at sync time, so the Sheet link can be changed later without changing code."
        )
        note.setWordWrap(True)
        layout.addRow("", note)
        return box

    def _build_script_tab(self) -> QGroupBox:
        box = QGroupBox("Create Apps Script project")
        layout = QVBoxLayout(box)

        steps = QLabel(
            "1. Open Extensions > Apps Script from your Google Sheet.\n"
            f"2. Rename the Apps Script project exactly to {APP_SCRIPT_PROJECT_NAME}.\n"
            "3. Paste the script below.\n"
            "4. Use Copy Apps Script after entering a token; the copied code includes your token."
        )
        steps.setWordWrap(True)
        layout.addWidget(steps)

        self.script_text = QTextEdit()
        self.script_text.setReadOnly(True)
        self.script_text.setPlainText(APPS_SCRIPT_TEMPLATE)
        self.script_text.setMinimumHeight(360)
        self.script_text.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 12px;"
        )
        layout.addWidget(self.script_text)
        return box

    def _build_deploy_tab(self) -> QGroupBox:
        box = QGroupBox("Deploy and test")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignRight)

        deploy_note = QLabel(
            "Deploy as Web App: Execute as Me, access Anyone. Use the URL shaped "
            "https://script.google.com/macros/s/.../exec. If Google gives a URL with "
            "/a/macros/your-domain/, the deployment is domain-restricted and this app cannot call it."
        )
        deploy_note.setWordWrap(True)
        layout.addRow("", deploy_note)

        self.script_url_input = QLineEdit()
        self.script_url_input.setPlaceholderText(
            "https://script.google.com/macros/s/.../exec"
        )
        self.script_url_input.textChanged.connect(self.refresh_status)
        layout.addRow("Web App URL", self.script_url_input)

        secret_row = QHBoxLayout()
        self.secret_input = QLineEdit()
        self.secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_input.setPlaceholderText("Use a long private token")
        self.secret_input.textChanged.connect(self.refresh_status)
        secret_row.addWidget(self.secret_input)

        self.generate_secret_btn = QPushButton("Generate")
        self.generate_secret_btn.clicked.connect(self.generate_secret)
        secret_row.addWidget(self.generate_secret_btn)
        layout.addRow("Secret Token", secret_row)

        self.show_secret_check = QCheckBox("Show secret token")
        self.show_secret_check.toggled.connect(self.toggle_secret)
        layout.addRow("", self.show_secret_check)

        self.test_result_label = QLabel("Connection has not been tested.")
        self.test_result_label.setWordWrap(True)
        layout.addRow("Status", self.test_result_label)
        return box

    def load_settings(self):
        self.sheet_link_input.setText(self.settings.sheet_link)
        self.sheet_tab_input.setText(self.settings.sheet_tab or DEFAULT_SHEET_TAB)
        self.script_url_input.setText(self.settings.script_url)
        self.secret_input.setText(self.settings.secret_token)

    def current_settings(self, *, validated: bool = None) -> GoogleSyncSettings:
        is_validated = self.settings.is_validated if validated is None else validated
        return GoogleSyncSettings(
            sheet_link=self.sheet_link_input.text().strip(),
            spreadsheet_id=extract_spreadsheet_id(self.sheet_link_input.text()),
            sheet_tab=(self.sheet_tab_input.text().strip() or DEFAULT_SHEET_TAB),
            script_url=self.script_url_input.text().strip(),
            secret_token=self.secret_input.text().strip(),
            is_validated=is_validated,
            last_test_at=self.settings.last_test_at,
            configured_at=self.settings.configured_at,
        )

    def refresh_status(self):
        sheet_id = extract_spreadsheet_id(self.sheet_link_input.text())
        self.spreadsheet_id_label.setText(sheet_id or "Not detected")
        settings = self.current_settings(validated=False)
        ok, msg = validate_settings(settings)
        if ok:
            self.status_label.setText(
                "Setup fields are complete. Use Test and Save to enable syncing."
            )
            self.status_label.setStyleSheet("color: #15803d; font-weight: bold;")
        else:
            self.status_label.setText(f"Setup incomplete: {msg}")
            self.status_label.setStyleSheet("color: #b45309; font-weight: bold;")

    def toggle_secret(self, checked: bool):
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.secret_input.setEchoMode(mode)

    def generate_secret(self):
        self.secret_input.setText(secrets.token_urlsafe(24))

    def copy_script(self):
        script = self.script_text.toPlainText()
        token = self.secret_input.text().strip()
        if token:
            script = script.replace("REPLACE_WITH_YOUR_SECRET_TOKEN", token)
        QApplication.clipboard().setText(script)
        QMessageBox.information(self, APP_NAME, "Apps Script template copied.")

    def save_draft(self):
        settings = self.current_settings(validated=False)
        save_google_sync_settings(settings)
        self.settings = settings
        QMessageBox.information(self, APP_NAME, "Google sync setup draft saved.")

    def test_and_save(self):
        settings = self.current_settings(validated=False)
        ok, msg = validate_settings(settings)
        if not ok:
            QMessageBox.warning(self, APP_NAME, msg)
            return

        self.test_save_btn.setEnabled(False)
        self.test_result_label.setText("Testing connection...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            data = post_to_apps_script(settings, [], test=True)
            settings.is_validated = True
            settings.last_test_at = datetime.now().isoformat(timespec="seconds")
            save_google_sync_settings(settings)
            self.settings = settings
            self.test_result_label.setText(data.get("message", "Connection ready."))
            logger.info("Google sync setup validated")
            QMessageBox.information(
                self,
                APP_NAME,
                "Connection test passed and settings were saved.",
            )
            self.accept()
        except Exception as e:
            settings.is_validated = False
            save_google_sync_settings(settings)
            self.settings = settings
            self.test_result_label.setText(str(e))
            logger.error(f"Google sync setup test failed: {e}")
            QMessageBox.critical(
                self,
                APP_NAME,
                "The app could not reach the Apps Script endpoint.\n\n"
                f"{e}\n\n"
                "Check the Web App URL, token, deployment access, and Sheet permissions.",
            )
        finally:
            QApplication.restoreOverrideCursor()
            self.test_save_btn.setEnabled(True)
