"""
Light theme styling with teal color scheme
"""

# Color palette
COLORS = {
    'primary': '#95e1d5',      # Teal
    'secondary': '#89b4fa',    # Blue
    'bg_primary': '#ffffff',   # White
    'bg_secondary': '#f8f9fa', # Light gray
    'bg_tertiary': '#e9ecef',  # Lighter gray
    'text_primary': '#000000', # Black
    'text_secondary': '#495057',
    'border': '#dee2e6',
    'accent': '#95e1d5',
}

LIGHT_THEME = f"""
/* Main Window */
QMainWindow {{
    background-color: {COLORS['bg_primary']};
}}

QDialog {{
    background-color: {COLORS['bg_primary']};
}}

/* Labels */
QLabel {{
    color: {COLORS['text_primary']};
    font-size: 13px;
}}

QLabel#TitleLabel {{
    font-size: 24px;
    font-weight: bold;
    color: #2d3436;
}}

QLabel#SubtitleLabel {{
    font-size: 12px;
    color: {COLORS['text_secondary']};
}}

/* Line Edits */
QLineEdit {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
}}

QLineEdit:focus {{
    border-color: {COLORS['primary']};
    background-color: #ffffff;
}}

/* Buttons */
QPushButton {{
    background-color: {COLORS['primary']};
    color: #000000;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: #7dd3c7;
}}

QPushButton:pressed {{
    background-color: #6bc4b9;
}}

QPushButton:disabled {{
    background-color: {COLORS['bg_tertiary']};
    color: #adb5bd;
}}

QPushButton#PrimaryButton {{
    background-color: {COLORS['primary']};
    color: #000000;
}}

QPushButton#PrimaryButton:hover {{
    background-color: #7dd3c7;
}}

QPushButton#SecondaryButton {{
    background-color: {COLORS['secondary']};
    color: #000000;
}}

QPushButton#SecondaryButton:hover {{
    background-color: #7aa8f8;
}}

QPushButton#DangerButton {{
    background-color: #ff6b6b;
    color: #000000;
}}

QPushButton#DangerButton:hover {{
    background-color: #ff5252;
}}

/* ComboBox */
QComboBox {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QComboBox:hover {{
    border-color: {COLORS['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {COLORS['primary']};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    selection-background-color: {COLORS['primary']};
    selection-color: #000000;
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
}}

/* DateEdit */
QDateEdit {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QDateEdit:hover {{
    border-color: {COLORS['primary']};
}}

QDateEdit::up-button, QDateEdit::down-button {{
    background-color: {COLORS['bg_tertiary']};
    border: none;
    border-radius: 4px;
}}

QDateEdit::up-button:hover, QDateEdit::down-button:hover {{
    background-color: {COLORS['border']};
}}

/* Table Widget */
QTableWidget {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: {COLORS['border']};
    font-size: 12px;
}}

QTableWidget::item {{
    padding: 8px;
    color: {COLORS['text_primary']};
    background-color: {COLORS['bg_primary']};
}}

QTableWidget::item:selected {{
    background-color: {COLORS['primary']};
    color: #000000;
}}

QHeaderView::section {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {COLORS['border']};
    font-weight: bold;
    font-size: 13px;
}}

QTableWidget QTableCornerButton::section {{
    background-color: {COLORS['bg_secondary']};
    border: none;
    border-bottom: 2px solid {COLORS['border']};
}}

/* ScrollBar */
QScrollBar:vertical {{
    background-color: {COLORS['bg_secondary']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {COLORS['border']};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {COLORS['text_secondary']};
}}

QScrollBar:horizontal {{
    background-color: {COLORS['bg_secondary']};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {COLORS['border']};
    border-radius: 5px;
    min-width: 30px;
}}

/* ProgressBar */
QProgressBar {{
    background-color: {COLORS['bg_tertiary']};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {COLORS['primary']};
    border-radius: 5px;
}}

/* CheckBox */
QCheckBox {{
    color: {COLORS['text_primary']};
    font-size: 13px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {COLORS['border']};
    border-radius: 4px;
    background-color: {COLORS['bg_secondary']};
}}

QCheckBox::indicator:checked {{
    background-color: {COLORS['primary']};
    border-color: {COLORS['primary']};
}}

QCheckBox::indicator:hover {{
    border-color: {COLORS['primary']};
}}

/* StatusBar */
QStatusBar {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_secondary']};
    font-size: 12px;
}}

/* GroupBox */
QGroupBox {{
    background-color: {COLORS['bg_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: {COLORS['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {COLORS['text_primary']};
}}

/* ToolTip */
QToolTip {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 5px;
}}

/* Menu Bar */
QMenuBar {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
}}

QMenuBar::item {{
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: {COLORS['bg_tertiary']};
}}

QMenu {{
    background-color: {COLORS['bg_primary']};
    color: {COLORS['text_primary']};
    border: 2px solid {COLORS['border']};
    border-radius: 8px;
}}

QMenu::item {{
    padding: 8px 20px;
}}

QMenu::item:selected {{
    background-color: {COLORS['primary']};
    color: #000000;
}}
"""

