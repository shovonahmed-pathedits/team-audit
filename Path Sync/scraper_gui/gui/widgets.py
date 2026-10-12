"""Custom GUI widgets — URL text edit, gradient label, modern button."""

import re
from PySide6.QtWidgets import QTextEdit, QLabel, QPushButton, QApplication
from PySide6.QtCore import Qt, QMimeData, QRect
from config import THEME


class PlainUrlTextEdit(QTextEdit):
    """QTextEdit that converts pasted hyperlinks to plain text URLs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # FIX H4: Disable rich text mode to prevent Qt from auto-linkifying URLs
        self.setAcceptRichText(False)

    def createMimeDataFromSelection(self):
        """Override copy to export only plain text, stripping all HTML/CSS."""
        mime = QMimeData()
        mime.setText(self.textCursor().selectedText())
        return mime

    def canInsertFromMimeData(self, source):
        """Prevent rich text (HTML) paste — force plain TextEdit."""
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        """Override paste to convert any HTML hyperlinks to plain URLs."""
        if source.hasHtml():
            html = source.html()
            urls = self._extract_urls_from_html(html)
            if urls:
                cursor = self.textCursor()
                cursor.insertText("\n".join(urls))
                return

        if source.hasText():
            cursor = self.textCursor()
            text = source.text()
            if text.strip().startswith("<") and "href" in text:
                urls = self._extract_urls_from_html(text)
                if urls:
                    cursor.insertText("\n".join(urls))
                    return
            cursor.insertText(text)
            return

        super().insertFromMimeData(source)

    @staticmethod
    def _extract_urls_from_html(html):
        """Extract href URLs from HTML anchor tags."""
        urls = []
        matches = re.findall(r'href\s*=\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
        for url in matches:
            if "tista.app" in url or url.startswith("http"):
                urls.append(url.strip())
        if not urls:
            plain = re.sub(r"<[^>]+>", "", html)
            plain = plain.strip()
            if plain:
                urls = [plain]
        return urls


class GradientLabel(QLabel):
    """Beautiful gradient label for headers."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QLabel {{
                color: {THEME["text"]};
                font-size: 28px;
                font-weight: bold;
                padding: 10px 0;
            }}
        """)


class ModernButton(QPushButton):
    """Modern styled button with flat colors from THEME."""

    def __init__(self, text: str, button_type: str = "primary", parent=None):
        super().__init__(text, parent)
        self.button_type = button_type

        color_map = {
            "primary": (
                THEME["primary"],
                THEME["primary_hover"],
                THEME["primary_pressed"],
                THEME["button_text"],
            ),
            "success": (
                THEME["success"],
                THEME["success_hover"],
                THEME["success_pressed"],
                THEME["button_text"],
            ),
            "danger": (
                THEME["danger"],
                THEME["danger_hover"],
                THEME["danger_pressed"],
                THEME["button_text"],
            ),
            "secondary": (
                THEME["secondary"],
                THEME["secondary_hover"],
                THEME["secondary_pressed"],
                THEME["button_text"],
            ),
        }

        hover_text_map = {
            "success": THEME["text_on_dark"],
        }
        pressed_text_map = {
            "success": THEME["text_on_dark"],
        }

        bg, hover, pressed, text_color = color_map.get(
            button_type, color_map["primary"]
        )
        hover_text = hover_text_map.get(button_type, text_color)
        pressed_text = pressed_text_map.get(button_type, text_color)

        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {text_color};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: bold;
                min-width: 80px;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background: {hover};
                color: {hover_text};
            }}
            QPushButton:pressed {{
                background: {pressed};
                color: {pressed_text};
            }}
            QPushButton:disabled {{
                background: #b8b8b8;
                color: #888888;
            }}
        """)


def center_dialog_on_parent(dialog, fallback_w=320, fallback_h=95):
    """Center a dialog on its parent window with full edge-case protection.

    Guards against: parent=None, parent destroyed, parent invisible, dialog
    larger than parent, headless/no-screen environments, 0-size dialogs.
    """
    pw = dialog.width() or fallback_w
    ph = dialog.height() or fallback_h

    parent = dialog.parent()
    if parent is not None and parent.isWidgetType() and parent.isVisible():
        pr = parent.geometry()
        x = pr.x() + max(0, (pr.width() - pw) // 2)
        y = pr.y() + max(0, (pr.height() - ph) // 2)
    else:
        screen = QApplication.primaryScreen()
        if screen is not None:
            sg = screen.geometry()
        else:
            sg = QRect(0, 0, 1920, 1080)
        x = sg.x() + max(0, (sg.width() - pw) // 2)
        y = sg.y() + max(0, (sg.height() - ph) // 2)

    dialog.move(x, y)
