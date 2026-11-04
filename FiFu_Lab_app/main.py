"""
Main Entry Point for FiFu Lab Studio Desktop Application (PySide6).
Supports execution from root or inside FiFuLab directory.
"""

import sys
import os

# Ensure local libs and FiFuLab directories are in sys.path
fifulab_dir = os.path.dirname(os.path.abspath(__file__))
if fifulab_dir not in sys.path:
    sys.path.insert(0, fifulab_dir)

libs_dir = os.path.join(fifulab_dir, 'libs')
if os.path.exists(libs_dir) and libs_dir not in sys.path:
    sys.path.insert(0, libs_dir)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from models.variables import AppState
from styles.theme import get_stylesheet
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    # Establecer fuente base consistente con pointSize válido (>0)
    app_font = QFont("Segoe UI", 10)
    app.setFont(app_font)

    app_state = AppState()
    app.setStyleSheet(get_stylesheet(app_state.theme_mode))

    window = MainWindow(app_state, app)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

    
#python3 main.py