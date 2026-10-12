"""
Theme helper for Order Collector GUI.
Handles light/dark selection, Windows theme detection, and application-wide palettes.
"""
import os
from typing import Dict

try:
    import winreg
except ImportError:
    winreg = None

from PySide6.QtGui import QPalette, QColor
from gui.styles import LIGHT_COLORS, DARK_COLORS, build_theme_stylesheet

DEFAULT_THEME = "light"
SUPPORTED_THEMES = ("light", "dark")
_current_theme_name = None


def detect_windows_theme() -> str:
    """Detect Windows app theme preference from the registry."""
    if os.name != "nt" or winreg is None:
        return DEFAULT_THEME

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            0,
            winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
    except Exception:
        return DEFAULT_THEME


def resolve_theme(requested: str | None = None) -> str:
    """Resolve the current theme name from explicit request or environment."""
    if requested:
        requested = requested.lower().strip()
        if requested in SUPPORTED_THEMES:
            return requested

    env_theme = os.getenv("ORDER_COLLECTOR_THEME", "").lower().strip()
    if env_theme in SUPPORTED_THEMES:
        return env_theme

    return detect_windows_theme()


def get_theme_colors(theme_name: str | None = None) -> Dict[str, str]:
    """Return the resolved color dictionary for the active theme."""
    theme_name = resolve_theme(theme_name)
    return LIGHT_COLORS if theme_name == "light" else DARK_COLORS


def get_theme_stylesheet(theme_name: str | None = None) -> str:
    """Return the full stylesheet for the selected theme."""
    colors = get_theme_colors(theme_name)
    return build_theme_stylesheet(colors)


def build_palette(theme_name: str | None = None) -> QPalette:
    """Build a Qt palette from the selected theme colors."""
    colors = get_theme_colors(theme_name)
    palette = QPalette()

    palette.setColor(QPalette.ColorRole.Window, QColor(colors['bg_primary']))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors['text_primary']))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors['bg_primary']))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors['table_alt_bg']))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors['popup_bg']))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors['text_primary']))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors['text_primary']))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors['bg_secondary']))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors['button_text']))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ff0000"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors['primary']))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors['button_text']))
    palette.setColor(QPalette.ColorRole.Link, QColor(colors['primary']))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors['text_muted']))

    palette.setColor(QPalette.ColorRole.Shadow, QColor(colors['border']))

    # Disabled state colors
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors['button_disabled']))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors['button_disabled']))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors['button_disabled']))
    palette.setColor(QPalette.Disabled, QPalette.Base, QColor(colors['bg_secondary']))
    palette.setColor(QPalette.Disabled, QPalette.Button, QColor(colors['button_disabled_bg']))

    return palette


def apply_theme(app, theme_name: str | None = None) -> str:
    """Apply the selected theme to the Qt application."""
    global _current_theme_name
    _current_theme_name = resolve_theme(theme_name)
    app.setStyle("Fusion")
    app.setPalette(build_palette(_current_theme_name))
    app.setStyleSheet(get_theme_stylesheet(_current_theme_name))
    return _current_theme_name


def current_theme() -> str:
    """Return the currently applied theme name."""
    return _current_theme_name or resolve_theme(None)
