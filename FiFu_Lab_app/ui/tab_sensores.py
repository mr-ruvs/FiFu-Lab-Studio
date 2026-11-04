"""
Sensors and Hardware Diagnostics Tab for FiFuLab Studio.
Provides real-time diagnostics for:
  - Placa Perimetral Frontal (PCF8574 @ 0x20): Switches e infrarrojos CNY70
  - Encoders magnéticos AS5600 (Bus 1 Wire1 Izq | Bus 0 Wire Der)
  - Medidor de Potencia y Batería Pack 4S (INA226)
  - Control de Motores Pololu VNH5019 / Perfiles
  - Diagnóstico del Módulo Lanzador (Servos IO8, IO9, IO10, flags y cronógrafo)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QPushButton, QSlider, QFrame, QProgressBar, QCheckBox
)
from PySide6.QtCore import Qt, Slot

from models.variables import AppState
from models.translations import tr
from libs.esp32_client import RADIO_RUEDA_M, ANCHO_VIA_M, PASO_MM_POR_GRADO, ANGULO_COMP_0MM


class SensorBitCardWidget(QFrame):
    """Tarjeta visual de diagnóstico para un sensor perimetral PCF8574."""

    def __init__(self, name: str, bit_index: int, sensor_type: str = "switch", parent=None):
        super().__init__(parent)
        self.name = name
        self.bit_index = bit_index
        self.sensor_type = sensor_type  # "switch", "cny70", "touch"

        self.setFrameShape(QFrame.StyledPanel)
        self.setMinimumHeight(80)
        self._init_ui()
        self.update_state(0xFF)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        self.lbl_title = QLabel(self.name)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 11px; color: #e5e7eb;")

        self.lbl_pin = QLabel(f"PCF8574 Bit P{self.bit_index}")
        self.lbl_pin.setStyleSheet("font-size: 10px; color: #9ca3af;")

        self.lbl_status = QLabel("⚪ LIBRE")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("font-weight: bold; font-size: 11px; border-radius: 4px; padding: 2px;")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_pin)
        layout.addWidget(self.lbl_status)

    def update_state(self, perim_byte: int):
        bit_val = (perim_byte >> self.bit_index) & 1

        if self.sensor_type == "cny70":
            # CNY70 óptico: bit en 1 = suelo detectado (normal); bit en 0 = en el aire / desnivel
            if bit_val == 1:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #064e3b;
                        border: 2px solid #10b981;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("🟢 SUELO DETECTADO")
                self.lbl_status.setStyleSheet("color: #6ee7b7; font-weight: bold;")
            else:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #451a03;
                        border: 2px solid #f59e0b;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("⚠️ EN EL AIRE / DESNIVEL")
                self.lbl_status.setStyleSheet("color: #fde047; font-weight: bold;")

        elif self.sensor_type == "touch":
            # Touch: bit en 1 = contacto touch detectado; bit en 0 = libre
            if bit_val == 1:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #1e1b4b;
                        border: 2px solid #818cf8;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("🟢 CONTACTO TOUCH")
                self.lbl_status.setStyleSheet("color: #c7d2fe; font-weight: bold;")
            else:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #1f2937;
                        border: 1px solid #374151;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("⚪ LIBRE")
                self.lbl_status.setStyleSheet("color: #9ca3af;")

        else: # "switch"
            # Switch con Pull-Up: bit en 0 = presionado/impacto; bit en 1 = libre
            if bit_val == 0:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #450a0a;
                        border: 2px solid #ef4444;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("🔴 IMPACTO / CONTACTO")
                self.lbl_status.setStyleSheet("color: #fca5a5; font-weight: bold;")
            else:
                self.setStyleSheet("""
                    SensorBitCardWidget {
                        background-color: #1f2937;
                        border: 1px solid #374151;
                        border-radius: 8px;
                    }
                """)
                self.lbl_status.setText("⚪ LIBRE")
                self.lbl_status.setStyleSheet("color: #9ca3af;")


class SensoresTab(QWidget):
    """Tab UI para diagnóstico de hardware, sensores y comunicación ESP-NOW."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Columna Izquierda: Placa Perimetral + Encoders AS5600 + Batería INA226
        col_left = QVBoxLayout()
        col_left.setSpacing(10)
        col_left.addWidget(self._create_perimetral_group())
        col_left.addWidget(self._create_encoders_group())
        col_left.addWidget(self._create_battery_group())
        content_layout.addLayout(col_left, stretch=3)

        # Columna Derecha: Control Directo de Tracción + Diagnóstico Lanzador
        col_right = QVBoxLayout()
        col_right.setSpacing(10)
        col_right.addWidget(self._create_traction_control_group())
        col_right.addWidget(self._create_launcher_diagnostic_group())
        content_layout.addLayout(col_right, stretch=2)

        main_layout.addLayout(content_layout)

    # 1. Placa Perimetral Frontal (PCF8574 @ 0x20)
    def _create_perimetral_group(self) -> QGroupBox:
        grp = QGroupBox("PLACA PERIMETRAL FRONTAL (PCF8574 @ 0x20 — CNY70 Y SWITCHES)")
        grp.setStyleSheet("QGroupBox { font-weight: bold; color: #fde047; }")
        l = QVBoxLayout(grp)
        l.setSpacing(8)

        grid = QGridLayout()
        grid.setSpacing(8)

        self.perim_cards = []
        nombres = [
            ("CNY70 Frontal Izq", 0, "cny70"),
            ("CNY70 Frontal Der", 1, "cny70"),
            ("Switch Frontal Izq", 2, "switch"),
            ("Switch Frontal Der", 3, "switch"),
            ("Sensor Touch (P4)", 4, "touch")
        ]

        for i, (nom, bit, stype) in enumerate(nombres):
            card = SensorBitCardWidget(nom, bit, sensor_type=stype)
            grid.addWidget(card, 0, i)
            self.perim_cards.append(card)

        l.addLayout(grid)
        return grp

    # 2. Telemetría de Encoders AS5600
    def _create_encoders_group(self) -> QGroupBox:
        grp = QGroupBox("TELEMETRÍA DE TRACCIÓN (ENCODERS AS5600 I2C)")
        grp.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        l = QHBoxLayout(grp)
        l.setSpacing(10)

        # Rueda Izquierda (Wire1)
        b_l = QFrame()
        b_l.setStyleSheet("background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 8px;")
        l_l = QVBoxLayout(b_l)
        l_l.addWidget(QLabel("RUEDA IZQUIERDA (Bus 1 Wire1)"))
        self.lbl_diag_rpm_l = QLabel("0.0 RPM")
        self.lbl_diag_rpm_l.setStyleSheet("font-size: 26px; font-weight: bold; color: #10b981; font-family: monospace;")
        self.lbl_diag_sp_l = QLabel("Consigna: 0.0 RPM | v: 0.00 m/s")
        self.lbl_diag_sp_l.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: bold;")
        l_l.addWidget(self.lbl_diag_rpm_l)
        l_l.addWidget(self.lbl_diag_sp_l)
        l.addWidget(b_l)

        # Rueda Derecha (Wire)
        b_r = QFrame()
        b_r.setStyleSheet("background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 8px;")
        l_r = QVBoxLayout(b_r)
        l_r.addWidget(QLabel("RUEDA DERECHA (Bus 0 Wire)"))
        self.lbl_diag_rpm_r = QLabel("0.0 RPM")
        self.lbl_diag_rpm_r.setStyleSheet("font-size: 26px; font-weight: bold; color: #10b981; font-family: monospace;")
        self.lbl_diag_sp_r = QLabel("Consigna: 0.0 RPM | v: 0.00 m/s")
        self.lbl_diag_sp_r.setStyleSheet("color: #9ca3af; font-size: 11px; font-weight: bold;")
        l_r.addWidget(self.lbl_diag_rpm_r)
        l_r.addWidget(self.lbl_diag_sp_r)
        l.addWidget(b_r)

        return grp

    # 3. Monitor de Batería INA226
    def _create_battery_group(self) -> QGroupBox:
        grp = QGroupBox("MONITOR DE BATERÍA Y ALIMENTACIÓN (INA226 PACK 4S)")
        grp.setStyleSheet("QGroupBox { font-weight: bold; color: #10b981; }")
        l = QVBoxLayout(grp)
        l.setSpacing(6)

        row_vals = QHBoxLayout()
        self.lbl_diag_vbat = QLabel("🔋 0.00 V")
        self.lbl_diag_vbat.setStyleSheet("font-size: 24px; font-weight: bold; color: #10b981; font-family: monospace;")

        self.lbl_diag_ibat = QLabel("⚡ 0.000 A")
        self.lbl_diag_ibat.setStyleSheet("font-size: 24px; font-weight: bold; color: #38bdf8; font-family: monospace;")

        row_vals.addWidget(self.lbl_diag_vbat)
        row_vals.addSpacing(20)
        row_vals.addWidget(self.lbl_diag_ibat)
        row_vals.addStretch()
        l.addLayout(row_vals)

        self.bar_diag_bat = QProgressBar()
        self.bar_diag_bat.setRange(0, 100)
        self.bar_diag_bat.setValue(0)
        self.bar_diag_bat.setTextVisible(True)
        self.bar_diag_bat.setFixedHeight(18)
        self.bar_diag_bat.setStyleSheet("""
            QProgressBar {
                background-color: #1f2937; border: 1px solid #374151; border-radius: 9px; text-align: center; font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:0.4 #f59e0b, stop:0.8 #10b981);
                border-radius: 8px;
            }
        """)
        l.addWidget(self.bar_diag_bat)

        return grp

    # 4. Control Directo de Tracción
    def _create_traction_control_group(self) -> QGroupBox:
        grp = QGroupBox("CONTROL DIRECTO DE TRACCIÓN (PRUEBA EN RPM)")
        grp.setStyleSheet("QGroupBox { font-weight: bold; color: #f59e0b; }")
        l = QVBoxLayout(grp)
        l.setSpacing(8)

        # Slider RPM Izquierda
        l.addWidget(QLabel("Consigna RPM Izquierda:"))
        self.sld_rpm_l = QSlider(Qt.Horizontal)
        self.sld_rpm_l.setRange(-250, 250)
        self.sld_rpm_l.setValue(0)
        self.lbl_val_sld_l = QLabel("0 RPM")
        self.lbl_val_sld_l.setStyleSheet("font-weight: bold; color: #38bdf8;")
        h_sl = QHBoxLayout()
        h_sl.addWidget(self.sld_rpm_l)
        h_sl.addWidget(self.lbl_val_sld_l)
        l.addLayout(h_sl)
        self.sld_rpm_l.valueChanged.connect(lambda v: self.lbl_val_sld_l.setText(f"{v} RPM"))

        # Slider RPM Derecha
        l.addWidget(QLabel("Consigna RPM Derecha:"))
        self.sld_rpm_r = QSlider(Qt.Horizontal)
        self.sld_rpm_r.setRange(-250, 250)
        self.sld_rpm_r.setValue(0)
        self.lbl_val_sld_r = QLabel("0 RPM")
        self.lbl_val_sld_r.setStyleSheet("font-weight: bold; color: #38bdf8;")
        h_sr = QHBoxLayout()
        h_sr.addWidget(self.sld_rpm_r)
        h_sr.addWidget(self.lbl_val_sld_r)
        l.addLayout(h_sr)
        self.sld_rpm_r.valueChanged.connect(lambda v: self.lbl_val_sld_r.setText(f"{v} RPM"))

        h_btns = QHBoxLayout()
        self.btn_send_rpm = QPushButton("Aplicar RPM Directas")
        self.btn_send_rpm.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px;")
        self.btn_send_rpm.clicked.connect(self._aplicar_rpm_directas)

        self.btn_stop_rpm = QPushButton("🛑 Parar Motores")
        self.btn_stop_rpm.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; padding: 6px;")
        self.btn_stop_rpm.clicked.connect(self._parar_motores)

        h_btns.addWidget(self.btn_send_rpm)
        h_btns.addWidget(self.btn_stop_rpm)
        l.addLayout(h_btns)

        return grp

    # 5. Diagnóstico del Módulo Lanzador
    def _create_launcher_diagnostic_group(self) -> QGroupBox:
        grp = QGroupBox("DIAGNÓSTICO MÓDULO LANZADOR (ESP32-S3 ID 2)")
        grp.setStyleSheet("QGroupBox { font-weight: bold; color: #f97316; }")
        l = QVBoxLayout(grp)
        l.setSpacing(6)

        self.lbl_diag_servos = QLabel("Servos -> Gatillo (IO8): 90° | Retráctil (IO9): 45° (0.0mm) | Cañón (IO10): 90° (0°)")
        self.lbl_diag_servos.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: bold;")
        l.addWidget(self.lbl_diag_servos)

        self.lbl_diag_flags = QLabel("Flags -> act8: 0 | act10: 0 | CNY1: 0 | CNY2: 0 | Armado: 0")
        self.lbl_diag_flags.setStyleSheet("color: #a1a1aa; font-size: 11px; font-family: monospace;")
        l.addWidget(self.lbl_diag_flags)

        self.lbl_diag_shot = QLabel("Último Disparo -> #: 0 | Δt: 0 µs | v₀: 0.000 m/s")
        self.lbl_diag_shot.setStyleSheet("color: #10b981; font-size: 12px; font-weight: bold; font-family: monospace;")
        l.addWidget(self.lbl_diag_shot)

        h_btns = QHBoxLayout()
        btn_buzz = QPushButton("🔔 Sonar Buzzer")
        btn_buzz.clicked.connect(lambda: self.app_state.client.send_launcher_buzzer())
        btn_shoot_test = QPushButton("🚀 Disparo de Prueba")
        btn_shoot_test.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold;")
        btn_shoot_test.clicked.connect(lambda: self.app_state.client.send_launcher_disparo_auto(108))
        h_btns.addWidget(btn_buzz)
        h_btns.addWidget(btn_shoot_test)
        l.addLayout(h_btns)

        return grp

    def _aplicar_rpm_directas(self):
        rpm_l = float(self.sld_rpm_l.value())
        rpm_r = float(self.sld_rpm_r.value())
        self.app_state.client.send_mobile_rpm(rpm_l, rpm_r, dur=2.0)

    def _parar_motores(self):
        self.sld_rpm_l.setValue(0)
        self.sld_rpm_r.setValue(0)
        self.app_state.client.send_mobile_stop()

    def _connect_signals(self):
        self.app_state.mobile_telemetry_updated.connect(self._on_mobile_telemetry)
        self.app_state.launcher_telemetry_updated.connect(self._on_launcher_telemetry)
        self.app_state.battery_updated.connect(self._on_battery_updated)

    @Slot(dict)
    def _on_mobile_telemetry(self, d: dict):
        perim = d.get("perim", 0xFF)
        for card in self.perim_cards:
            card.update_state(perim)

        rpm_l = d.get("rpm_l", 0.0)
        rpm_r = d.get("rpm_r", 0.0)
        sp_l = d.get("sp_l", 0.0)
        sp_r = d.get("sp_r", 0.0)
        v_l = d.get("v_l", 0.0)
        v_r = d.get("v_r", 0.0)

        self.lbl_diag_rpm_l.setText(f"{rpm_l:5.1f} RPM")
        self.lbl_diag_sp_l.setText(f"Consigna: {sp_l:5.1f} RPM | v: {v_l:4.2f} m/s")

        self.lbl_diag_rpm_r.setText(f"{rpm_r:5.1f} RPM")
        self.lbl_diag_sp_r.setText(f"Consigna: {sp_r:5.1f} RPM | v: {v_r:4.2f} m/s")

    @Slot(dict)
    def _on_launcher_telemetry(self, d: dict):
        gat = d.get("gat", 90)
        ret = d.get("ret", 45)
        can = d.get("can", 90)
        comp_mm = d.get("comp_mm", 0.0)
        tiro_deg = d.get("tiro_deg", 0)

        self.lbl_diag_servos.setText(f"Servos -> Gatillo (IO8): {gat}° | Retráctil (IO9): {ret}° ({comp_mm:.1f}mm) | Cañón (IO10): {can}° ({tiro_deg}°)")

        flags = d.get("flags", 0)
        act8 = 1 if d.get("act8", False) else 0
        act10 = 1 if d.get("act10", False) else 0
        cny1 = 1 if d.get("cny1", False) else 0
        cny2 = 1 if d.get("cny2", False) else 0
        arm = 1 if d.get("armado", False) else 0
        self.lbl_diag_flags.setText(f"Flags (0x{flags:02X}) -> act8:{act8} | act10:{act10} | CNY1:{cny1} | CNY2:{cny2} | Armado:{arm}")

        shot_id = d.get("shot_id", 0)
        dt_us = d.get("dt_us", 0)
        v_ms = d.get("v_ms", 0.0)
        self.lbl_diag_shot.setText(f"Último Disparo -> #: {shot_id} | Δt: {dt_us} µs | v₀: {v_ms:.3f} m/s")

    @Slot(float, float, int)
    def _on_battery_updated(self, vbat: float, ibat: float, pct: int):
        self.lbl_diag_vbat.setText(f"🔋 {vbat:.2f} V ({pct}%)")
        self.lbl_diag_ibat.setText(f"⚡ {ibat:.3f} A")
        self.bar_diag_bat.setValue(pct)
