"""
Dark & Light Modern Themes & QSS Stylesheets for FiFu Lab Studio.
Instrumentation style with high contrast adaptation for Dark & Light modes.
"""

# Dark Palette
DARK_BG = "#0d1117"
DARK_PANEL = "#161b22"
DARK_CARD = "#1c2128"
DARK_BORDER = "#30363d"
DARK_TEXT = "#f0f6fc"
DARK_MUTED = "#8b949e"

# Light Palette - High Contrast & Sharp Readability
LIGHT_BG = "#f6f8fa"
LIGHT_PANEL = "#ffffff"
LIGHT_CARD = "#ffffff"
LIGHT_BORDER = "#d0d7de"
LIGHT_TEXT = "#1f2328"
LIGHT_MUTED = "#57606a"

ACCENT_CYAN = "#00f0ff"
ACCENT_GREEN = "#10b981"
ACCENT_BLUE = "#0969da"
ACCENT_AMBER = "#d97706"
ACCENT_RED = "#cf222e"
ACCENT_PURPLE = "#8250df"

STUDIO_QSS_DARK = f"""
QWidget {{
    background-color: {DARK_BG};
    color: {DARK_TEXT};
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}}
QMainWindow {{ background-color: {DARK_BG}; }}

QScrollBar:vertical {{ border: none; background: {DARK_PANEL}; width: 8px; margin: 0; border-radius: 4px; }}
QScrollBar::handle:vertical {{ background: {DARK_BORDER}; min-height: 20px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #58a6ff; }}

QTabWidget::pane {{ border: 1px solid {DARK_BORDER}; background-color: {DARK_PANEL}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background-color: {DARK_BG}; color: {DARK_MUTED}; padding: 10px 20px; font-weight: 600;
    border: 1px solid {DARK_BORDER}; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px;
}}
QTabBar::tab:hover {{ background-color: {DARK_CARD}; color: {DARK_TEXT}; }}
QTabBar::tab:selected {{ background-color: {DARK_PANEL}; color: {ACCENT_CYAN}; border-top: 3px solid {ACCENT_CYAN}; }}

QGroupBox {{
    background-color: {DARK_PANEL}; border: 1px solid {DARK_BORDER}; border-radius: 8px; margin-top: 24px; font-weight: bold; color: {ACCENT_CYAN};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; padding: 4px 10px; background-color: {DARK_CARD}; border: 1px solid {DARK_BORDER}; border-radius: 4px; color: {ACCENT_CYAN};
}}

QPushButton {{
    background-color: {DARK_CARD}; color: {DARK_TEXT}; border: 1px solid {DARK_BORDER}; border-radius: 6px; padding: 7px 14px; font-weight: 600; outline: none;
}}
QPushButton:hover {{ background-color: #21262d; border-color: #58a6ff; color: #ffffff; }}
QPushButton:pressed {{ background-color: #30363d; }}

QPushButton#btn_play {{ background-color: #0d3822; color: {ACCENT_GREEN}; border: 1px solid #10b981; font-weight: bold; }}
QPushButton#btn_play:hover {{ background-color: #10b981; color: #000000; }}

QPushButton#btn_stop {{ background-color: #3e1618; color: {ACCENT_RED}; border: 1px solid #ef4444; font-weight: bold; }}
QPushButton#btn_stop:hover {{ background-color: #ef4444; color: #ffffff; }}

QPushButton#btn_action {{ background-color: #24143a; color: {ACCENT_PURPLE}; border: 1px solid #a855f7; font-weight: bold; }}
QPushButton#btn_action:hover {{ background-color: #a855f7; color: #ffffff; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {DARK_CARD}; color: {DARK_TEXT}; border: 1px solid {DARK_BORDER}; border-radius: 5px; padding: 5px 8px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT_CYAN}; }}

QTableWidget {{ background-color: {DARK_PANEL}; border: 1px solid {DARK_BORDER}; gridline-color: {DARK_BORDER}; color: {DARK_TEXT}; }}
QHeaderView::section {{ background-color: {DARK_CARD}; color: {DARK_MUTED}; padding: 6px; border: 1px solid {DARK_BORDER}; font-weight: bold; }}

QDialog {{ background-color: {DARK_BG}; border: 1px solid {DARK_BORDER}; border-radius: 8px; }}

QToolTip {{
    background-color: #1f2937;
    color: #f3f4f6;
    border: 1px solid #4b5563;
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 4px;
}}

QLabel#lbl_title {{ font-size: 18px; font-weight: bold; color: {ACCENT_CYAN}; }}
QLabel#lbl_badge_green {{ background-color: #064e3b; color: {ACCENT_GREEN}; border: 1px solid {ACCENT_GREEN}; border-radius: 10px; padding: 2px 8px; font-weight: bold; font-size: 11px; }}
QLabel#lbl_badge_red {{ background-color: #450a0a; color: {ACCENT_RED}; border: 1px solid {ACCENT_RED}; border-radius: 10px; padding: 2px 8px; font-weight: bold; font-size: 11px; }}
QLabel#lbl_stopwatch {{ font-family: "Consolas", monospace; font-size: 20px; font-weight: bold; color: {ACCENT_CYAN}; background-color: {DARK_CARD}; border: 1px solid {ACCENT_CYAN}; border-radius: 6px; padding: 4px 12px; }}
"""