# Extended theme support
LIGHT_COLORS = {
    'primary': '#95e1d5',
    'primary_hover': '#7dd3c7',
    'primary_pressed': '#6bc4b9',
    'secondary': '#89b4fa',
    'secondary_hover': '#7aa8f8',
    'secondary_pressed': '#6b9af0',
    'danger': '#ff6b6b',
    'danger_hover': '#ff5252',
    'bg_primary': '#ffffff',
    'bg_secondary': '#f8f9fa',
    'bg_tertiary': '#e9ecef',
    'popup_bg': '#ffffff',
    'table_alt_bg': '#f8f9fa',
    'text_primary': '#000000',
    'text_secondary': '#495057',
    'text_muted': '#6c757d',
    'border': '#dee2e6',
    'button_text': '#000000',
    'button_disabled': '#adb5bd',
    'button_disabled_bg': '#dee2e6',
}

DARK_COLORS = {
    'primary': '#56c0b3',
    'primary_hover': '#4bb0a4',
    'primary_pressed': '#41998f',
    'secondary': '#5a9bf8',
    'secondary_hover': '#4f8ae6',
    'secondary_pressed': '#3f73c5',
    'danger': '#ff6b6b',
    'danger_hover': '#ff5252',
    'bg_primary': '#1e1e1e',
    'bg_secondary': '#2a2a2a',
    'bg_tertiary': '#343434',
    'popup_bg': '#272727',
    'table_alt_bg': '#252525',
    'text_primary': '#f8f9f2',
    'text_secondary': '#c0c0c0',
    'text_muted': '#7a7a7a',
    'border': '#3a3a3a',
    'button_text': '#000000',
    'button_disabled': '#7a7a7a',
    'button_disabled_bg': '#3a3a3a',
}

THEME_COLORS = {
    'light': LIGHT_COLORS,
    'dark': DARK_COLORS,
}


