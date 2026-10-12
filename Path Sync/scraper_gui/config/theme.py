"""Theme — Centralized Color Palette."""

import platform

try:
    import winreg
except ModuleNotFoundError:
    winreg = None

LIGHT_THEME = {
    # Backgrounds
    "bg": "#f0f0f0",
    "surface": "#ffffff",
    "alt_row": "#fafafa",
    # Borders
    "border": "#e0e0e0",
    "input_border": "#d0d0d0",
    "header_border": "#e0e0e0",
    # Text
    "text": "#1a1a2e",
    "text_muted": "#555555",
    "text_on_dark": "#ffffff",
    # Button text (black for contrast on mint/teal buttons)
    "button_text": "#000000",
    # Inputs
    "input_bg": "#ffffff",
    "input_focus": "#95e1d5",
    # Table
    "table_bg": "#ffffff",
    "header_bg": "#f8f8f8",
    "gridline": "#f0f0f0",
    "selection": "#95e1d5",
    "selection_fg": "#1a1a2e",
    # Buttons — Primary (Mint)
    "primary": "#95e1d5",
    "primary_hover": "#7dd3c7",
    "primary_pressed": "#6bc4b9",
    # Buttons — Success (Green)
    "success": "#16a34a",
    "success_hover": "#15803d",
    "success_pressed": "#166534",
    # Buttons — Danger (Red)
    "danger": "#ff6b6b",
    "danger_hover": "#ff5252",
    "danger_pressed": "#e53e3e",
    # Buttons — Secondary (Gray)
    "secondary": "#e8e8e8",
    "secondary_hover": "#d8d8d8",
    "secondary_pressed": "#c8c8c8",
    # Progress Bar
    "progress_track": "#e8e8e8",
    "progress_border": "#d0d0d0",
    "progress_idle": "#b8b8b8",
    "progress_idle_end": "#949494",
    "progress_running": "#95e1d5",
    "progress_running_end": "#7dd3c7",
    "progress_success": "#16a34a",
    "progress_success_end": "#22c55e",
    "progress_error": "#ff6b6b",
    "progress_error_end": "#ff5252",
    # Toast / Popup
    "toast_border": "#95e1d5",
    "copied_bg": "#4ade80",
    # Status bar
    "statusbar_bg": "#ffffff",
    "statusbar_border": "#e0e0e0",
}

DARK_THEME = {
    # Backgrounds
    "bg": "#1e1e1e",
    "surface": "#1e1e1e",
    "alt_row": "#2a2a2a",
    # Borders
    "border": "#3a3a3a",
    "input_border": "#3a3a3a",
    "header_border": "#3a3a3a",
    # Text
    "text": "#f8f9f2",
    "text_muted": "#7a7a7a",
    "text_on_dark": "#ffffff",
    # Button text (black for contrast on mint/teal buttons)
    "button_text": "#000000",
    # Inputs
    "input_bg": "#1e1e1e",
    "input_focus": "#56c0b3",
    # Table
    "table_bg": "#1e1e1e",
    "header_bg": "#2a2a2a",
    "gridline": "#3a3a3a",
    "selection": "#4bb0a4",
    "selection_fg": "#ffffff",
    # Buttons — Primary (Mint)
    "primary": "#56c0b3",
    "primary_hover": "#4bb0a4",
    "primary_pressed": "#41998f",
    # Buttons — Success (Green)
    "success": "#22c55e",
    "success_hover": "#16a34a",
    "success_pressed": "#15803d",
    # Buttons — Danger (Red)
    "danger": "#f87171",
    "danger_hover": "#ef4444",
    "danger_pressed": "#dc2626",
    # Buttons — Secondary (Gray)
    "secondary": "#2a2a2a",
    "secondary_hover": "#343434",
    "secondary_pressed": "#3a3a3a",
    # Progress Bar
    "progress_track": "#2a2a2a",
    "progress_border": "#3a3a3a",
    "progress_idle": "#52525b",
    "progress_idle_end": "#71717a",
    "progress_running": "#56c0b3",
    "progress_running_end": "#4bb0a4",
    "progress_success": "#22c55e",
    "progress_success_end": "#4ade80",
    "progress_error": "#f87171",
    "progress_error_end": "#ef4444",
    # Toast / Popup
    "toast_border": "#56c0b3",
    "copied_bg": "#22c55e",
    # Status bar
    "statusbar_bg": "#1e1e1e",
    "statusbar_border": "#3a3a3a",
}


def _get_windows_app_theme() -> str:
    if platform.system() != "Windows" or winreg is None:
        return "light"

    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
    except OSError:
        return "light"


SYSTEM_THEME = _get_windows_app_theme()
IS_DARK_MODE = SYSTEM_THEME == "dark"
THEME = DARK_THEME if IS_DARK_MODE else LIGHT_THEME