STUDIO_QSS_LIGHT = f"""
QWidget {{
    background-color: {LIGHT_BG};
    color: {LIGHT_TEXT};
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}}
QMainWindow {{ background-color: {LIGHT_BG}; }}

QScrollBar:vertical {{ border: none; background: {LIGHT_PANEL}; width: 8px; margin: 0; border-radius: 4px; }}
QScrollBar::handle:vertical {{ background: {LIGHT_BORDER}; min-height: 20px; border-radius: 4px; }}
QScrollBar::handle:vertical:hover {{ background: #0969da; }}

QTabWidget::pane {{ border: 1px solid {LIGHT_BORDER}; background-color: {LIGHT_PANEL}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background-color: {LIGHT_BG}; color: {LIGHT_MUTED}; padding: 10px 20px; font-weight: 600;
    border: 1px solid {LIGHT_BORDER}; border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px;
}}
QTabBar::tab:hover {{ background-color: #eaeef2; color: {LIGHT_TEXT}; }}
QTabBar::tab:selected {{ background-color: {LIGHT_PANEL}; color: {ACCENT_BLUE}; border-top: 3px solid {ACCENT_BLUE}; }}

QGroupBox {{
    background-color: {LIGHT_PANEL}; border: 1px solid {LIGHT_BORDER}; border-radius: 8px; margin-top: 24px; font-weight: bold; color: {ACCENT_BLUE};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left; padding: 4px 10px; background-color: #ffffff; border: 1px solid {LIGHT_BORDER}; border-radius: 4px; color: {ACCENT_BLUE};
}}

QPushButton {{
    background-color: #ffffff; color: {LIGHT_TEXT}; border: 1px solid {LIGHT_BORDER}; border-radius: 6px; padding: 7px 14px; font-weight: 600; outline: none;
}}
QPushButton:hover {{ background-color: #f3f4f6; border-color: #0969da; color: #0969da; }}
QPushButton:pressed {{ background-color: #d0d7de; }}

QPushButton#btn_play {{ background-color: #dafbe1; color: #1a7f37; border: 1px solid #2da44e; font-weight: bold; }}
QPushButton#btn_play:hover {{ background-color: #2da44e; color: #ffffff; }}

QPushButton#btn_stop {{ background-color: #ffebe9; color: {ACCENT_RED}; border: 1px solid #cf222e; font-weight: bold; }}
QPushButton#btn_stop:hover {{ background-color: #cf222e; color: #ffffff; }}

QPushButton#btn_action {{ background-color: #fbefff; color: {ACCENT_PURPLE}; border: 1px solid #8250df; font-weight: bold; }}
QPushButton#btn_action:hover {{ background-color: #8250df; color: #ffffff; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: #ffffff; color: {LIGHT_TEXT}; border: 1px solid {LIGHT_BORDER}; border-radius: 5px; padding: 5px 8px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT_BLUE}; }}

QTableWidget {{ background-color: {LIGHT_PANEL}; border: 1px solid {LIGHT_BORDER}; gridline-color: {LIGHT_BORDER}; color: {LIGHT_TEXT}; }}
QHeaderView::section {{ background-color: #f3f4f6; color: {LIGHT_MUTED}; padding: 6px; border: 1px solid {LIGHT_BORDER}; font-weight: bold; }}

QDialog {{ background-color: {LIGHT_BG}; border: 1px solid {LIGHT_BORDER}; border-radius: 8px; }}

QToolTip {{
    background-color: #ffffff;
    color: #1f2328;
    border: 1px solid #d0d7de;
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 4px;
}}

QLabel {{ color: {LIGHT_TEXT}; }}
QLabel#lbl_title {{ font-size: 18px; font-weight: bold; color: {ACCENT_BLUE}; }}
QLabel#lbl_badge_green {{ background-color: #dafbe1; color: #1a7f37; border: 1px solid #2da44e; border-radius: 10px; padding: 2px 8px; font-weight: bold; font-size: 11px; }}
QLabel#lbl_badge_red {{ background-color: #ffebe9; color: {ACCENT_RED}; border: 1px solid #cf222e; border-radius: 10px; padding: 2px 8px; font-weight: bold; font-size: 11px; }}
QLabel#lbl_stopwatch {{ font-family: "Consolas", monospace; font-size: 20px; font-weight: bold; color: {ACCENT_BLUE}; background-color: #ffffff; border: 1px solid {ACCENT_BLUE}; border-radius: 6px; padding: 4px 12px; }}
"""

def get_stylesheet(theme_mode: str = "dark") -> str:
    return STUDIO_QSS_DARK if theme_mode == "dark" else STUDIO_QSS_LIGHT