def build_theme_stylesheet(colors):
    """Build a stylesheet string for the specified theme colors."""
    return f"""
/* Main Window */
QMainWindow {{
    background-color: {colors['bg_primary']};
}}

QDialog {{
    background-color: {colors['popup_bg']};
}}

/* Labels */
QLabel {{
    color: {colors['text_primary']};
    font-size: 13px;
}}

QLabel#TitleLabel {{
    font-size: 24px;
    font-weight: bold;
    color: {colors['text_primary']};
}}

QLabel#SubtitleLabel {{
    font-size: 12px;
    color: {colors['text_secondary']};
}}

/* Line Edits */
QLineEdit {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
}}

QLineEdit:focus {{
    border-color: {colors['primary']};
    background-color: {colors['bg_primary']};
}}

/* Buttons */
QPushButton {{
    background-color: {colors['primary']};
    color: {colors['button_text']};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {colors['primary_hover']};
}}

QPushButton:pressed {{
    background-color: {colors['primary_pressed']};
}}

QPushButton:disabled {{
    background-color: {colors['button_disabled_bg']};
    color: {colors['button_disabled']};
}}

QPushButton#PrimaryButton {{
    background-color: {colors['primary']};
    color: {colors['button_text']};
}}

QPushButton#PrimaryButton:hover {{
    background-color: {colors['primary_hover']};
}}

QPushButton#SecondaryButton {{
    background-color: {colors['secondary']};
    color: {colors['button_text']};
}}

QPushButton#SecondaryButton:hover {{
    background-color: {colors['secondary_hover']};
}}

QPushButton#DangerButton {{
    background-color: {colors['danger']};
    color: {colors['button_text']};
}}

QPushButton#DangerButton:hover {{
    background-color: {colors['danger_hover']};
}}

/* ComboBox */
QComboBox {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QComboBox:hover {{
    border-color: {colors['primary']};
}}

QComboBox::drop-down {{
    border: none;
    width: 30px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {colors['primary']};
    margin-right: 10px;
}}

QComboBox QAbstractItemView {{
    background-color: {colors['bg_primary']};
    color: {colors['text_primary']};
    selection-background-color: {colors['primary']};
    selection-color: {colors['button_text']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
}}

/* DateEdit */
QDateEdit {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QDateEdit:hover {{
    border-color: {colors['primary']};
}}

QDateEdit::up-button, QDateEdit::down-button {{
    background-color: {colors['bg_tertiary']};
    border: none;
    border-radius: 4px;
}}

QDateEdit::up-button:hover, QDateEdit::down-button:hover {{
    background-color: {colors['border']};
}}

/* Table Widget */
QTableWidget {{
    background-color: {colors['bg_primary']};
    color: {colors['text_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
    gridline-color: {colors['border']};
    font-size: 12px;
}}

QTableWidget::item {{
    padding: 8px;
    color: {colors['text_primary']};
    background-color: {colors['bg_primary']};
}}

QTableWidget::item:selected {{
    background-color: {colors['primary']};
    color: {colors['button_text']};
}}

QTableWidget::item:alternate {{
    background-color: {colors['table_alt_bg']};
}}

QHeaderView::section {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
    padding: 10px;
    border: none;
    border-bottom: 2px solid {colors['border']};
    font-weight: bold;
    font-size: 13px;
}}

QTableWidget QTableCornerButton::section {{
    background-color: {colors['bg_secondary']};
    border: none;
    border-bottom: 2px solid {colors['border']};
}}

/* ScrollBar */
QScrollBar:vertical {{
    background-color: {colors['bg_secondary']};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {colors['border']};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {colors['text_secondary']};
}}

QScrollBar:horizontal {{
    background-color: {colors['bg_secondary']};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {colors['border']};
    border-radius: 5px;
    min-width: 30px;
}}

/* ProgressBar */
QProgressBar {{
    background-color: {colors['bg_tertiary']};
    border: none;
    border-radius: 5px;
    height: 8px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {colors['primary']};
    border-radius: 5px;
}}

/* CheckBox */
QCheckBox {{
    color: {colors['text_primary']};
    font-size: 13px;
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {colors['border']};
    border-radius: 4px;
    background-color: {colors['bg_secondary']};
}}

QCheckBox::indicator:checked {{
    background-color: {colors['primary']};
    border-color: {colors['primary']};
}}

QCheckBox::indicator:hover {{
    border-color: {colors['primary']};
}}

/* StatusBar */
QStatusBar {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_secondary']};
    font-size: 12px;
}}

/* GroupBox */
QGroupBox {{
    background-color: {colors['bg_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: bold;
    color: {colors['text_primary']};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {colors['text_primary']};
}}

/* ToolTip */
QToolTip {{
    background-color: {colors['popup_bg']};
    color: {colors['text_primary']};
    border: 1px solid {colors['border']};
    border-radius: 4px;
    padding: 5px;
}}

/* Menu Bar */
QMenuBar {{
    background-color: {colors['bg_secondary']};
    color: {colors['text_primary']};
}}

QMenuBar::item {{
    padding: 8px 12px;
}}

QMenuBar::item:selected {{
    background-color: {colors['bg_tertiary']};
}}

QMenu {{
    background-color: {colors['bg_primary']};
    color: {colors['text_primary']};
    border: 2px solid {colors['border']};
    border-radius: 8px;
}}

QMenu::item {{
    padding: 8px 20px;
}}

QMenu::item:selected {{
    background-color: {colors['primary']};
    color: {colors['button_text']};
}}
"""

DARK_THEME = build_theme_stylesheet(DARK_COLORS)
LIGHT_THEME = build_theme_stylesheet(LIGHT_COLORS)
