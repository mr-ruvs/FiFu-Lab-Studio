"""
Global Header Navbar & Telemetry Monitor Component for FiFu Lab Studio.
Provides unified Dongle USB serial connection, live link status indicators
for Móvil and Lanzador, real-time battery voltage & current monitor,
and global emergency stop.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QPushButton
)
from PySide6.QtCore import Qt, Slot
from models.variables import AppState, ESP32Status
from models.translations import tr
from libs.esp32_client import list_available_ports


class NavbarWidget(QFrame):
    """Header Navigation, Serial Connection Manager & Telemetry Monitor Bar."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            NavbarWidget {
                border-bottom: 2px solid #30363d;
                padding: 4px 12px;
                background-color: #161b22;
            }
        """)

        self._init_ui()
        self._populate_ports()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 6, 10, 6)
        main_layout.setSpacing(10)

        # 1. Logo / Título de la Plataforma
        logo_layout = QVBoxLayout()
        logo_layout.setSpacing(0)
        self.lbl_brand = QLabel(tr("app_title", self.app_state.language))
        self.lbl_brand.setObjectName("lbl_title")
        self.lbl_brand.setStyleSheet("font-size: 20px; font-weight: 900; letter-spacing: 1px; color: #00f0ff;")
        logo_layout.addWidget(self.lbl_brand)
        main_layout.addLayout(logo_layout)

        main_layout.addWidget(self._create_vdivider())

        # 2. Control de Conexión Serial (Dongle ESP8266 ESP-NOW)
        f_conn = QFrame()
        l_conn = QHBoxLayout(f_conn)
        l_conn.setContentsMargins(0, 0, 0, 0)
        l_conn.setSpacing(6)

        lbl_dongle = QLabel("Dongle (ESP8266):")
        lbl_dongle.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 11px;")
        l_conn.addWidget(lbl_dongle)

        self.combo_ports = QComboBox()
        self.combo_ports.setMinimumWidth(160)
        self.combo_ports.setMaximumWidth(220)
        self.combo_ports.setStyleSheet("font-size: 11px; padding: 3px 6px;")
        l_conn.addWidget(self.combo_ports)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Actualizar lista de puertos COM")
        self.btn_refresh.setFixedWidth(32)
        self.btn_refresh.setStyleSheet("background-color: #30363d; color: white; font-weight: bold; padding: 4px;")
        self.btn_refresh.clicked.connect(self._populate_ports)
        l_conn.addWidget(self.btn_refresh)

        self.btn_connect = QPushButton("Conectar Dongle")
        self.btn_connect.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold;
                border-radius: 5px; padding: 5px 12px; font-size: 11px;
            }
            QPushButton:hover { background-color: #0369a1; }
        """)
        self.btn_connect.clicked.connect(self._toggle_connection)
        l_conn.addWidget(self.btn_connect)

        main_layout.addWidget(f_conn)

        main_layout.addWidget(self._create_vdivider())

        # 3. Badges de Enlace en Tiempo Real (Móvil y Lanzador)
        f_badges = QFrame()
        l_badges = QHBoxLayout(f_badges)
        l_badges.setContentsMargins(0, 0, 0, 0)
        l_badges.setSpacing(6)

        self.lbl_link_dongle = QLabel("🔴 DONGLE: OFF")
        self.lbl_link_dongle.setStyleSheet("""
            background-color: #374151; color: #fca5a5; font-weight: bold;
            border-radius: 5px; padding: 5px 8px; font-size: 11px;
        """)
        l_badges.addWidget(self.lbl_link_dongle)

        self.lbl_link_movil = QLabel("🔴 MÓVIL: OFF")
        self.lbl_link_movil.setStyleSheet("""
            background-color: #374151; color: #fca5a5; font-weight: bold;
            border-radius: 5px; padding: 5px 8px; font-size: 11px;
        """)
        l_badges.addWidget(self.lbl_link_movil)

        self.lbl_link_lanz = QLabel("🔴 LANZADOR: OFF")
        self.lbl_link_lanz.setStyleSheet("""
            background-color: #374151; color: #fca5a5; font-weight: bold;
            border-radius: 5px; padding: 5px 8px; font-size: 11px;
        """)
        l_badges.addWidget(self.lbl_link_lanz)

        main_layout.addWidget(f_badges)

        main_layout.addStretch()

        # 4. Monitor de Batería y Energía Global (INA226 Pack 4S)
        telemetry_box = QFrame()
        telemetry_box.setStyleSheet("""
            QFrame {
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 4px 10px;
                background-color: #0d1117;
            }
        """)
        tel_layout = QHBoxLayout(telemetry_box)
        tel_layout.setContentsMargins(6, 2, 6, 2)
        tel_layout.setSpacing(12)

        self.lbl_bat_v = QLabel("🔋 --.-- V (--%)")
        self.lbl_bat_v.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; font-weight: bold; color: #10b981;")
        tel_layout.addWidget(self.lbl_bat_v)

        self.lbl_bat_i = QLabel("⚡ 0.000 A")
        self.lbl_bat_i.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; font-weight: bold; color: #38bdf8;")
        tel_layout.addWidget(self.lbl_bat_i)

        main_layout.addWidget(telemetry_box)

        # 5. Botón de Paro de Emergencia Global
        self.btn_estop = QPushButton("🛑 PARO")
        self.btn_estop.setToolTip("Paro de emergencia inmediato de todos los actuadores")
        self.btn_estop.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: 900;
                font-size: 12px; padding: 6px 14px; border-radius: 6px; border: 1px solid #ef4444;
            }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.btn_estop.clicked.connect(self._on_emergency_stop)
        main_layout.addWidget(self.btn_estop)

    def _create_vdivider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #30363d;")
        return line

    def _populate_ports(self):
        curr = self.combo_ports.currentData()
        self.combo_ports.clear()
        ports = list_available_ports()
        if ports:
            for dev, desc in ports:
                self.combo_ports.addItem(f"{dev} ({desc[:18]})", dev)
            if curr:
                idx = self.combo_ports.findData(curr)
                if idx >= 0:
                    self.combo_ports.setCurrentIndex(idx)
        else:
            self.combo_ports.addItem("Sin puertos COM", "")

    def _toggle_connection(self):
        if self.app_state.dongle_connected:
            self.app_state.client.disconnect_client()
            self.btn_connect.setText("Conectar Dongle")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7; color: white; font-weight: bold;
                    border-radius: 5px; padding: 5px 12px; font-size: 11px;
                }
                QPushButton:hover { background-color: #0369a1; }
            """)
        else:
            port = self.combo_ports.currentData()
            if not port:
                return
            self.app_state.client.set_serial_config(port, 115200)
            self.btn_connect.setText("Desconectar")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626; color: white; font-weight: bold;
                    border-radius: 5px; padding: 5px 12px; font-size: 11px;
                }
                QPushButton:hover { background-color: #b91c1c; }
            """)

    def _on_emergency_stop(self):
        self.app_state.client.send_mobile_stop()
        self.app_state.stop_motion()

    def _connect_signals(self):
        self.app_state.dongle_connection_changed.connect(self._on_dongle_changed)
        self.app_state.mobile_connection_changed.connect(self._on_mobile_changed)
        self.app_state.launcher_connection_changed.connect(self._on_launcher_changed)
        self.app_state.battery_updated.connect(self._on_battery_updated)
        self.app_state.language_changed.connect(self._retranslate_ui)

    @Slot(bool)
    def _on_dongle_changed(self, connected: bool):
        if connected:
            self.lbl_link_dongle.setText("🟢 DONGLE: ON")
            self.lbl_link_dongle.setStyleSheet("""
                background-color: #064e3b; color: #a7f3d0; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)
            self.btn_connect.setText("Desconectar")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #dc2626; color: white; font-weight: bold;
                    border-radius: 5px; padding: 5px 12px; font-size: 11px;
                }
                QPushButton:hover { background-color: #b91c1c; }
            """)
        else:
            self.lbl_link_dongle.setText("🔴 DONGLE: OFF")
            self.lbl_link_dongle.setStyleSheet("""
                background-color: #374151; color: #fca5a5; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)
            self.btn_connect.setText("Conectar Dongle")
            self.btn_connect.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7; color: white; font-weight: bold;
                    border-radius: 5px; padding: 5px 12px; font-size: 11px;
                }
                QPushButton:hover { background-color: #0369a1; }
            """)

    @Slot(bool)
    def _on_mobile_changed(self, connected: bool):
        if connected:
            self.lbl_link_movil.setText("🟢 MÓVIL: ENLAZADO")
            self.lbl_link_movil.setStyleSheet("""
                background-color: #065f46; color: #ffffff; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)
        else:
            self.lbl_link_movil.setText("🔴 MÓVIL: OFF")
            self.lbl_link_movil.setStyleSheet("""
                background-color: #374151; color: #fca5a5; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)

    @Slot(bool)
    def _on_launcher_changed(self, connected: bool):
        if connected:
            self.lbl_link_lanz.setText("🟢 LANZADOR: ENLAZADO")
            self.lbl_link_lanz.setStyleSheet("""
                background-color: #065f46; color: #ffffff; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)
        else:
            self.lbl_link_lanz.setText("🔴 LANZADOR: OFF")
            self.lbl_link_lanz.setStyleSheet("""
                background-color: #374151; color: #fca5a5; font-weight: bold;
                border-radius: 5px; padding: 5px 8px; font-size: 11px;
            """)

    @Slot(float, float, int)
    def _on_battery_updated(self, vbat: float, ibat: float, pct: int):
        # Color dinámico de batería
        if vbat >= 15.5:
            color = "#10b981"  # Verde (>75%)
        elif vbat >= 13.8:
            color = "#f59e0b"  # Ámbar
        else:
            color = "#ef4444"  # Rojo

        self.lbl_bat_v.setText(f"🔋 {vbat:.2f} V ({pct}%)")
        self.lbl_bat_v.setStyleSheet(f"font-family: Consolas, monospace; font-size: 13px; font-weight: bold; color: {color};")
        self.lbl_bat_i.setText(f"⚡ {ibat:.3f} A")

    def _retranslate_ui(self, lang: str):
        self.lbl_brand.setText(tr("app_title", lang))
