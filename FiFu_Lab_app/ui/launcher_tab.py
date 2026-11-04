"""
Tab 2: Módulo Lanzador for FiFu Lab Studio.
Full Spanish & English translation support, interactive hardware controls for servos
(Retracción IO9, Cañón IO10, Gatillo IO8), real-time Ballistic Chronograph (CNY70 IO6/IO7),
live shot logging table, theoretical vs measured kinematic calculations, and interactive
parabolic trajectory graph (pyqtgraph).
"""

import math
import numpy as np
import pyqtgraph as pg
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QFrame, QSlider, QDoubleSpinBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QFileDialog, QScrollArea
)
from PySide6.QtCore import Qt, Slot, QTimer

from models.variables import AppState
from models.translations import tr
from libs.esp32_client import (
    PASO_MM_POR_GRADO, ANGULO_COMP_0MM, ANGULO_COMP_MAX, MAX_COMP_MM, ANGULO_TOPE_MIN
)
from components.modals import ActionTriggerModal, ShootModal, CalibrateKModal, ProfileSaveModal


class LauncherTab(QWidget):
    """Pestaña 2: Módulo Lanzador Parabólico y Cronógrafo Balístico."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.ultimo_v0_medido = 0.0

        self._init_ui()
        self._connect_signals()
        self._update_kinematic_calculations()
        self._render_trajectory_plot()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 10, 12, 10)

        lang = self.app_state.language

        # Top Action Bar: Calibrar K, Configuración y Paro
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.btn_buzzer_test = QPushButton("🔔 Probar Buzzer")
        self.btn_buzzer_test.setStyleSheet("background-color: #7c3aed; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_buzzer_test.clicked.connect(lambda: self.app_state.client.send_launcher_buzzer())

        self.btn_reset_crono = QPushButton("🔄 Reset Cronógrafo")
        self.btn_reset_crono.setStyleSheet("background-color: #374151; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_reset_crono.clicked.connect(self._on_reset_crono)

        self.btn_calibrate = QPushButton(tr("btn_calibrate_k", lang))
        self.btn_calibrate.setStyleSheet("background-color: #1f6beb; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        self.btn_calibrate.clicked.connect(self._open_calibrate_modal)

        top_bar.addWidget(self.btn_buzzer_test)
        top_bar.addWidget(self.btn_reset_crono)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_calibrate)

        main_layout.addLayout(top_bar)

        # 1. CRONÓGRAFO BALÍSTICO (Display de Velocidad de Salida CNY70)
        lf_crono = QGroupBox("CRONÓGRAFO BALÍSTICO: VELOCIDAD DE SALIDA v₀ (CNY70: IO6 / IO7 — Separación 8 mm)")
        lf_crono.setStyleSheet("QGroupBox { font-weight: bold; color: #10b981; }")
        l_crono = QVBoxLayout(lf_crono)
        l_crono.setSpacing(8)

        f_crono_display = QHBoxLayout()

        self.lbl_v0_ms = QLabel("0.000 m/s")
        self.lbl_v0_ms.setStyleSheet("""
            background-color: #0d1117; color: #10b981; font-size: 32px; font-weight: 900;
            font-family: Consolas, monospace; padding: 6px 16px; border: 2px solid #10b981; border-radius: 8px;
        """)
        f_crono_display.addWidget(self.lbl_v0_ms)

        f_info = QVBoxLayout()
        f_info.setSpacing(3)
        self.lbl_v0_kmh = QLabel("Equivalente: 0.00 km/h | Δt de vuelo: 0 µs")
        self.lbl_v0_kmh.setStyleSheet("font-size: 13px; font-weight: bold; color: #f0f6fc;")
        self.lbl_cny_status = QLabel("Barreras Ópticas -> S1 (IO6): LIBRE | S2 (IO7): LIBRE")
        self.lbl_cny_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #fbbf24;")
        f_info.addWidget(self.lbl_v0_kmh)
        f_info.addWidget(self.lbl_cny_status)
        f_crono_display.addLayout(f_info)

        f_crono_display.addStretch()
        l_crono.addLayout(f_crono_display)

        # Tabla de disparos registrados
        self.tbl_shots = QTableWidget(0, 7)
        self.tbl_shots.setHorizontalHeaderLabels([
            "# Disparo", "Hora", "Compresión (mm)", "Ángulo Tiro (°)", "Δt (µs)", "v₀ (m/s)", "v₀ (km/h)"
        ])
        self.tbl_shots.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_shots.setFixedHeight(110)
        l_crono.addWidget(self.tbl_shots)

        main_layout.addWidget(lf_crono)

        # 2. CONTROLES DE SERVOMOTORES Y MECANISMO DE DISPARO
        f_controls = QHBoxLayout()
        f_controls.setSpacing(12)

        # --- Columna A: Retracción / Compresión del Resorte (IO9) ---
        grp_ret = QGroupBox("1. Retracción / Compresión (Servo IO9 - PWM)")
        grp_ret.setStyleSheet("QGroupBox { font-weight: bold; color: #f59e0b; }")
        l_ret = QVBoxLayout(grp_ret)
        l_ret.setSpacing(8)

        h_ret_presets = QHBoxLayout()
        btn_ret_tope = QPushButton("Tope (20°)")
        btn_ret_45 = QPushButton("0.0 mm (45°)")
        btn_ret_max = QPushButton(f"Máx {MAX_COMP_MM:.2f}mm (95°)")
        btn_ret_tope.clicked.connect(lambda: self._set_retractil_deg(20))
        btn_ret_45.clicked.connect(lambda: self._set_retractil_deg(45))
        btn_ret_max.clicked.connect(lambda: self._set_retractil_deg(95))
        h_ret_presets.addWidget(btn_ret_tope)
        h_ret_presets.addWidget(btn_ret_45)
        h_ret_presets.addWidget(btn_ret_max)
        l_ret.addLayout(h_ret_presets)

        h_comp_input = QHBoxLayout()
        h_comp_input.addWidget(QLabel("Compresión (mm):"))
        self.spn_ret_mm = QDoubleSpinBox()
        self.spn_ret_mm.setRange(0.0, MAX_COMP_MM)
        self.spn_ret_mm.setSingleStep(0.2)
        self.spn_ret_mm.setDecimals(2)
        self.spn_ret_mm.setValue(0.0)
        self.spn_ret_mm.valueChanged.connect(self._on_comp_mm_changed)
        h_comp_input.addWidget(self.spn_ret_mm)

        h_comp_input.addWidget(QLabel("Ángulo IO9:"))
        self.spn_ret_deg = QSpinBox()
        self.spn_ret_deg.setRange(int(ANGULO_TOPE_MIN), int(ANGULO_COMP_MAX))
        self.spn_ret_deg.setValue(45)
        self.spn_ret_deg.valueChanged.connect(self._on_comp_deg_changed)
        h_comp_input.addWidget(self.spn_ret_deg)
        l_ret.addLayout(h_comp_input)

        self.sld_ret = QSlider(Qt.Horizontal)
        self.sld_ret.setRange(int(ANGULO_TOPE_MIN), int(ANGULO_COMP_MAX))
        self.sld_ret.setValue(45)
        self.sld_ret.valueChanged.connect(self.spn_ret_deg.setValue)
        l_ret.addWidget(self.sld_ret)

        self.lbl_ret_status = QLabel("Posición: 45° (0.00 mm - En reposo)")
        self.lbl_ret_status.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        l_ret.addWidget(self.lbl_ret_status)

        self.btn_apply_ret = QPushButton("Aplicar Retracción (IO9)")
        self.btn_apply_ret.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px;")
        self.btn_apply_ret.clicked.connect(self._aplicar_retractil)
        l_ret.addWidget(self.btn_apply_ret)

        f_controls.addWidget(grp_ret, stretch=1)

        # --- Columna B: Ángulo de Lanzamiento (IO10) ---
        grp_can = QGroupBox("2. Ángulo de Lanzamiento (Servo IO10 - 800ms)")
        grp_can.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        l_can = QVBoxLayout(grp_can)
        l_can.setSpacing(8)

        h_can_presets = QHBoxLayout()
        btn_can_0 = QPushButton("0° Horiz")
        btn_can_45 = QPushButton("45° Alcance")
        btn_can_90 = QPushButton("90° Vert")
        btn_can_0.clicked.connect(lambda: self._set_canon_deg(0))
        btn_can_45.clicked.connect(lambda: self._set_canon_deg(45))
        btn_can_90.clicked.connect(lambda: self._set_canon_deg(90))
        h_can_presets.addWidget(btn_can_0)
        h_can_presets.addWidget(btn_can_45)
        h_can_presets.addWidget(btn_can_90)
        l_can.addLayout(h_can_presets)

        h_can_input = QHBoxLayout()
        h_can_input.addWidget(QLabel("Ángulo Tiro (°):"))
        self.spn_tiro_deg = QSpinBox()
        self.spn_tiro_deg.setRange(0, 90)
        self.spn_tiro_deg.setValue(45)
        self.spn_tiro_deg.valueChanged.connect(self._on_tiro_deg_changed)
        h_can_input.addWidget(self.spn_tiro_deg)

        self.lbl_servo_io10_val = QLabel("Servo: 135°")
        self.lbl_servo_io10_val.setStyleSheet("color: #38bdf8; font-weight: bold;")
        h_can_input.addWidget(self.lbl_servo_io10_val)

        self.lbl_io10_pwm = QLabel("IO10: CORTE LOW")
        self.lbl_io10_pwm.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: bold;")
        h_can_input.addWidget(self.lbl_io10_pwm)
        l_can.addLayout(h_can_input)

        self.sld_can = QSlider(Qt.Horizontal)
        self.sld_can.setRange(0, 90)
        self.sld_can.setValue(45)
        self.sld_can.valueChanged.connect(self.spn_tiro_deg.setValue)
        l_can.addWidget(self.sld_can)

        self.btn_apply_can = QPushButton("Aplicar Ángulo (IO10)")
        self.btn_apply_can.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px;")
        self.btn_apply_can.clicked.connect(self._aplicar_canon)
        l_can.addWidget(self.btn_apply_can)

        f_controls.addWidget(grp_can, stretch=1)

        # --- Columna C: Gatillo y Disparo (IO8) ---
        grp_gat = QGroupBox("3. Mecanismo de Gatillo (Servo IO8)")
        grp_gat.setStyleSheet("QGroupBox { font-weight: bold; color: #ef4444; }")
        l_gat = QVBoxLayout(grp_gat)
        l_gat.setSpacing(8)

        self.btn_anclar = QPushButton("🔒 ANCLAR (90°)")
        self.btn_anclar.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 8px; border-radius: 5px;")
        self.btn_anclar.clicked.connect(lambda: self.app_state.client.send_launcher_gatillo_anclar())
        l_gat.addWidget(self.btn_anclar)

        self.btn_liberar = QPushButton("🔓 LIBERAR (MANUAL)")
        self.btn_liberar.setStyleSheet("background-color: #ea580c; color: white; font-weight: bold; padding: 8px; border-radius: 5px;")
        self.btn_liberar.clicked.connect(self._disparar_manual)
        l_gat.addWidget(self.btn_liberar)

        self.btn_guardar_perfil_gatillo = QPushButton("💾 Guardar Perfil de Disparo")
        self.btn_guardar_perfil_gatillo.setStyleSheet("background-color: #1e293b; color: #ef4444; font-weight: bold; padding: 7px; border: 1px solid #ef4444; border-radius: 5px;")
        self.btn_guardar_perfil_gatillo.clicked.connect(self._guardar_perfil_gatillo)
        l_gat.addWidget(self.btn_guardar_perfil_gatillo)

        h_gat_ang = QHBoxLayout()
        h_gat_ang.addWidget(QLabel("Ángulo Disparo (°):"))
        self.spn_gat_ang = QSpinBox()
        self.spn_gat_ang.setRange(95, 145)
        self.spn_gat_ang.setValue(108)
        h_gat_ang.addWidget(self.spn_gat_ang)

        self.lbl_io8_pwm = QLabel("IO8: CORTE LOW")
        self.lbl_io8_pwm.setStyleSheet("color: #8b949e; font-size: 10px; font-weight: bold;")
        h_gat_ang.addWidget(self.lbl_io8_pwm)
        l_gat.addLayout(h_gat_ang)

        f_controls.addWidget(grp_gat, stretch=1)
        main_layout.addLayout(f_controls)

        # 3. RESULTADOS CINEMÁTICOS Y GRÁFICA PARABÓLICA
        f_bottom = QHBoxLayout()
        f_bottom.setSpacing(12)

        # Tabla de Cinemática Teórica vs Medida
        grp_table = QGroupBox("Resultados Cinemáticos (Teórico vs Medido CNY70)")
        l_tab = QVBoxLayout(grp_table)
        self.tbl_results = QTableWidget(6, 3)
        self.tbl_results.setHorizontalHeaderLabels(["Variable / Parámetro", "Valor Teórico", "Valor Medido CNY70"])
        self.tbl_results.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_results.setMinimumHeight(190)
        l_tab.addWidget(self.tbl_results)
        f_bottom.addWidget(grp_table, stretch=2)

        # Gráfica de Trayectoria Balística Parabólica y(x)
        grp_traj = QGroupBox("Gráfica de Trayectoria Parabólica y(x)")
        l_traj = QVBoxLayout(grp_traj)
        self.pw_traj = pg.PlotWidget()
        self.pw_traj.showGrid(x=True, y=True, alpha=0.3)
        self.pw_traj.setLabel('bottom', 'Alcance Horizontal x (m)', units='m')
        self.pw_traj.setLabel('left', 'Altura y (m)', units='m')
        self.pw_traj.setMinimumHeight(190)
        self.pw_traj.addLegend(offset=(10, 10))
        l_traj.addWidget(self.pw_traj)
        f_bottom.addWidget(grp_traj, stretch=3)

        main_layout.addLayout(f_bottom)

    # =========================================================================
    # LÓGICA DE CONTROL DE SERVOS Y GATILLO
    # =========================================================================
    def _set_retractil_deg(self, deg: int):
        self.spn_ret_deg.setValue(deg)
        self._aplicar_retractil()

    def _on_comp_mm_changed(self, mm: float):
        deg = int(round(ANGULO_COMP_0MM + (mm / PASO_MM_POR_GRADO)))
        deg = max(int(ANGULO_TOPE_MIN), min(int(ANGULO_COMP_MAX), deg))
        self.spn_ret_deg.blockSignals(True)
        self.spn_ret_deg.setValue(deg)
        self.sld_ret.setValue(deg)
        self.spn_ret_deg.blockSignals(False)
        self.lbl_ret_status.setText(f"Posición: {deg}° (Compresión activa: {mm:.2f} mm)")
        self.lbl_ret_status.setStyleSheet("color: #10b981; font-size: 11px;")
        self._update_kinematic_calculations()

    def _on_comp_deg_changed(self, deg: int):
        mm = 0.0 if deg <= ANGULO_COMP_0MM else (deg - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO
        mm = min(MAX_COMP_MM, mm)
        self.spn_ret_mm.blockSignals(True)
        self.spn_ret_mm.setValue(mm)
        self.sld_ret.setValue(deg)
        self.spn_ret_mm.blockSignals(False)
        if deg < ANGULO_COMP_0MM:
            self.lbl_ret_status.setText(f"Posición: {deg}° (Tope / Calibración: 0.00 mm)")
            self.lbl_ret_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        else:
            self.lbl_ret_status.setText(f"Posición: {deg}° (Compresión activa: {mm:.2f} mm)")
            self.lbl_ret_status.setStyleSheet("color: #10b981; font-size: 11px;")
        self._update_kinematic_calculations()

    def _aplicar_retractil(self):
        deg = self.spn_ret_deg.value()
        self.app_state.launcher_compression = self.spn_ret_mm.value()
        self.app_state.client.send_launcher_retractil(deg)

    def _set_canon_deg(self, tiro_deg: int):
        self.spn_tiro_deg.setValue(tiro_deg)
        self._aplicar_canon()

    def _on_tiro_deg_changed(self, tiro_deg: int):
        self.app_state.launcher_angle = float(tiro_deg)
        self.lbl_servo_io10_val.setText(f"Servo: {90 + tiro_deg}°")
        self._update_kinematic_calculations()

    def _aplicar_canon(self):
        tiro = self.spn_tiro_deg.value()
        self.app_state.client.send_launcher_canon(tiro)

    def _disparar_manual(self):
        ang = self.spn_gat_ang.value()
        self.app_state.client.send_launcher_gatillo_liberar(ang)

    def _guardar_perfil_gatillo(self):
        ang = self.spn_gat_ang.value()
        params = {"action": "liberar", "angle": ang}
        modal = ProfileSaveModal(
            app_state=self.app_state,
            motion_type="LAUNCHER",
            params=params,
            default_name="Disparo Balístico Gatillo",
            parent=self
        )
        modal.exec()

    def _on_reset_crono(self):
        self.app_state.client.send_launcher_reset_crono()
        self.lbl_v0_ms.setText("0.000 m/s")
        self.lbl_v0_kmh.setText("Equivalente: 0.00 km/h | Δt de vuelo: 0 µs")

    def _open_calibrate_modal(self):
        CalibrateKModal(self.app_state, self).exec()
        self._update_kinematic_calculations()

    # =========================================================================
    # PROCESAMIENTO DE TELEMETRÍA Y DISPAROS
    # =========================================================================
    def _connect_signals(self):
        self.app_state.launcher_telemetry_updated.connect(self._on_launcher_telemetry)
        self.app_state.shot_recorded.connect(self._on_shot_recorded)
        self.app_state.theme_changed.connect(self._on_theme_changed)

    @Slot(dict)
    def _on_launcher_telemetry(self, d: dict):
        act8 = d.get("act8", False)
        act10 = d.get("act10", False)
        cny1 = d.get("cny1", False)
        cny2 = d.get("cny2", False)
        armado = d.get("armado", False)

        self.lbl_io8_pwm.setText("IO8: PWM ACTIVO" if act8 else "IO8: CORTE LOW")
        self.lbl_io8_pwm.setStyleSheet(f"color: {'#10b981' if act8 else '#8b949e'}; font-size: 10px; font-weight: bold;")

        self.lbl_io10_pwm.setText("IO10: PWM ACTIVO" if act10 else "IO10: CORTE LOW")
        self.lbl_io10_pwm.setStyleSheet(f"color: {'#10b981' if act10 else '#8b949e'}; font-size: 10px; font-weight: bold;")

        txt_cny = f"Barreras Ópticas -> S1 (IO6): {'DETECTADO' if cny1 else 'LIBRE'} | S2 (IO7): {'DETECTADO' if cny2 else 'LIBRE'}"
        if armado:
            txt_cny += "  [⚡ MIDIENDO Δt...]"
        self.lbl_cny_status.setText(txt_cny)

    @Slot(dict)
    def _on_shot_recorded(self, shot: dict):
        comp_mm = shot.get("comp_mm", 0.0)
        if comp_mm < 1.0:
            return

        v_ms = shot.get("v_ms", 0.0)
        v_kmh = shot.get("v_kmh", 0.0)
        dt_us = shot.get("dt_us", 0)
        shot_id = shot.get("id", 0)
        hora = shot.get("hora", "")
        ang_tiro = shot.get("ang_tiro", 0)

        self.ultimo_v0_medido = v_ms
        self.lbl_v0_ms.setText(f"{v_ms:.3f} m/s")
        self.lbl_v0_kmh.setText(f"Equivalente: {v_kmh:.2f} km/h | Δt de vuelo: {dt_us} µs")

        # Insertar fila en la tabla de disparos
        row = 0
        self.tbl_shots.insertRow(row)
        for c, txt in enumerate([str(shot_id), hora, f"{comp_mm:.1f} mm", f"{ang_tiro}°", str(dt_us), f"{v_ms:.3f}", f"{v_kmh:.2f}"]):
            self.tbl_shots.setItem(row, c, QTableWidgetItem(txt))

        self._update_kinematic_calculations()

    # =========================================================================
    # CÁLCULOS CINEMÁTICOS Y TRAYECTORIA PARABÓLICA
    # =========================================================================
    def _update_kinematic_calculations(self):
        theta_deg = float(self.spn_tiro_deg.value())
        theta_rad = math.radians(theta_deg)
        x_m = float(self.spn_ret_mm.value()) / 1000.0
        m_kg = float(self.app_state.launcher_mass) / 1000.0
        k_nm = float(self.app_state.launcher_k_constant)
        g = 9.81

        # Fórmulas teóricas de energía elástica y lanzamiento
        energy_theor = 0.5 * k_nm * (x_m ** 2)
        v0_theor = math.sqrt((k_nm * (x_m ** 2)) / m_kg) if m_kg > 0 else 0.0
        vx_theor = v0_theor * math.cos(theta_rad)
        vy0_theor = v0_theor * math.sin(theta_rad)
        rmax_theor = (v0_theor ** 2 * math.sin(2 * theta_rad)) / g
        hmax_theor = (vy0_theor ** 2) / (2 * g)

        # Cálculos basados en la velocidad real medida por las barreras CNY70
        v0_meas = self.ultimo_v0_medido
        if v0_meas > 0.05:
            energy_meas = 0.5 * m_kg * (v0_meas ** 2)
            vx_meas = v0_meas * math.cos(theta_rad)
            vy0_meas = v0_meas * math.sin(theta_rad)
            rmax_meas = (v0_meas ** 2 * math.sin(2 * theta_rad)) / g
            hmax_meas = (vy0_meas ** 2) / (2 * g)
            str_e = f"{energy_meas:.4f} J"
            str_v0 = f"{v0_meas:.3f} m/s"
            str_vx = f"{vx_meas:.3f} m/s"
            str_vy0 = f"{vy0_meas:.3f} m/s"
            str_rmax = f"{rmax_meas:.2f} m"
            str_hmax = f"{hmax_meas:.2f} m"
        else:
            str_e = "--"
            str_v0 = "Pendiente de disparo"
            str_vx = "--"
            str_vy0 = "--"
            str_rmax = "--"
            str_hmax = "--"

        rows = [
            ("Energía Elástica / Cinética", f"{energy_theor:.4f} J", str_e),
            ("Velocidad Inicial v₀", f"{v0_theor:.3f} m/s", str_v0),
            ("Velocidad Horizontal v_x", f"{vx_theor:.3f} m/s", str_vx),
            ("Velocidad Vertical Inicial v_y0", f"{vy0_theor:.3f} m/s", str_vy0),
            ("Alcance Máximo x_max", f"{rmax_theor:.2f} m", str_rmax),
            ("Altura Máxima y_max", f"{hmax_theor:.2f} m", str_hmax)
        ]

        for i, (nom, teor, med) in enumerate(rows):
            self.tbl_results.setItem(i, 0, QTableWidgetItem(nom))
            self.tbl_results.setItem(i, 1, QTableWidgetItem(teor))
            self.tbl_results.setItem(i, 2, QTableWidgetItem(med))

        self._render_trajectory_plot(v0_theor, v0_meas, theta_rad, rmax_theor)

    def _render_trajectory_plot(self, v0_theor=2.5, v0_meas=0.0, theta_rad=math.pi/4, rmax_theor=0.6):
        self.pw_traj.clear()
        g = 9.81

        # Curva Teórica
        if v0_theor > 0.05 and theta_rad > 0.01:
            x_max_theor = max(0.1, (v0_theor ** 2 * math.sin(2 * theta_rad)) / g)
            x_vals = np.linspace(0, x_max_theor, 100)
            y_vals = x_vals * math.tan(theta_rad) - (g * (x_vals ** 2)) / (2 * (v0_theor ** 2) * (math.cos(theta_rad) ** 2))
            y_vals = np.maximum(0.0, y_vals)
            self.pw_traj.plot(x_vals, y_vals, pen=pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine), name="Teórica y(x)")

        # Curva Medida CNY70
        if v0_meas > 0.05 and theta_rad > 0.01:
            x_max_meas = (v0_meas ** 2 * math.sin(2 * theta_rad)) / g
            x_meas_vals = np.linspace(0, x_max_meas, 100)
            y_meas_vals = x_meas_vals * math.tan(theta_rad) - (g * (x_meas_vals ** 2)) / (2 * (v0_meas ** 2) * (math.cos(theta_rad) ** 2))
            y_meas_vals = np.maximum(0.0, y_meas_vals)
            self.pw_traj.plot(x_meas_vals, y_meas_vals, pen=pg.mkPen(color='#10b981', width=3), name="Medida Real y(x)")

    def _on_theme_changed(self, mode: str):
        bg = '#0d1117' if mode == 'dark' else '#ffffff'
        fg = '#c9d1d9' if mode == 'dark' else '#1f2328'
        self.pw_traj.setBackground(bg)
        self.pw_traj.getAxis('bottom').setPen(fg)
        self.pw_traj.getAxis('left').setPen(fg)
