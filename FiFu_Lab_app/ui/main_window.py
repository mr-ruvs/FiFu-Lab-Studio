"""
Main Application Window for FiFu Lab Studio Desktop UI.
Incorporates navigation header, status bar, and workspace tabs including Diagnostics.
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget,
    QStatusBar, QLabel
)
from PySide6.QtGui import QCloseEvent

from models.variables import AppState
from models.translations import tr
from styles.theme import get_stylesheet
from components.navbar import NavbarWidget
from ui.dashboard_tab import DashboardTab
from ui.launcher_tab import LauncherTab
from ui.mobile_tab import MobileTab, make_scrollable
from ui.tab_sensores import SensoresTab


class MainWindow(QMainWindow):
    """Main Window containing all primary module tabs for FiFuLab Studio."""

    def __init__(self, app_state: AppState, app):
        super().__init__()
        self.app_state = app_state
        self.qapp = app

        lang = self.app_state.language
        self.setWindowTitle("FiFu Lab Studio — Plataforma Unificada ESP-NOW (Móvil + Lanzador)")
        self.resize(1340, 840)
        self.setMinimumSize(1100, 700)

        self._init_ui()
        self._init_statusbar()
        self._connect_signals()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        lang = self.app_state.language

        # 1. Barra de Navegación y Conexión Global
        self.navbar = NavbarWidget(self.app_state, self)
        main_layout.addWidget(self.navbar)

        # 2. Pestañas de Trabajo
        self.tab_widget = QTabWidget()
        self.tab_widget.setContentsMargins(6, 6, 6, 6)

        # Contenido de pestañas
        self.tab_dashboard_content = DashboardTab(self.app_state, self)
        self.tab_launcher_content = LauncherTab(self.app_state, self)
        self.tab_mobile_content = MobileTab(self.app_state, self)
        self.tab_sensores_content = SensoresTab(self.app_state, self)

        self.tab_widget.addTab(make_scrollable(self.tab_dashboard_content), " 📊 " + tr("tab_dashboard", lang))
        self.tab_widget.addTab(make_scrollable(self.tab_launcher_content), " 🎯 " + tr("tab_launcher", lang))
        self.tab_widget.addTab(self.tab_mobile_content, " 🚗 " + tr("tab_mobile", lang))
        self.tab_widget.addTab(make_scrollable(self.tab_sensores_content), " ⚙️ " + tr("tab_sensores", lang))

        main_layout.addWidget(self.tab_widget)

    def _init_statusbar(self):
        statusbar = QStatusBar()
        self.setStatusBar(statusbar)

        lang = self.app_state.language
        theme_str = tr("theme_label_dark", lang) if self.app_state.theme_mode == "dark" else tr("theme_label_light", lang)
        self.lbl_state = QLabel(f"{tr('status_ready', lang)} | {theme_str}")
        self.lbl_state.setStyleSheet("color: #8b949e; font-size: 11px;")
        statusbar.addPermanentWidget(self.lbl_state)

        self.lbl_esp = QLabel("ESP-NOW Dongle Bridge (115200 Bd/s) | Telemetría: 10 Hz / Lazo 20 Hz")
        self.lbl_esp.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;")
        statusbar.addWidget(self.lbl_esp)

    def _connect_signals(self):
        self.app_state.theme_changed.connect(self._on_theme_changed)
        self.app_state.language_changed.connect(self._retranslate_ui)

    def _on_theme_changed(self, mode: str):
        qss = get_stylesheet(mode)
        self.qapp.setStyleSheet(qss)
        lang = self.app_state.language
        theme_str = tr("theme_label_dark", lang) if mode == "dark" else tr("theme_label_light", lang)
        self.lbl_state.setText(f"{tr('status_ready', lang)} | {theme_str}")

    def _retranslate_ui(self, lang: str):
        self.tab_widget.setTabText(0, " 📊 " + tr("tab_dashboard", lang))
        self.tab_widget.setTabText(1, " 🎯 " + tr("tab_launcher", lang))
        self.tab_widget.setTabText(2, " 🚗 " + tr("tab_mobile", lang))
        self.tab_widget.setTabText(3, " ⚙️ " + tr("tab_sensores", lang))

        theme_str = tr("theme_label_dark", lang) if self.app_state.theme_mode == "dark" else tr("theme_label_light", lang)
        self.lbl_state.setText(f"{tr('status_ready', lang)} | {theme_str}")

    def closeEvent(self, event: QCloseEvent):
        """Cierre seguro del hilo de comunicación serial al salir."""
        try:
            self.app_state.client.stop()
        except Exception:
            pass
        super().closeEvent(event)
