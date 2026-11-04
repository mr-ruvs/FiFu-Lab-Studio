"""
Tab 3: Unidad Móvil (Cinemática) for FiFu Lab Studio.
Full Spanish & English translation support, interactive live plot views (pyqtgraph),
real-time encoder telemetry streaming (MRU, MRUV, MCU, Movimiento Libre),
region fit selection (ROI Recuadro), polynomial regression (Linear & Quadratic with R²),
real-time data acquisition table, and CSV download.
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'libs'))

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QFrame, QRadioButton, QCheckBox, QComboBox, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QTabWidget, QInputDialog, QMessageBox, QFileDialog,
    QStackedLayout, QScrollArea, QProgressBar
)
from PySide6.QtCore import Qt, Slot, QTimer
import math
import time

from models.variables import AppState
from models.translations import tr
from libs.esp32_client import ANCHO_VIA_M, RADIO_RUEDA_M, MS_TO_RPM
from components.canvas_widget import KinematicCanvasWidget
from components.modals import ActionTriggerModal, ProfileSaveModal


def make_scrollable(content_widget: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(content_widget)
    scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
    return scroll


class MobileTab(QWidget):
    """Pestaña 3: Unidad Móvil (Cinemática Experimental y Teórica)."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        self.free_motion_timer = QTimer(self)
        self.free_motion_timer.timeout.connect(self._on_free_motion_tick)
        self._free_t_arr = None
        self._free_x_arr = None
        self._free_v_arr = None
        self._free_dur = 0.0
        self._free_start_time = 0.0

        self._init_ui()
        self._connect_signals()
        self._setup_plot_styles()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        lang = self.app_state.language

        # Top Bar: Estado de Enlace, Modo del Robot y Paro de Emergencia
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.lbl_telemetry_status = QLabel("Estado: EN REPOSO (IDLE)")
        self.lbl_telemetry_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #fbbf24; background: #161b22; padding: 6px 12px; border-radius: 6px; border: 1px solid #30363d;")

        self.lbl_wheels_rpm = QLabel("Izq: 0.0 RPM (0.00 m/s) | Der: 0.0 RPM (0.00 m/s)")
        self.lbl_wheels_rpm.setStyleSheet("font-family: Consolas, monospace; font-size: 12px; font-weight: bold; color: #38bdf8; background: #161b22; padding: 6px 12px; border-radius: 6px; border: 1px solid #30363d;")

        self.prog_bar = QProgressBar()
        self.prog_bar.setRange(0, 1000)
        self.prog_bar.setValue(0)
        self.prog_bar.setTextVisible(False)
        self.prog_bar.setFixedWidth(140)
        self.prog_bar.setFixedHeight(18)
        self.prog_bar.setStyleSheet("""
            QProgressBar {
                background-color: #21262d; border: 1px solid #30363d; border-radius: 9px;
            }
            QProgressBar::chunk {
                background-color: #0284c7; border-radius: 8px;
            }
        """)

        self.btn_estop = QPushButton("🛑 PARO DE EMERGENCIA")
        self.btn_estop.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: bold; font-size: 12px;
                border: 1px solid #ef4444; border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.btn_estop.clicked.connect(self._paro_emergencia)

        top_bar.addWidget(self.lbl_telemetry_status)
        top_bar.addWidget(self.lbl_wheels_rpm)
        top_bar.addWidget(self.prog_bar)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_estop)

        main_layout.addLayout(top_bar)

        # Sub-pestañas: MRU | MRUV | MCU | MOVIMIENTO LIBRE
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setObjectName("sub_tab_widget")

        self.tab_mru_content = self._build_mru_tab()
        self.tab_mruv_content = self._build_mruv_tab()
        self.tab_mcu_content = self._build_mcu_tab()
        self.tab_free_content = self._build_free_draw_tab()

        self.sub_tabs.addTab(make_scrollable(self.tab_mru_content), tr("subtab_mru", lang))
        self.sub_tabs.addTab(make_scrollable(self.tab_mruv_content), tr("subtab_mruv", lang))
        self.sub_tabs.addTab(make_scrollable(self.tab_mcu_content), tr("subtab_mcu", lang))
        self.sub_tabs.addTab(make_scrollable(self.tab_free_content), tr("subtab_free", lang))

        main_layout.addWidget(self.sub_tabs)

    # =========================================================================
    # 1. PESTAÑA MRU: VELOCIDAD CONSTANTE
    # =========================================================================
    def _build_mru_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setSpacing(12)

        lang = self.app_state.language
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        # Parámetros MRU
        self.grp_mru = QGroupBox(tr("grp_mru_title", lang))
        l_grp = QVBoxLayout(self.grp_mru)
        l_grp.setSpacing(8)

        # 1. Selector de variable a calcular (Distancia d, Velocidad v, Tiempo t)
        h_calc = QHBoxLayout()
        self.lbl_mru_calc_var = QLabel("Variable a calcular:")
        self.lbl_mru_calc_var.setStyleSheet("font-weight: bold; color: #00f0ff;")
        self.cbo_mru_calc_var = QComboBox()
        self.cbo_mru_calc_var.addItem(f"{tr('opt_distance', lang)} (d)", "d")
        self.cbo_mru_calc_var.addItem(f"{tr('opt_velocity', lang)} (v)", "v")
        self.cbo_mru_calc_var.addItem(f"{tr('opt_time', lang)} (t)", "t")
        self.cbo_mru_calc_var.currentIndexChanged.connect(self._update_mru_calc_var_mode)
        h_calc.addWidget(self.lbl_mru_calc_var)
        h_calc.addWidget(self.cbo_mru_calc_var)
        l_grp.addLayout(h_calc)

        sep_mru = QFrame()
        sep_mru.setFrameShape(QFrame.HLine)
        sep_mru.setFrameShadow(QFrame.Sunken)
        sep_mru.setStyleSheet("color: #30363d;")
        l_grp.addWidget(sep_mru)

        # 2. Entradas numéricas: Velocidad v, Distancia d, Tiempo t
        h_v = QHBoxLayout()
        self.lbl_mru_v = QLabel("Velocidad v (m/s):")
        self.spn_mru_v = QDoubleSpinBox()
        self.spn_mru_v.setRange(0.05, 1.20)
        self.spn_mru_v.setSingleStep(0.05)
        self.spn_mru_v.setDecimals(2)
        self.spn_mru_v.setSuffix(" m/s")
        self.spn_mru_v.setValue(0.35)
        self.spn_mru_v.valueChanged.connect(self._recalc_mru_theor)
        h_v.addWidget(self.lbl_mru_v)
        h_v.addWidget(self.spn_mru_v)
        l_grp.addLayout(h_v)

        h_d = QHBoxLayout()
        self.lbl_mru_d = QLabel("Distancia d (m):")
        self.spn_mru_d = QDoubleSpinBox()
        self.spn_mru_d.setRange(0.05, 36.00)
        self.spn_mru_d.setSingleStep(0.10)
        self.spn_mru_d.setDecimals(2)
        self.spn_mru_d.setSuffix(" m")
        self.spn_mru_d.setValue(1.40)
        self.spn_mru_d.valueChanged.connect(self._recalc_mru_theor)
        h_d.addWidget(self.lbl_mru_d)
        h_d.addWidget(self.spn_mru_d)
        l_grp.addLayout(h_d)

        h_t = QHBoxLayout()
        self.lbl_mru_t = QLabel("Tiempo t (s):")
        self.spn_mru_t = QDoubleSpinBox()
        self.spn_mru_t.setRange(0.5, 30.0)
        self.spn_mru_t.setSingleStep(0.5)
        self.spn_mru_t.setDecimals(1)
        self.spn_mru_t.setSuffix(" s")
        self.spn_mru_t.setValue(4.0)
        self.spn_mru_t.valueChanged.connect(self._recalc_mru_theor)
        h_t.addWidget(self.lbl_mru_t)
        h_t.addWidget(self.spn_mru_t)
        l_grp.addLayout(h_t)

        self.lbl_mru_dist_theor = QLabel("MRU Teórico: v = 0.35 m/s | d = 1.40 m | t = 4.0 s")
        self.lbl_mru_dist_theor.setStyleSheet("color: #a1a1aa; font-size: 12px; font-weight: 500;")
        l_grp.addWidget(self.lbl_mru_dist_theor)

        h_mru_act = QHBoxLayout()
        self.btn_ejecutar_mru = QPushButton("▶ Ejecutar MRU")
        self.btn_ejecutar_mru.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #10b981;
            }
            QPushButton:hover { background-color: #10b981; color: black; }
        """)
        self.btn_ejecutar_mru.clicked.connect(self._ejecutar_mru)

        self.btn_guardar_perfil_mru = QPushButton("💾 Guardar Perfil")
        self.btn_guardar_perfil_mru.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #38bdf8; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #0284c7;
            }
            QPushButton:hover { background-color: #0284c7; color: white; }
        """)
        self.btn_guardar_perfil_mru.clicked.connect(self._guardar_perfil_mru)

        h_mru_act.addWidget(self.btn_ejecutar_mru, stretch=3)
        h_mru_act.addWidget(self.btn_guardar_perfil_mru, stretch=2)
        l_grp.addLayout(h_mru_act)

        left_panel.addWidget(self.grp_mru)

        # Resultados Medidos en Vivo
        self.grp_mru_res = QGroupBox(tr("grp_calculated_results", lang))
        l_res = QVBoxLayout(self.grp_mru_res)

        self.lbl_mru_res_val = QLabel("v_medida = 0.00 m/s\nx_real = 0.00 m")
        self.lbl_mru_res_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #10b981; padding: 8px; font-family: monospace;")
        l_res.addWidget(self.lbl_mru_res_val, alignment=Qt.AlignCenter)

        left_panel.addWidget(self.grp_mru_res)
        left_panel.addStretch()
        layout.addLayout(left_panel, stretch=2)

        # Panel Derecho: Gráficas en Tiempo Real
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        self.grp_mru_plot = QGroupBox("Gráficas Experimentales MRU (Posición y Velocidad vs Tiempo)")
        l_plot = QVBoxLayout(self.grp_mru_plot)
        l_plot.setSpacing(6)

        # Barra de herramientas de gráficas
        h_toggles = QHBoxLayout()
        self.btn_mru_xt = QPushButton(tr("plot_pos", lang))
        self.btn_mru_vt = QPushButton(tr("plot_vel", lang))
        self.btn_mru_sim = QPushButton(tr("plot_simultaneous", lang))

        self.btn_mru_xt.clicked.connect(lambda: self._set_mru_view_mode("xt"))
        self.btn_mru_vt.clicked.connect(lambda: self._set_mru_view_mode("vt"))
        self.btn_mru_sim.clicked.connect(lambda: self._set_mru_view_mode("sim"))

        self.btn_mru_roi = QPushButton("🔍 Recuadro (ROI)")
        self.btn_mru_roi.setCheckable(True)
        self.btn_mru_roi.toggled.connect(self._toggle_mru_roi)

        self.cbo_mru_fit = QComboBox()
        self.cbo_mru_fit.addItems(["Ajuste: Ninguno", "Ajuste: Lineal (x = v*t)", "Ajuste: Cuadrático"])
        self.cbo_mru_fit.currentIndexChanged.connect(self._recalc_mru_fit)

        self.btn_mru_limpiar = QPushButton("Limpiar Gráfica")
        self.btn_mru_limpiar.clicked.connect(self._limpiar_graficas_mru)

        h_toggles.addWidget(self.btn_mru_xt)
        h_toggles.addWidget(self.btn_mru_vt)
        h_toggles.addWidget(self.btn_mru_sim)
        h_toggles.addWidget(self.btn_mru_roi)
        h_toggles.addWidget(self.cbo_mru_fit)
        h_toggles.addWidget(self.btn_mru_limpiar)

        l_plot.addLayout(h_toggles)

        self.mru_plot_stack = QWidget()
        self.mru_stack_layout = QStackedLayout(self.mru_plot_stack)

        # Plot simple (x-t o v-t)
        self.pw_mru_single = pg.PlotWidget()
        self.pw_mru_single.showGrid(x=True, y=True, alpha=0.3)
        self.pw_mru_single.setMouseEnabled(x=True, y=True)
        self.pw_mru_single.setMinimumHeight(240)
        self.pw_mru_single.addLegend(offset=(10, 10))

        # Plots simultáneos (x-t arriba, v-t abajo)
        self.pw_mru_sim_widget = QWidget()
        l_sim = QVBoxLayout(self.pw_mru_sim_widget)
        l_sim.setContentsMargins(0, 0, 0, 0)
        self.pw_mru_sim1 = pg.PlotWidget()
        self.pw_mru_sim2 = pg.PlotWidget()
        self.pw_mru_sim1.showGrid(x=True, y=True, alpha=0.3)
        self.pw_mru_sim2.showGrid(x=True, y=True, alpha=0.3)
        self.pw_mru_sim1.setMouseEnabled(x=True, y=True)
        self.pw_mru_sim2.setMouseEnabled(x=True, y=True)
        self.pw_mru_sim1.setMinimumHeight(160)
        self.pw_mru_sim2.setMinimumHeight(160)
        self.pw_mru_sim1.addLegend(offset=(10, 10))
        self.pw_mru_sim2.addLegend(offset=(10, 10))
        l_sim.addWidget(self.pw_mru_sim1)
        l_sim.addWidget(self.pw_mru_sim2)

        self.mru_stack_layout.addWidget(self.pw_mru_single)
        self.mru_stack_layout.addWidget(self.pw_mru_sim_widget)
        l_plot.addWidget(self.mru_plot_stack)

        # ROI Selector de Región
        self.mru_roi = pg.LinearRegionItem([0.5, 2.5])
        self.mru_roi.setBrush(pg.mkBrush(0, 240, 255, 40))
        self.mru_roi.sigRegionChanged.connect(self._recalc_mru_fit)

        # Etiqueta de Ajuste Matemático
        self.lbl_mru_fit = QLabel("Ajuste Experimental: Ninguno | R² = 1.000")
        self.lbl_mru_fit.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: bold;")
        l_plot.addWidget(self.lbl_mru_fit)

        right_panel.addWidget(self.grp_mru_plot)

        # Historial de Datos de la Gráfica
        grp_mru_data = QGroupBox("Historial de Muestras de la Medición (Tiempo Real)")
        l_mru_data = QVBoxLayout(grp_mru_data)
        l_mru_data.setSpacing(6)

        h_data_ctrl = QHBoxLayout()
        h_data_ctrl.addStretch()
        btn_dl_csv = QPushButton(tr("btn_download_csv", lang))
        btn_dl_csv.clicked.connect(lambda: self._download_table_csv(self.tbl_mru_data, "MRU_Datos_Robot.csv"))
        btn_clr_data = QPushButton(tr("btn_clear_history", lang))
        btn_clr_data.clicked.connect(lambda: self.tbl_mru_data.setRowCount(0))
        h_data_ctrl.addWidget(btn_dl_csv)
        h_data_ctrl.addWidget(btn_clr_data)
        l_mru_data.addLayout(h_data_ctrl)

        self.tbl_mru_data = QTableWidget(0, 5)
        self.tbl_mru_data.setHorizontalHeaderLabels(["Tiempo t (s)", "Posición x (m)", "Velocidad v (m/s)", "Aceleración a (m/s²)", "RPM Promedio"])
        self.tbl_mru_data.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mru_data.setMinimumHeight(150)
        l_mru_data.addWidget(self.tbl_mru_data)

        right_panel.addWidget(grp_mru_data)
        layout.addLayout(right_panel, stretch=3)

        self.mru_view_mode = "xt"
        self._update_mru_calc_var_mode()
        return w

    # =========================================================================
    # 2. PESTAÑA MRUV: ACELERACIÓN CONSTANTE
    # =========================================================================
    def _build_mruv_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setSpacing(12)

        lang = self.app_state.language
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        self.grp_mruv = QGroupBox(tr("grp_mruv_title", lang))
        l_grp = QVBoxLayout(self.grp_mruv)
        l_grp.setSpacing(8)

        # Encabezado informativo para las 5 variables del MRUV
        self.lbl_mruv_known = QLabel(tr("lbl_mruv_known", lang))
        self.lbl_mruv_known.setStyleSheet("font-weight: bold; color: #38bdf8;")
        l_grp.addWidget(self.lbl_mruv_known)

        self.lbl_mruv_status = QLabel("✓ 3 de 3 variables seleccionadas. Desmarca una para elegir otra.")
        self.lbl_mruv_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        l_grp.addWidget(self.lbl_mruv_status)

        sep_mruv = QFrame()
        sep_mruv.setFrameShape(QFrame.HLine)
        sep_mruv.setFrameShadow(QFrame.Sunken)
        sep_mruv.setStyleSheet("color: #30363d;")
        l_grp.addWidget(sep_mruv)

        # 1. Velocidad Inicial v0 (m/s)
        h_v0 = QHBoxLayout()
        self.chk_mruv_v0 = QCheckBox(f"{tr('chk_v0', lang)}:")
        self.chk_mruv_v0.setChecked(True)
        self.spn_mruv_v0 = QDoubleSpinBox()
        self.spn_mruv_v0.setRange(0.00, 1.20)
        self.spn_mruv_v0.setSingleStep(0.05)
        self.spn_mruv_v0.setDecimals(2)
        self.spn_mruv_v0.setSuffix(" m/s")
        self.spn_mruv_v0.setValue(0.15)
        self.chk_mruv_v0.toggled.connect(self._on_mruv_check_toggled)
        self.spn_mruv_v0.valueChanged.connect(self._recalc_mruv_theor)
        h_v0.addWidget(self.chk_mruv_v0)
        h_v0.addWidget(self.spn_mruv_v0)
        l_grp.addLayout(h_v0)

        # 2. Velocidad Final vf (m/s)
        h_vf = QHBoxLayout()
        self.chk_mruv_vf = QCheckBox(f"{tr('chk_vf', lang)}:")
        self.chk_mruv_vf.setChecked(True)
        self.spn_mruv_vf = QDoubleSpinBox()
        self.spn_mruv_vf.setRange(0.00, 1.20)
        self.spn_mruv_vf.setSingleStep(0.05)
        self.spn_mruv_vf.setDecimals(2)
        self.spn_mruv_vf.setSuffix(" m/s")
        self.spn_mruv_vf.setValue(0.65)
        self.chk_mruv_vf.toggled.connect(self._on_mruv_check_toggled)
        self.spn_mruv_vf.valueChanged.connect(self._recalc_mruv_theor)
        h_vf.addWidget(self.chk_mruv_vf)
        h_vf.addWidget(self.spn_mruv_vf)
        l_grp.addLayout(h_vf)

        # 3. Aceleración a (m/s²)
        h_a = QHBoxLayout()
        self.chk_mruv_a = QCheckBox(f"{tr('chk_accel', lang)}:")
        self.chk_mruv_a.setChecked(False)
        self.spn_mruv_a = QDoubleSpinBox()
        self.spn_mruv_a.setRange(-2.00, 2.00)
        self.spn_mruv_a.setSingleStep(0.05)
        self.spn_mruv_a.setDecimals(3)
        self.spn_mruv_a.setSuffix(" m/s²")
        self.spn_mruv_a.setValue(0.100)
        self.chk_mruv_a.toggled.connect(self._on_mruv_check_toggled)
        self.spn_mruv_a.valueChanged.connect(self._recalc_mruv_theor)
        h_a.addWidget(self.chk_mruv_a)
        h_a.addWidget(self.spn_mruv_a)
        l_grp.addLayout(h_a)

        # 4. Distancia d (m)
        h_d = QHBoxLayout()
        self.chk_mruv_d = QCheckBox(f"{tr('chk_distance', lang)}:")
        self.chk_mruv_d.setChecked(False)
        self.spn_mruv_d = QDoubleSpinBox()
        self.spn_mruv_d.setRange(0.05, 36.00)
        self.spn_mruv_d.setSingleStep(0.10)
        self.spn_mruv_d.setDecimals(2)
        self.spn_mruv_d.setSuffix(" m")
        self.spn_mruv_d.setValue(2.00)
        self.chk_mruv_d.toggled.connect(self._on_mruv_check_toggled)
        self.spn_mruv_d.valueChanged.connect(self._recalc_mruv_theor)
        h_d.addWidget(self.chk_mruv_d)
        h_d.addWidget(self.spn_mruv_d)
        l_grp.addLayout(h_d)

        # 5. Tiempo t (s)
        h_t = QHBoxLayout()
        self.chk_mruv_t = QCheckBox(f"{tr('chk_time', lang)}:")
        self.chk_mruv_t.setChecked(True)
        self.spn_mruv_t = QDoubleSpinBox()
        self.spn_mruv_t.setRange(0.5, 30.0)
        self.spn_mruv_t.setSingleStep(0.5)
        self.spn_mruv_t.setDecimals(1)
        self.spn_mruv_t.setSuffix(" s")
        self.spn_mruv_t.setValue(5.0)
        self.chk_mruv_t.toggled.connect(self._on_mruv_check_toggled)
        self.spn_mruv_t.valueChanged.connect(self._recalc_mruv_theor)
        h_t.addWidget(self.chk_mruv_t)
        h_t.addWidget(self.spn_mruv_t)
        l_grp.addLayout(h_t)

        self.lbl_mruv_theor_info = QLabel("MRUV Teórico: v₀ = 0.15 m/s | vf = 0.65 m/s | a = 0.100 m/s² | d = 2.00 m | t = 5.0 s")
        self.lbl_mruv_theor_info.setStyleSheet("color: #a1a1aa; font-size: 12px; font-weight: 500;")
        l_grp.addWidget(self.lbl_mruv_theor_info)

        h_mruv_act = QHBoxLayout()
        self.btn_ejecutar_mruv = QPushButton("▶ Ejecutar MRUV")
        self.btn_ejecutar_mruv.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #38bdf8;
            }
            QPushButton:hover { background-color: #38bdf8; color: black; }
        """)
        self.btn_ejecutar_mruv.clicked.connect(self._ejecutar_mruv)

        self.btn_guardar_perfil_mruv = QPushButton("💾 Guardar Perfil")
        self.btn_guardar_perfil_mruv.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #38bdf8; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #38bdf8;
            }
            QPushButton:hover { background-color: #38bdf8; color: white; }
        """)
        self.btn_guardar_perfil_mruv.clicked.connect(self._guardar_perfil_mruv)

        h_mruv_act.addWidget(self.btn_ejecutar_mruv, stretch=3)
        h_mruv_act.addWidget(self.btn_guardar_perfil_mruv, stretch=2)
        l_grp.addLayout(h_mruv_act)

        left_panel.addWidget(self.grp_mruv)

        self.grp_mruv_res = QGroupBox(tr("grp_calculated_results", lang))
        l_res = QVBoxLayout(self.grp_mruv_res)
        self.lbl_mruv_res_val = QLabel("a_real = 0.00 m/s²\nv_inst = 0.00 m/s")
        self.lbl_mruv_res_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #10b981; padding: 8px; font-family: monospace;")
        l_res.addWidget(self.lbl_mruv_res_val, alignment=Qt.AlignCenter)

        left_panel.addWidget(self.grp_mruv_res)
        left_panel.addStretch()
        layout.addLayout(left_panel, stretch=2)

        # Mappings para iteración rápida
        self.mruv_checks = {
            "v0": self.chk_mruv_v0,
            "vf": self.chk_mruv_vf,
            "a": self.chk_mruv_a,
            "d": self.chk_mruv_d,
            "t": self.chk_mruv_t
        }
        self.mruv_spins = {
            "v0": self.spn_mruv_v0,
            "vf": self.spn_mruv_vf,
            "a": self.spn_mruv_a,
            "d": self.spn_mruv_d,
            "t": self.spn_mruv_t
        }

        # Panel Derecho: Gráficas MRUV
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        self.grp_mruv_plot = QGroupBox("Gráficas Experimentales MRUV (x-t, v-t, a-t)")
        l_plot = QVBoxLayout(self.grp_mruv_plot)
        l_plot.setSpacing(6)

        h_toggles = QHBoxLayout()
        self.btn_mruv_xt = QPushButton(tr("plot_pos", lang))
        self.btn_mruv_vt = QPushButton(tr("plot_vel", lang))
        self.btn_mruv_at = QPushButton(tr("plot_acc", lang))
        self.btn_mruv_sim = QPushButton(tr("plot_simultaneous", lang))

        self.btn_mruv_xt.clicked.connect(lambda: self._set_mruv_view_mode("xt"))
        self.btn_mruv_vt.clicked.connect(lambda: self._set_mruv_view_mode("vt"))
        self.btn_mruv_at.clicked.connect(lambda: self._set_mruv_view_mode("at"))
        self.btn_mruv_sim.clicked.connect(lambda: self._set_mruv_view_mode("sim"))

        self.btn_mruv_roi = QPushButton("🔍 Recuadro (ROI)")
        self.btn_mruv_roi.setCheckable(True)
        self.btn_mruv_roi.toggled.connect(self._toggle_mruv_roi)

        self.cbo_mruv_fit = QComboBox()
        self.cbo_mruv_fit.addItems(["Ajuste: Ninguno", "Ajuste: Cuadrático x(t)", "Ajuste: Lineal v(t)"])
        self.cbo_mruv_fit.currentIndexChanged.connect(self._recalc_mruv_fit)

        self.btn_mruv_limpiar = QPushButton("Limpiar Gráfica")
        self.btn_mruv_limpiar.clicked.connect(self._limpiar_graficas_mruv)

        h_toggles.addWidget(self.btn_mruv_xt)
        h_toggles.addWidget(self.btn_mruv_vt)
        h_toggles.addWidget(self.btn_mruv_at)
        h_toggles.addWidget(self.btn_mruv_sim)
        h_toggles.addWidget(self.btn_mruv_roi)
        h_toggles.addWidget(self.cbo_mruv_fit)
        h_toggles.addWidget(self.btn_mruv_limpiar)

        l_plot.addLayout(h_toggles)

        self.mruv_plot_stack = QWidget()
        self.mruv_stack_layout = QStackedLayout(self.mruv_plot_stack)

        self.pw_mruv_single = pg.PlotWidget()
        self.pw_mruv_single.showGrid(x=True, y=True, alpha=0.3)
        self.pw_mruv_single.setMouseEnabled(x=True, y=True)
        self.pw_mruv_single.setMinimumHeight(240)
        self.pw_mruv_single.addLegend(offset=(10, 10))

        self.pw_mruv_sim_widget = QWidget()
        l_sim = QVBoxLayout(self.pw_mruv_sim_widget)
        l_sim.setContentsMargins(0, 0, 0, 0)
        self.pw_mruv_sim1 = pg.PlotWidget()
        self.pw_mruv_sim2 = pg.PlotWidget()
        self.pw_mruv_sim3 = pg.PlotWidget()
        for pw in [self.pw_mruv_sim1, self.pw_mruv_sim2, self.pw_mruv_sim3]:
            pw.showGrid(x=True, y=True, alpha=0.3)
            pw.setMouseEnabled(x=True, y=True)
            pw.setMinimumHeight(130)
            pw.addLegend(offset=(10, 10))
            l_sim.addWidget(pw)

        self.mruv_stack_layout.addWidget(self.pw_mruv_single)
        self.mruv_stack_layout.addWidget(self.pw_mruv_sim_widget)
        l_plot.addWidget(self.mruv_plot_stack)

        self.mruv_roi = pg.LinearRegionItem([1.0, 3.5])
        self.mruv_roi.setBrush(pg.mkBrush(16, 185, 129, 40))
        self.mruv_roi.sigRegionChanged.connect(self._recalc_mruv_fit)

        self.lbl_mruv_fit = QLabel("Ajuste Experimental: Ninguno | R² = 1.000")
        self.lbl_mruv_fit.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: bold;")
        l_plot.addWidget(self.lbl_mruv_fit)

        right_panel.addWidget(self.grp_mruv_plot)

        # Historial de Datos MRUV
        grp_mruv_data = QGroupBox("Historial de Muestras MRUV")
        l_mruv_data = QVBoxLayout(grp_mruv_data)
        l_mruv_data.setSpacing(6)

        h_data_ctrl = QHBoxLayout()
        h_data_ctrl.addStretch()
        btn_dl_csv = QPushButton(tr("btn_download_csv", lang))
        btn_dl_csv.clicked.connect(lambda: self._download_table_csv(self.tbl_mruv_data, "MRUV_Datos_Robot.csv"))
        btn_clr_data = QPushButton(tr("btn_clear_history", lang))
        btn_clr_data.clicked.connect(lambda: self.tbl_mruv_data.setRowCount(0))
        h_data_ctrl.addWidget(btn_dl_csv)
        h_data_ctrl.addWidget(btn_clr_data)
        l_mruv_data.addLayout(h_data_ctrl)

        self.tbl_mruv_data = QTableWidget(0, 5)
        self.tbl_mruv_data.setHorizontalHeaderLabels(["Tiempo t (s)", "Posición x (m)", "Velocidad v (m/s)", "Aceleración a (m/s²)", "RPM Promedio"])
        self.tbl_mruv_data.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mruv_data.setMinimumHeight(150)
        l_mruv_data.addWidget(self.tbl_mruv_data)

        right_panel.addWidget(grp_mruv_data)
        layout.addLayout(right_panel, stretch=3)

        self.mruv_view_mode = "xt"
        self._on_mruv_check_toggled()
        return w

    # =========================================================================
    # 3. PESTAÑA MCU: MOVIMIENTO CIRCULAR (ORBITAR) Y GIRO PROPIO EJE
    # =========================================================================
    def _build_mcu_tab(self) -> QWidget:
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setSpacing(12)

        lang = self.app_state.language
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)

        self.grp_mcu = QGroupBox(tr("grp_mcu_title", lang))
        l_grp = QVBoxLayout(self.grp_mcu)
        l_grp.setSpacing(8)

        # 1. Selector de Modalidad MCU: "Orbitar" vs "Giro sobre su propio eje"
        h_mode = QHBoxLayout()
        lbl_mode = QLabel("Modalidad MCU:")
        lbl_mode.setStyleSheet("font-weight: bold; color: #c084fc;")
        self.cbo_mcu_mode = QComboBox()
        self.cbo_mcu_mode.addItems([
            "Orbitar",
            "Giro sobre su propio eje"
        ])
        self.cbo_mcu_mode.currentIndexChanged.connect(self._on_mcu_mode_changed)
        h_mode.addWidget(lbl_mode)
        h_mode.addWidget(self.cbo_mcu_mode)
        l_grp.addLayout(h_mode)

        sep_mcu = QFrame()
        sep_mcu.setFrameShape(QFrame.HLine)
        sep_mcu.setFrameShadow(QFrame.Sunken)
        sep_mcu.setStyleSheet("color: #30363d;")
        l_grp.addWidget(sep_mcu)

        # ---------------------------------------------------------------------
        # PANEL A: ORBITAR (Círculo con Radio R)
        # ---------------------------------------------------------------------
        self.panel_mcu_orbit = QWidget()
        l_orbit = QVBoxLayout(self.panel_mcu_orbit)
        l_orbit.setContentsMargins(0, 0, 0, 0)
        l_orbit.setSpacing(8)

        # Radio R (m)
        h_orb_r = QHBoxLayout()
        self.lbl_mcu_orb_r = QLabel("Radio de Órbita R (m):")
        self.spn_mcu_orb_r = QDoubleSpinBox()
        self.spn_mcu_orb_r.setRange(0.10, 5.00)
        self.spn_mcu_orb_r.setSingleStep(0.05)
        self.spn_mcu_orb_r.setDecimals(2)
        self.spn_mcu_orb_r.setSuffix(" m")
        self.spn_mcu_orb_r.setValue(0.40)
        self.spn_mcu_orb_r.valueChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_r.addWidget(self.lbl_mcu_orb_r)
        h_orb_r.addWidget(self.spn_mcu_orb_r)
        l_orbit.addLayout(h_orb_r)

        # Selector Tipo de Velocidad
        h_orb_stype = QHBoxLayout()
        lbl_orb_stype = QLabel("Tipo de Velocidad:")
        lbl_orb_stype.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.cbo_mcu_orb_speed_type = QComboBox()
        self.cbo_mcu_orb_speed_type.addItems([
            "Velocidad lineal (v)",
            "Velocidad angular (ω)"
        ])
        self.cbo_mcu_orb_speed_type.currentIndexChanged.connect(self._on_mcu_orb_speed_type_changed)
        h_orb_stype.addWidget(lbl_orb_stype)
        h_orb_stype.addWidget(self.cbo_mcu_orb_speed_type)
        l_orbit.addLayout(h_orb_stype)

        # Velocidad lineal v (m/s)
        h_orb_v = QHBoxLayout()
        self.lbl_mcu_orb_v = QLabel("Velocidad lineal v (m/s):")
        self.spn_mcu_orb_v = QDoubleSpinBox()
        self.spn_mcu_orb_v.setRange(0.05, 1.00)
        self.spn_mcu_orb_v.setSingleStep(0.05)
        self.spn_mcu_orb_v.setDecimals(2)
        self.spn_mcu_orb_v.setSuffix(" m/s")
        self.spn_mcu_orb_v.setValue(0.30)
        self.spn_mcu_orb_v.valueChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_v.addWidget(self.lbl_mcu_orb_v)
        h_orb_v.addWidget(self.spn_mcu_orb_v)
        l_orbit.addLayout(h_orb_v)

        # Velocidad angular omega (rad/s)
        h_orb_w = QHBoxLayout()
        self.lbl_mcu_orb_omega = QLabel("Velocidad angular ω (rad/s):")
        self.spn_mcu_orb_omega = QDoubleSpinBox()
        self.spn_mcu_orb_omega.setRange(0.10, 6.00)
        self.spn_mcu_orb_omega.setSingleStep(0.10)
        self.spn_mcu_orb_omega.setDecimals(2)
        self.spn_mcu_orb_omega.setSuffix(" rad/s")
        self.spn_mcu_orb_omega.setValue(0.75)
        self.spn_mcu_orb_omega.valueChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_w.addWidget(self.lbl_mcu_orb_omega)
        h_orb_w.addWidget(self.spn_mcu_orb_omega)
        l_orbit.addLayout(h_orb_w)

        # Selector Tipo de Duración
        h_orb_dtype = QHBoxLayout()
        lbl_orb_dtype = QLabel("Definición de Duración:")
        lbl_orb_dtype.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.cbo_mcu_orb_dur_type = QComboBox()
        self.cbo_mcu_orb_dur_type.addItems([
            "Tiempo de duración (t)",
            "Número de vueltas (N)"
        ])
        self.cbo_mcu_orb_dur_type.currentIndexChanged.connect(self._on_mcu_orb_dur_type_changed)
        h_orb_dtype.addWidget(lbl_orb_dtype)
        h_orb_dtype.addWidget(self.cbo_mcu_orb_dur_type)
        l_orbit.addLayout(h_orb_dtype)

        # Tiempo t (s)
        h_orb_t = QHBoxLayout()
        self.lbl_mcu_orb_t = QLabel("Tiempo de duración t (s):")
        self.spn_mcu_orb_t = QDoubleSpinBox()
        self.spn_mcu_orb_t.setRange(0.5, 30.0)
        self.spn_mcu_orb_t.setSingleStep(0.5)
        self.spn_mcu_orb_t.setDecimals(1)
        self.spn_mcu_orb_t.setSuffix(" s")
        self.spn_mcu_orb_t.setValue(5.0)
        self.spn_mcu_orb_t.valueChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_t.addWidget(self.lbl_mcu_orb_t)
        h_orb_t.addWidget(self.spn_mcu_orb_t)
        l_orbit.addLayout(h_orb_t)

        # Número de vueltas N
        h_orb_n = QHBoxLayout()
        self.lbl_mcu_orb_n = QLabel("Número de vueltas (N):")
        self.spn_mcu_orb_n = QDoubleSpinBox()
        self.spn_mcu_orb_n.setRange(0.25, 10.00)
        self.spn_mcu_orb_n.setSingleStep(0.25)
        self.spn_mcu_orb_n.setDecimals(2)
        self.spn_mcu_orb_n.setSuffix(" vueltas")
        self.spn_mcu_orb_n.setValue(1.00)
        self.spn_mcu_orb_n.valueChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_n.addWidget(self.lbl_mcu_orb_n)
        h_orb_n.addWidget(self.spn_mcu_orb_n)
        l_orbit.addLayout(h_orb_n)

        # Sentido de giro Orbitar
        h_orb_dir = QHBoxLayout()
        h_orb_dir.addWidget(QLabel("Sentido de Giro:"))
        self.cbo_mcu_orb_dir = QComboBox()
        self.cbo_mcu_orb_dir.addItems(["Horario (CW)", "Antihorario (CCW)"])
        self.cbo_mcu_orb_dir.currentIndexChanged.connect(self._recalc_mcu_orb_theor)
        h_orb_dir.addWidget(self.cbo_mcu_orb_dir)
        l_orbit.addLayout(h_orb_dir)

        l_grp.addWidget(self.panel_mcu_orbit)

        # ---------------------------------------------------------------------
        # PANEL B: GIRO SOBRE SU PROPIO EJE
        # ---------------------------------------------------------------------
        self.panel_mcu_spin = QWidget()
        l_spin = QVBoxLayout(self.panel_mcu_spin)
        l_spin.setContentsMargins(0, 0, 0, 0)
        l_spin.setSpacing(8)

        # Velocidad angular omega (rad/s) únicamente
        h_spin_w = QHBoxLayout()
        self.lbl_mcu_spin_omega = QLabel("Velocidad angular ω (rad/s):")
        self.lbl_mcu_spin_omega.setStyleSheet("font-weight: bold; color: #c084fc;")
        self.spn_mcu_spin_omega = QDoubleSpinBox()
        self.spn_mcu_spin_omega.setRange(0.10, 8.00)
        self.spn_mcu_spin_omega.setSingleStep(0.20)
        self.spn_mcu_spin_omega.setDecimals(2)
        self.spn_mcu_spin_omega.setSuffix(" rad/s")
        self.spn_mcu_spin_omega.setValue(1.50)
        self.spn_mcu_spin_omega.valueChanged.connect(self._recalc_mcu_spin_theor)
        h_spin_w.addWidget(self.lbl_mcu_spin_omega)
        h_spin_w.addWidget(self.spn_mcu_spin_omega)
        l_spin.addLayout(h_spin_w)

        # Selector variable duración (Por Tiempo vs Por Ángulo)
        h_spin_param = QHBoxLayout()
        lbl_spin_param = QLabel("Definición de Duración:")
        lbl_spin_param.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        self.cbo_mcu_spin_param = QComboBox()
        self.cbo_mcu_spin_param.addItems([
            "Por Tiempo (t)",
            "Por Ángulo (θ°)"
        ])
        self.cbo_mcu_spin_param.currentIndexChanged.connect(self._on_mcu_spin_param_changed)
        h_spin_param.addWidget(lbl_spin_param)
        h_spin_param.addWidget(self.cbo_mcu_spin_param)
        l_spin.addLayout(h_spin_param)

        # Tiempo t (s)
        h_spin_t = QHBoxLayout()
        self.lbl_mcu_spin_t = QLabel("Tiempo de giro t (s):")
        self.spn_mcu_spin_t = QDoubleSpinBox()
        self.spn_mcu_spin_t.setRange(0.5, 30.0)
        self.spn_mcu_spin_t.setSingleStep(0.5)
        self.spn_mcu_spin_t.setDecimals(1)
        self.spn_mcu_spin_t.setSuffix(" s")
        self.spn_mcu_spin_t.setValue(3.0)
        self.spn_mcu_spin_t.valueChanged.connect(self._recalc_mcu_spin_theor)
        h_spin_t.addWidget(self.lbl_mcu_spin_t)
        h_spin_t.addWidget(self.spn_mcu_spin_t)
        l_spin.addLayout(h_spin_t)

        # Ángulo theta (°)
        h_spin_ang = QHBoxLayout()
        self.lbl_mcu_spin_ang = QLabel("Ángulo de giro θ (°):")
        self.spn_mcu_spin_ang = QDoubleSpinBox()
        self.spn_mcu_spin_ang.setRange(10.0, 1440.0)
        self.spn_mcu_spin_ang.setSingleStep(15.0)
        self.spn_mcu_spin_ang.setDecimals(1)
        self.spn_mcu_spin_ang.setSuffix("°")
        self.spn_mcu_spin_ang.setValue(180.0)
        self.spn_mcu_spin_ang.valueChanged.connect(self._recalc_mcu_spin_theor)
        h_spin_ang.addWidget(self.lbl_mcu_spin_ang)
        h_spin_ang.addWidget(self.spn_mcu_spin_ang)
        l_spin.addLayout(h_spin_ang)

        # Sentido de giro Propio Eje
        h_spin_dir = QHBoxLayout()
        h_spin_dir.addWidget(QLabel("Sentido de Giro:"))
        self.cbo_mcu_spin_dir = QComboBox()
        self.cbo_mcu_spin_dir.addItems(["Horario (CW)", "Antihorario (CCW)"])
        self.cbo_mcu_spin_dir.currentIndexChanged.connect(self._recalc_mcu_spin_theor)
        h_spin_dir.addWidget(self.cbo_mcu_spin_dir)
        l_spin.addLayout(h_spin_dir)

        l_grp.addWidget(self.panel_mcu_spin)

        # ---------------------------------------------------------------------
        # ELEMENTOS COMUNES MCU
        # ---------------------------------------------------------------------
        self.lbl_mcu_theor_info = QLabel("MCU Teórico")
        self.lbl_mcu_theor_info.setStyleSheet("color: #a1a1aa; font-size: 12px; font-weight: 500;")
        l_grp.addWidget(self.lbl_mcu_theor_info)

        h_mcu_act = QHBoxLayout()
        self.btn_ejecutar_mcu = QPushButton("▶ Ejecutar en Robot")
        self.btn_ejecutar_mcu.setStyleSheet("""
            QPushButton {
                background-color: #7c3aed; color: white; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #c084fc;
            }
            QPushButton:hover { background-color: #c084fc; color: black; }
        """)
        self.btn_ejecutar_mcu.clicked.connect(self._ejecutar_mcu)

        self.btn_guardar_perfil_mcu = QPushButton("💾 Guardar Perfil")
        self.btn_guardar_perfil_mcu.setStyleSheet("""
            QPushButton {
                background-color: #1e293b; color: #c084fc; font-weight: bold; font-size: 13px;
                padding: 10px; border-radius: 6px; border: 1px solid #9333ea;
            }
            QPushButton:hover { background-color: #9333ea; color: white; }
        """)
        self.btn_guardar_perfil_mcu.clicked.connect(self._guardar_perfil_mcu)

        h_mcu_act.addWidget(self.btn_ejecutar_mcu, stretch=3)
        h_mcu_act.addWidget(self.btn_guardar_perfil_mcu, stretch=2)
        l_grp.addLayout(h_mcu_act)

        # Botón backward-compatible para giro directo (oculto)
        self.btn_mcu_giro_directo = QPushButton("🔄 Girar Propio Eje Ya")
        self.btn_mcu_giro_directo.clicked.connect(self._ejecutar_giro_directo)
        self.btn_mcu_giro_directo.hide()

        # Aliases para compatibilidad con código existente
        self.spn_mcu_r = self.spn_mcu_orb_r
        self.spn_mcu_v = self.spn_mcu_orb_v
        self.spn_mcu_t = self.spn_mcu_orb_t
        self.cbo_mcu_dir = self.cbo_mcu_orb_dir

        left_panel.addWidget(self.grp_mcu)

        # Resultados Medidos en Vivo
        self.grp_mcu_res = QGroupBox(tr("grp_calculated_results", lang))
        l_res = QVBoxLayout(self.grp_mcu_res)
        self.lbl_mcu_res_val = QLabel("ω_real = 0.00 rad/s\na_c = 0.00 m/s²")
        self.lbl_mcu_res_val.setStyleSheet("font-size: 18px; font-weight: bold; color: #c084fc; padding: 8px; font-family: monospace;")
        l_res.addWidget(self.lbl_mcu_res_val, alignment=Qt.AlignCenter)

        left_panel.addWidget(self.grp_mcu_res)
        left_panel.addStretch()
        layout.addLayout(left_panel, stretch=2)

        # ---------------------------------------------------------------------
        # PANEL DERECHO: VISTA GRÁFICA (ORBITAR) vs MENSAJE NO-PLOT (PROPIO EJE)
        # ---------------------------------------------------------------------
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)

        self.grp_mcu_plot = QGroupBox("Trayectoria 2D en Vivo (Odometría Diferencial x-y)")
        l_plot_container = QVBoxLayout(self.grp_mcu_plot)
        l_plot_container.setSpacing(6)

        self.mcu_plot_stack = QWidget()
        self.mcu_plot_layout = QStackedLayout(self.mcu_plot_stack)

        # Vista 0: Orbitar con gráfica 2D
        self.widget_orbit_plot = QWidget()
        l_orb_plot = QVBoxLayout(self.widget_orbit_plot)
        l_orb_plot.setContentsMargins(0, 0, 0, 0)
        l_orb_plot.setSpacing(6)

        h_mcu_tools = QHBoxLayout()
        self.btn_mcu_limpiar = QPushButton("Limpiar Trayectoria")
        self.btn_mcu_limpiar.clicked.connect(self._limpiar_graficas_mcu)
        h_mcu_tools.addStretch()
        h_mcu_tools.addWidget(self.btn_mcu_limpiar)
        l_orb_plot.addLayout(h_mcu_tools)

        self.pw_mcu = pg.PlotWidget()
        self.pw_mcu.showGrid(x=True, y=True, alpha=0.3)
        self.pw_mcu.setAspectLocked(True)
        self.pw_mcu.setMouseEnabled(x=True, y=True)
        self.pw_mcu.setMinimumHeight(280)
        self.pw_mcu.setLabel('bottom', 'Posición X', units='m')
        self.pw_mcu.setLabel('left', 'Posición Y', units='m')
        self.pw_mcu.addLegend(offset=(10, 10))
        l_orb_plot.addWidget(self.pw_mcu)

        # Vista 1: Giro Propio Eje SIN GRÁFICA 2D (Requerimiento explícito: NO SE DEBE GRAFICAR)
        self.widget_spin_no_plot = QWidget()
        l_spin_no_plot = QVBoxLayout(self.widget_spin_no_plot)
        l_spin_no_plot.setAlignment(Qt.AlignCenter)
        l_spin_no_plot.setSpacing(12)

        lbl_spin_icon = QLabel("🔄")
        lbl_spin_icon.setStyleSheet("font-size: 52px; color: #c084fc;")
        lbl_spin_icon.setAlignment(Qt.AlignCenter)

        self.lbl_mcu_no_plot = QLabel(
            "La rotación sobre el propio eje es un giro angular en el centro sin traslación x-y.\n"
            "Gráfica de trayectoria deshabilitada."
        )
        self.lbl_mcu_no_plot.setAlignment(Qt.AlignCenter)
        self.lbl_mcu_no_plot.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: bold;
                color: #e2e8f0;
                background-color: #161b22;
                border: 1.5px dashed #7c3aed;
                border-radius: 8px;
                padding: 20px;
                line-height: 1.5;
            }
        """)

        self.lbl_mcu_spin_live_info = QLabel("Ángulo acumulado en vivo: 0.0° | ω: 0.00 rad/s")
        self.lbl_mcu_spin_live_info.setStyleSheet("font-size: 13px; font-weight: bold; color: #c084fc; padding: 6px;")
        self.lbl_mcu_spin_live_info.setAlignment(Qt.AlignCenter)

        l_spin_no_plot.addStretch()
        l_spin_no_plot.addWidget(lbl_spin_icon)
        l_spin_no_plot.addWidget(self.lbl_mcu_no_plot)
        l_spin_no_plot.addWidget(self.lbl_mcu_spin_live_info)
        l_spin_no_plot.addStretch()

        self.mcu_plot_layout.addWidget(self.widget_orbit_plot)
        self.mcu_plot_layout.addWidget(self.widget_spin_no_plot)
        l_plot_container.addWidget(self.mcu_plot_stack)

        right_panel.addWidget(self.grp_mcu_plot)

        # Tabla MCU
        grp_mcu_data = QGroupBox("Historial de Muestras MCU")
        l_mcu_data = QVBoxLayout(grp_mcu_data)
        l_mcu_data.setSpacing(6)

        h_data_ctrl = QHBoxLayout()
        h_data_ctrl.addStretch()
        btn_dl_csv = QPushButton(tr("btn_download_csv", lang))
        btn_dl_csv.clicked.connect(lambda: self._download_table_csv(self.tbl_mcu_data, "MCU_Datos_Robot.csv"))
        btn_clr_data = QPushButton(tr("btn_clear_history", lang))
        btn_clr_data.clicked.connect(lambda: self.tbl_mcu_data.setRowCount(0))
        h_data_ctrl.addWidget(btn_dl_csv)
        h_data_ctrl.addWidget(btn_clr_data)
        l_mcu_data.addLayout(h_data_ctrl)

        self.tbl_mcu_data = QTableWidget(0, 5)
        self.tbl_mcu_data.setHorizontalHeaderLabels(["Tiempo t (s)", "Pos X (m)", "Pos Y (m)", "ω (rad/s)", "a_c (m/s²)"])
        self.tbl_mcu_data.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_mcu_data.setMinimumHeight(150)
        l_mcu_data.addWidget(self.tbl_mcu_data)

        right_panel.addWidget(grp_mcu_data)
        layout.addLayout(right_panel, stretch=3)

        # Inicialización de vistas y recálculo
        self._on_mcu_mode_changed()
        return w

    # =========================================================================
    # 4. PESTAÑA MOVIMIENTO LIBRE (DIBUJO A MANO Y REPRODUCCIÓN)
    # =========================================================================
    def _build_free_draw_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)

        lang = self.app_state.language

        ctrl_bar = QHBoxLayout()
        ctrl_bar.setSpacing(12)

        ctrl_bar.addWidget(QLabel("Dibujar sobre:"))
        self.rb_draw_x = QRadioButton("x(t)")
        self.rb_draw_v = QRadioButton("v(t)")
        self.rb_draw_a = QRadioButton("a(t)")
        self.rb_draw_x.setChecked(True)

        self.rb_draw_x.toggled.connect(self._on_draw_mode_changed)
        self.rb_draw_v.toggled.connect(self._on_draw_mode_changed)
        self.rb_draw_a.toggled.connect(self._on_draw_mode_changed)

        ctrl_bar.addWidget(self.rb_draw_x)
        ctrl_bar.addWidget(self.rb_draw_v)
        ctrl_bar.addWidget(self.rb_draw_a)

        ctrl_bar.addSpacing(16)
        ctrl_bar.addWidget(QLabel("Escala de tiempo (T max):"))
        self.spn_t_max = QDoubleSpinBox()
        self.spn_t_max.setRange(1.0, 30.0)
        self.spn_t_max.setValue(6.0)
        self.spn_t_max.setSuffix(" s")
        self.spn_t_max.valueChanged.connect(self._on_free_t_max_changed)
        ctrl_bar.addWidget(self.spn_t_max)

        self.btn_clear_canvas = QPushButton("Limpiar Trazo")
        self.btn_clear_canvas.clicked.connect(self._on_clear_canvas)
        ctrl_bar.addWidget(self.btn_clear_canvas)

        self.btn_execute_free = QPushButton("▶ Ejecutar Trazo en Robot")
        self.btn_execute_free.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #38bdf8; color: black; }
        """)
        self.btn_execute_free.clicked.connect(self._ejecutar_trazo_en_robot)
        ctrl_bar.addWidget(self.btn_execute_free)

        layout.addLayout(ctrl_bar)

        self.canvas_widget = KinematicCanvasWidget()
        self.canvas_widget.set_theme_mode(self.app_state.theme_mode)
        self.canvas_widget.points_updated.connect(self._on_canvas_points_updated)
        layout.addWidget(self.canvas_widget)

        self.lbl_plots_t = QLabel("Gráficas Cinemáticas Resultantes (Trazo vs Medición Real del Robot)")
        self.lbl_plots_t.setStyleSheet("font-weight: bold; color: #00f0ff; font-size: 13px;")
        layout.addWidget(self.lbl_plots_t)

        h_plots = QHBoxLayout()
        h_plots.setSpacing(10)

        # Plot x(t)
        self.grp_free_x = QGroupBox("Posición x(t)")
        l_x = QVBoxLayout(self.grp_free_x)
        self.pw_free_x = pg.PlotWidget()
        self.pw_free_x.showGrid(x=True, y=True, alpha=0.3)
        self.pw_free_x.setMinimumHeight(160)
        self.pw_free_x.setLabel('bottom', 'Tiempo t', units='s')
        self.pw_free_x.setLabel('left', 'Posición x', units='m')
        self.pw_free_x.addLegend(offset=(10, 10))
        self.curve_free_x_theor = self.pw_free_x.plot([], [], pen=pg.mkPen(color='#00f0ff', width=3), name="Trazo x(t)")
        self.curve_free_x_real = self.pw_free_x.plot([], [], pen=pg.mkPen(color='#fbbf24', width=2, style=Qt.DashLine), name="Medido Real x(t)")
        l_x.addWidget(self.pw_free_x)
        h_plots.addWidget(self.grp_free_x)

        # Plot v(t)
        self.grp_free_v = QGroupBox("Velocidad v(t)")
        l_v = QVBoxLayout(self.grp_free_v)
        self.pw_free_v = pg.PlotWidget()
        self.pw_free_v.showGrid(x=True, y=True, alpha=0.3)
        self.pw_free_v.setMinimumHeight(160)
        self.pw_free_v.setLabel('bottom', 'Tiempo t', units='s')
        self.pw_free_v.setLabel('left', 'Velocidad v', units='m/s')
        self.pw_free_v.addLegend(offset=(10, 10))
        self.curve_free_v_theor = self.pw_free_v.plot([], [], pen=pg.mkPen(color='#10b981', width=3), name="Trazo v(t)")
        self.curve_free_v_real = self.pw_free_v.plot([], [], pen=pg.mkPen(color='#fbbf24', width=2, style=Qt.DashLine), name="Medido Real v(t)")
        l_v.addWidget(self.pw_free_v)
        h_plots.addWidget(self.grp_free_v)

        layout.addLayout(h_plots)
        self.last_canvas_data = None
        return w

    # =========================================================================
    # LÓGICA DE EJECUCIÓN CINEMÁTICA Y ENVÍO SERIAL REAL
    # =========================================================================
    def _ejecutar_mru(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()

        if not self.app_state.dongle_connected:
            QMessageBox.warning(self, "Dongle Desconectado", "Conecta primero el Dongle ESP8266 en la barra superior.")
            return

        v = float(self.spn_mru_v.value())
        d = float(self.spn_mru_d.value())
        t = float(self.spn_mru_t.value())

        if v < 0.05 or v > 1.20:
            QMessageBox.warning(
                self,
                "Velocidad Fuera de Rango",
                f"La velocidad resultante ({v:.2f} m/s) debe estar en el rango seguro de 0.05 a 1.20 m/s."
            )
            return

        if t < 0.2:
            QMessageBox.warning(
                self,
                "Tiempo Insuficiente",
                f"El tiempo de ejecución ({t:.2f} s) debe ser mayor a 0.2 s para garantizar la maniobra."
            )
            return

        self._limpiar_graficas_mru()
        self.app_state.start_motion(f"MRU (v={v:.2f} m/s, d={d:.2f} m, t={t:.1f}s)", profile_type="MRU")
        self.app_state.client.send_mobile_mru(v, t)

    def _guardar_perfil_mru(self):
        v = float(self.spn_mru_v.value())
        d = float(self.spn_mru_d.value())
        t = float(self.spn_mru_t.value())
        params = {"v": v, "d": d, "dur": t}
        modal = ProfileSaveModal(
            app_state=self.app_state,
            motion_type="MRU",
            params=params,
            default_name=f"MRU {v:.2f} m/s ({t:.1f}s)",
            parent=self
        )
        modal.exec()

    def _ejecutar_mruv(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()

        if not self.app_state.dongle_connected:
            QMessageBox.warning(self, "Dongle Desconectado", "Conecta primero el Dongle ESP8266 en la barra superior.")
            return

        v0 = float(self.spn_mruv_v0.value())
        vf = float(self.spn_mruv_vf.value())
        a  = float(self.spn_mruv_a.value())
        d  = float(self.spn_mruv_d.value())
        t  = float(self.spn_mruv_t.value())

        if t < 0.5:
            QMessageBox.warning(
                self,
                "Tiempo Insuficiente",
                f"El tiempo de ejecución ({t:.1f} s) debe ser mayor o igual a 0.5 s para garantizar la rampa de aceleración."
            )
            return

        if v0 < 0.00 or v0 > 1.20 or vf < 0.05 or vf > 1.20:
            QMessageBox.warning(
                self,
                "Velocidades Fuera de Rango",
                f"Las velocidades deben estar dentro del margen físico alcanzable del robot:\n"
                f"• Velocidad Inicial v₀ ({v0:.2f} m/s): debe ser de 0.00 a 1.20 m/s.\n"
                f"• Velocidad Final vf ({vf:.2f} m/s): debe ser de 0.05 a 1.20 m/s."
            )
            return

        self._limpiar_graficas_mruv()
        self.app_state.start_motion(f"MRUV (v0={v0:.2f}, vf={vf:.2f}, a={a:.3f}, d={d:.2f}m, t={t:.1f}s)", profile_type="MRUV")
        self.app_state.client.send_mobile_mruv(v0, vf, t)

    def _guardar_perfil_mruv(self):
        v0 = float(self.spn_mruv_v0.value())
        vf = float(self.spn_mruv_vf.value())
        a = float(self.spn_mruv_a.value())
        d = float(self.spn_mruv_d.value())
        t = float(self.spn_mruv_t.value())
        params = {"v0": v0, "vf": vf, "a": a, "d": d, "dur": t}
        modal = ProfileSaveModal(
            app_state=self.app_state,
            motion_type="MRUV",
            params=params,
            default_name=f"MRUV {v0:.2f}→{vf:.2f} m/s ({t:.1f}s)",
            parent=self
        )
        modal.exec()

    def _on_mcu_mode_changed(self):
        modo = self.cbo_mcu_mode.currentText()
        if modo == "Giro sobre su propio eje":
            self.panel_mcu_orbit.hide()
            self.panel_mcu_spin.show()
            self.mcu_plot_layout.setCurrentIndex(1)
            self.grp_mcu_plot.setTitle("Giro sobre Propio Eje (Sin Trayectoria Espacial x-y)")
            self.btn_ejecutar_mcu.setText("▶ Ejecutar Giro Propio Eje en Robot")
            self._on_mcu_spin_param_changed()
            self._recalc_mcu_spin_theor()
        else:  # "Orbitar"
            self.panel_mcu_spin.hide()
            self.panel_mcu_orbit.show()
            self.mcu_plot_layout.setCurrentIndex(0)
            self.grp_mcu_plot.setTitle("Trayectoria 2D en Vivo (Odometría Diferencial x-y)")
            self.btn_ejecutar_mcu.setText("▶ Ejecutar Orbitar en Robot")
            self._on_mcu_orb_speed_type_changed()
            self._on_mcu_orb_dur_type_changed()
            self._recalc_mcu_orb_theor()

    def _on_mcu_spin_param_changed(self):
        if not hasattr(self, 'cbo_mcu_spin_param') or not hasattr(self, 'spn_mcu_spin_t'):
            return

        mode = self.cbo_mcu_spin_param.currentText()
        style_calc = """
            QDoubleSpinBox:disabled {
                background-color: rgba(124, 58, 237, 0.15);
                color: #c084fc;
                border: 1.5px dashed #7c3aed;
                font-weight: bold;
            }
        """

        if mode == "Por Tiempo (t)":
            self.spn_mcu_spin_t.setEnabled(True)
            self.spn_mcu_spin_t.setStyleSheet("")
            self.spn_mcu_spin_ang.setEnabled(False)
            self.spn_mcu_spin_ang.setStyleSheet(style_calc)
            self.spn_mcu_spin_ang.setToolTip("Ángulo calculado automáticamente: θ° = (ω · t · 180) / π")
            self.spn_mcu_spin_t.setToolTip("Tiempo de duración editable en segundos")
        else:  # "Por Ángulo (θ°)"
            self.spn_mcu_spin_ang.setEnabled(True)
            self.spn_mcu_spin_ang.setStyleSheet("")
            self.spn_mcu_spin_t.setEnabled(False)
            self.spn_mcu_spin_t.setStyleSheet(style_calc)
            self.spn_mcu_spin_t.setToolTip("Tiempo calculado automáticamente: t = (θ° · π) / (180 · ω)")
            self.spn_mcu_spin_ang.setToolTip("Ángulo total de giro editable en grados")

        self._recalc_mcu_spin_theor()

    def _recalc_mcu_spin_theor(self):
        if not hasattr(self, 'spn_mcu_spin_omega') or not hasattr(self, 'cbo_mcu_spin_param'):
            return

        omega = max(0.10, float(self.spn_mcu_spin_omega.value()))
        mode = self.cbo_mcu_spin_param.currentText()

        if mode == "Por Tiempo (t)":
            t = float(self.spn_mcu_spin_t.value())
            ang_deg = (omega * t * 180.0) / math.pi
            ang_deg = max(10.0, min(1440.0, ang_deg))
            self.spn_mcu_spin_ang.blockSignals(True)
            self.spn_mcu_spin_ang.setValue(ang_deg)
            self.spn_mcu_spin_ang.blockSignals(False)
        else:  # "Por Ángulo (θ°)"
            ang_deg = float(self.spn_mcu_spin_ang.value())
            t = (ang_deg * math.pi) / (180.0 * omega)
            t = max(0.5, min(30.0, t))
            self.spn_mcu_spin_t.blockSignals(True)
            self.spn_mcu_spin_t.setValue(t)
            self.spn_mcu_spin_t.blockSignals(False)

        t_val = self.spn_mcu_spin_t.value()
        ang_val = self.spn_mcu_spin_ang.value()
        v_wheel = omega * (ANCHO_VIA_M / 2.0)
        sentido = self.cbo_mcu_spin_dir.currentText() if hasattr(self, 'cbo_mcu_spin_dir') else "Horario (CW)"

        if hasattr(self, 'lbl_mcu_theor_info'):
            self.lbl_mcu_theor_info.setText(
                f"Giro Propio Eje Teórico: ω = {omega:.2f} rad/s | θ = {ang_val:.1f}° | t = {t_val:.1f} s | v_rueda = {v_wheel:.3f} m/s ({sentido})"
            )

    def _on_mcu_orb_speed_type_changed(self):
        if not hasattr(self, 'cbo_mcu_orb_speed_type') or not hasattr(self, 'spn_mcu_orb_v'):
            return

        stype = self.cbo_mcu_orb_speed_type.currentText()
        style_calc = """
            QDoubleSpinBox:disabled {
                background-color: rgba(124, 58, 237, 0.15);
                color: #c084fc;
                border: 1.5px dashed #7c3aed;
                font-weight: bold;
            }
        """

        if stype == "Velocidad lineal (v)":
            self.spn_mcu_orb_v.setEnabled(True)
            self.spn_mcu_orb_v.setStyleSheet("")
            self.spn_mcu_orb_omega.setEnabled(False)
            self.spn_mcu_orb_omega.setStyleSheet(style_calc)
            self.spn_mcu_orb_omega.setToolTip("Velocidad angular calculada: ω = v / R")
            self.spn_mcu_orb_v.setToolTip("Velocidad tangencial lineal editable")
        else:  # "Velocidad angular (ω)"
            self.spn_mcu_orb_omega.setEnabled(True)
            self.spn_mcu_orb_omega.setStyleSheet("")
            self.spn_mcu_orb_v.setEnabled(False)
            self.spn_mcu_orb_v.setStyleSheet(style_calc)
            self.spn_mcu_orb_v.setToolTip("Velocidad lineal calculada: v = ω · R")
            self.spn_mcu_orb_omega.setToolTip("Velocidad angular de órbita editable")

        self._recalc_mcu_orb_theor()

    def _on_mcu_orb_dur_type_changed(self):
        if not hasattr(self, 'cbo_mcu_orb_dur_type') or not hasattr(self, 'spn_mcu_orb_t'):
            return

        dtype = self.cbo_mcu_orb_dur_type.currentText()
        style_calc = """
            QDoubleSpinBox:disabled {
                background-color: rgba(124, 58, 237, 0.15);
                color: #c084fc;
                border: 1.5px dashed #7c3aed;
                font-weight: bold;
            }
        """

        if dtype == "Tiempo de duración (t)":
            self.spn_mcu_orb_t.setEnabled(True)
            self.spn_mcu_orb_t.setStyleSheet("")
            self.spn_mcu_orb_n.setEnabled(False)
            self.spn_mcu_orb_n.setStyleSheet(style_calc)
            self.spn_mcu_orb_n.setToolTip("Número de vueltas calculado: N = (ω · t) / (2π)")
            self.spn_mcu_orb_t.setToolTip("Tiempo de duración editable en segundos")
        else:  # "Número de vueltas (N)"
            self.spn_mcu_orb_n.setEnabled(True)
            self.spn_mcu_orb_n.setStyleSheet("")
            self.spn_mcu_orb_t.setEnabled(False)
            self.spn_mcu_orb_t.setStyleSheet(style_calc)
            self.spn_mcu_orb_t.setToolTip("Tiempo calculado automáticamente: t = (2π · N) / ω")
            self.spn_mcu_orb_n.setToolTip("Número total de vueltas orbitales editable")

        self._recalc_mcu_orb_theor()

    def _recalc_mcu_orb_theor(self):
        if not hasattr(self, 'spn_mcu_orb_r') or not hasattr(self, 'cbo_mcu_orb_speed_type'):
            return

        r = max(0.05, float(self.spn_mcu_orb_r.value()))
        stype = self.cbo_mcu_orb_speed_type.currentText()

        # Cálculo de velocidades
        if stype == "Velocidad lineal (v)":
            v = float(self.spn_mcu_orb_v.value())
            omega = v / r
            omega = max(0.10, min(6.00, omega))
            self.spn_mcu_orb_omega.blockSignals(True)
            self.spn_mcu_orb_omega.setValue(omega)
            self.spn_mcu_orb_omega.blockSignals(False)
        else:  # "Velocidad angular (ω)"
            omega = float(self.spn_mcu_orb_omega.value())
            v = omega * r
            v = max(0.05, min(1.00, v))
            self.spn_mcu_orb_v.blockSignals(True)
            self.spn_mcu_orb_v.setValue(v)
            self.spn_mcu_orb_v.blockSignals(False)

        v_val = self.spn_mcu_orb_v.value()
        omega_val = self.spn_mcu_orb_omega.value()
        dtype = self.cbo_mcu_orb_dur_type.currentText()

        # Cálculo de duración
        if dtype == "Tiempo de duración (t)":
            t = float(self.spn_mcu_orb_t.value())
            n = (omega_val * t) / (2.0 * math.pi) if omega_val > 0 else 0.0
            n = max(0.25, min(10.00, n))
            self.spn_mcu_orb_n.blockSignals(True)
            self.spn_mcu_orb_n.setValue(n)
            self.spn_mcu_orb_n.blockSignals(False)
        else:  # "Número de vueltas (N)"
            n = float(self.spn_mcu_orb_n.value())
            t = (2.0 * math.pi * n) / omega_val if omega_val > 0 else 0.5
            t = max(0.5, min(30.0, t))
            self.spn_mcu_orb_t.blockSignals(True)
            self.spn_mcu_orb_t.setValue(t)
            self.spn_mcu_orb_t.blockSignals(False)

        t_val = self.spn_mcu_orb_t.value()
        n_val = self.spn_mcu_orb_n.value()
        ac = (v_val * v_val) / r

        if hasattr(self, 'lbl_mcu_theor_info'):
            self.lbl_mcu_theor_info.setText(
                f"Orbitar Teórico: R = {r:.2f} m | v = {v_val:.2f} m/s | ω = {omega_val:.2f} rad/s | a_c = {ac:.2f} m/s² | t = {t_val:.1f} s | N = {n_val:.2f} vueltas"
            )

        # Actualizar órbita teórica en la gráfica si estamos en modo Orbitar y no hay perfil activo
        if hasattr(self, 'cbo_mcu_mode') and self.cbo_mcu_mode.currentText() == "Orbitar":
            if not self.app_state.profile_active:
                self.pw_mcu.clear()
                theta_pts = np.linspace(0, 2 * math.pi, 100)
                x_circle = r * np.cos(theta_pts)
                y_circle = r * np.sin(theta_pts)
                self.pw_mcu.plot(x_circle, y_circle, pen=pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine), name="Órbita Teórica")

    def _recalc_mcu_theor(self):
        if not hasattr(self, 'cbo_mcu_mode'):
            return
        modo = self.cbo_mcu_mode.currentText()
        if modo == "Giro sobre su propio eje":
            self._recalc_mcu_spin_theor()
        else:
            self._recalc_mcu_orb_theor()

    def _ejecutar_giro_directo(self):
        self.cbo_mcu_mode.setCurrentText("Giro sobre su propio eje")
        self._ejecutar_mcu()

    def _ejecutar_mcu(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()

        if not self.app_state.dongle_connected:
            QMessageBox.warning(self, "Dongle Desconectado", "Conecta primero el Dongle ESP8266 en la barra superior.")
            return

        modo = self.cbo_mcu_mode.currentText()

        if modo == "Giro sobre su propio eje":
            omega = float(self.spn_mcu_spin_omega.value())
            t = float(self.spn_mcu_spin_t.value())
            ang_deg = float(self.spn_mcu_spin_ang.value())
            sentido_str = self.cbo_mcu_spin_dir.currentText()
            is_ccw = "CCW" in sentido_str or "Antihorario" in sentido_str
            is_cw = not is_ccw

            if t < 0.2:
                QMessageBox.warning(
                    self,
                    "Tiempo Insuficiente",
                    f"El tiempo de giro ({t:.2f} s) debe ser mayor o igual a 0.2 s para garantizar la maniobra."
                )
                return

            v_wheel = omega * (ANCHO_VIA_M / 2.0)
            if is_cw:
                v_l = +v_wheel
                v_r = -v_wheel
            else:  # Antihorario (CCW)
                v_l = -v_wheel
                v_r = +v_wheel

            max_v = max(abs(v_l), abs(v_r))
            if max_v > 1.20:
                QMessageBox.warning(
                    self,
                    "Velocidad de Rueda Excesiva",
                    f"La velocidad tangencial de rueda calculada ({max_v:.2f} m/s) "
                    f"excede el límite físico seguro del robot (1.20 m/s).\n"
                    f"Por favor reduce la velocidad angular ω (actual: {omega:.2f} rad/s)."
                )
                return

            self._limpiar_graficas_mcu()
            dir_label = "Horario CW" if is_cw else "Antihorario CCW"
            self.app_state.start_motion(f"Giro Propio Eje ({dir_label}, ω={omega:.2f} rad/s, θ={ang_deg:.1f}°, t={t:.1f}s)", profile_type="MCU")
            self.app_state.client.send_mobile_mcu(v_l, v_r, t)

        else:  # "Orbitar"
            r = float(self.spn_mcu_orb_r.value())
            v = float(self.spn_mcu_orb_v.value())
            omega = float(self.spn_mcu_orb_omega.value())
            t = float(self.spn_mcu_orb_t.value())
            n_turns = float(self.spn_mcu_orb_n.value())
            sentido_str = self.cbo_mcu_orb_dir.currentText()
            is_ccw = "CCW" in sentido_str or "Antihorario" in sentido_str
            is_cw = not is_ccw
            init_y = +r if is_cw else -r

            if t < 0.2:
                QMessageBox.warning(
                    self,
                    "Tiempo Insuficiente",
                    f"El tiempo de duración ({t:.2f} s) debe ser mayor o igual a 0.2 s para garantizar la maniobra."
                )
                return

            delta_v = (omega * ANCHO_VIA_M) / 2.0
            if is_cw:
                v_l = v + delta_v
                v_r = v - delta_v
            else:  # Antihorario (CCW)
                v_l = v - delta_v
                v_r = v + delta_v

            max_v = max(abs(v_l), abs(v_r))
            if max_v > 1.20:
                QMessageBox.warning(
                    self,
                    "Velocidad de Rueda Excesiva",
                    f"Las velocidades de rueda resultantes (Izq: {v_l:.2f} m/s, Der: {v_r:.2f} m/s) "
                    f"exceden el límite físico seguro del robot (1.20 m/s).\n"
                    f"Por favor reduce la velocidad o incrementa el radio de órbita R."
                )
                return

            self._limpiar_graficas_mcu()
            dir_label = "Horario CW" if is_cw else "Antihorario CCW"
            self.app_state.start_motion(
                f"Orbitar ({dir_label}, R={r:.2f}m, v={v:.2f}m/s, ω={omega:.2f}rad/s, N={n_turns:.2f}, t={t:.1f}s)",
                profile_type="MCU",
                initial_pos=(0.0, init_y)
            )
            self.app_state.client.send_mobile_mcu(v_l, v_r, t)

    def _guardar_perfil_mcu(self):
        modo_idx = self.cbo_mcu_mode.currentIndex()
        if modo_idx == 0:  # Orbitar
            r = float(self.spn_mcu_orb_r.value())
            v = float(self.spn_mcu_orb_v.value())
            omega = float(self.spn_mcu_orb_omega.value())
            t = float(self.spn_mcu_orb_t.value())
            sentido = "CW" if self.cbo_mcu_orb_dir.currentIndex() == 0 else "CCW"
            delta_v = (omega * ANCHO_VIA_M) / 2.0
            vl = v + delta_v if sentido == "CW" else v - delta_v
            vr = v - delta_v if sentido == "CW" else v + delta_v
            params = {
                "submode": "orbit", "r": r, "v": v, "omega": omega, "dur": t,
                "dir": sentido, "v_l": vl, "v_r": vr
            }
            def_name = f"Órbita R={r:.2f}m ({sentido})"
            m_type = "MCU_ORBIT"
        else:  # Giro Propio Eje
            omega = float(self.spn_mcu_spin_omega.value())
            t = float(self.spn_mcu_spin_t.value())
            ang_deg = float(self.spn_mcu_spin_ang.value())
            sentido = "CW" if self.cbo_mcu_spin_dir.currentIndex() == 0 else "CCW"
            v_wheel = omega * (ANCHO_VIA_M / 2.0)
            vl = +v_wheel if sentido == "CW" else -v_wheel
            vr = -v_wheel if sentido == "CW" else +v_wheel
            params = {
                "submode": "spin", "omega": omega, "dur": t, "ang_deg": ang_deg,
                "dir": sentido, "v_l": vl, "v_r": vr
            }
            def_name = f"Giro Propio Eje {ang_deg:.0f}° ({sentido})"
            m_type = "MCU_SPIN"

        modal = ProfileSaveModal(
            app_state=self.app_state,
            motion_type=m_type,
            params=params,
            default_name=def_name,
            parent=self
        )
        modal.exec()

    def _ejecutar_trazo_en_robot(self):
        # Si ya está en ejecución, este mismo botón actúa como detención inmediata
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()
            return

        if not self.app_state.dongle_connected:
            QMessageBox.warning(self, "Dongle Desconectado", "Conecta primero el Dongle ESP8266 en la barra superior.")
            return
        if self.last_canvas_data is None or len(self.last_canvas_data) == 0:
            QMessageBox.information(self, "Trazo Vacío", "Dibuja primero un trazo sobre el lienzo.")
            return

        self._free_t_arr = np.array(self.last_canvas_data[:, 0], dtype=float)
        self._free_x_arr = np.array(self.last_canvas_data[:, 1], dtype=float)
        self._free_v_arr = np.array(self.last_canvas_data[:, 2], dtype=float)
        self._free_dur = float(self._free_t_arr[-1])

        if self._free_dur < 0.2:
            QMessageBox.warning(self, "Duración Insuficiente", "El trazo debe tener al menos 0.2 s de duración.")
            return

        # Si el usuario dibujó x(t), la posición de inicio teórica es x_arr[0]
        init_x = float(self._free_x_arr[0]) if getattr(self.canvas_widget, 'draw_mode', '') == "x(t)" else 0.0

        self.curve_free_x_real.setData([], [])
        self.curve_free_v_real.setData([], [])

        self.app_state.start_motion(f"Movimiento Libre (t={self._free_dur:.1f}s)", profile_type="FREE", initial_x=init_x)
        self._free_start_time = time.time()

        self.btn_execute_free.setText("⏹ Detener Trazo")
        self.btn_execute_free.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #ef4444; color: white; }
        """)

        # Iniciar streaming continuo en lazo de control a 20 Hz (50 ms)
        self.free_motion_timer.start(50)
        self._on_free_motion_tick()

    def _on_free_motion_tick(self):
        t_rel = time.time() - self._free_start_time
        if t_rel >= self._free_dur:
            self._detener_trazo_en_robot()
            return

        # Interpolar la velocidad requerida en el instante actual de la curva dibujada
        v_target = float(np.interp(t_rel, self._free_t_arr, self._free_v_arr))
        # Limitar a la velocidad segura alcanzable por el robot (0.0 a 1.10 m/s)
        v_target = max(0.0, min(1.10, v_target))
        rpm_target = v_target * MS_TO_RPM

        # Enviar consigna de velocidad dinámica en modo 4 (Control directo RPM)
        self.app_state.client.send_mobile_rpm(rpm_target, rpm_target, dur=1.0)

    def _detener_trazo_en_robot(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self.free_motion_timer.stop()
        self.app_state.client.send_mobile_stop()
        self.app_state.stop_motion()
        self.btn_execute_free.setText("▶ Ejecutar Trazo en Robot")
        self.btn_execute_free.setStyleSheet("""
            QPushButton {
                background-color: #0284c7; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #38bdf8; color: black; }
        """)

    def _paro_emergencia(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()
        self.app_state.client.send_mobile_stop()
        self.app_state.stop_motion()
        self.lbl_telemetry_status.setText("Estado: PARO DE EMERGENCIA")
        self.lbl_telemetry_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #ef4444; background: #161b22; padding: 6px 12px; border-radius: 6px; border: 1px solid #ef4444;")

    # =========================================================================
    # ACTUALIZACIÓN EN TIEMPO REAL DE TELEMETRÍA Y GRÁFICAS
    # =========================================================================
    def _connect_signals(self):
        self.app_state.mobile_telemetry_updated.connect(self._on_mobile_telemetry)
        self.app_state.profile_point_added.connect(self._on_profile_point_added)
        self.app_state.language_changed.connect(self._retranslate_ui)
        self.app_state.theme_changed.connect(self._on_theme_changed)

    @Slot(dict)
    def _on_mobile_telemetry(self, d: dict):
        rpm_l = d.get("rpm_l", 0.0)
        rpm_r = d.get("rpm_r", 0.0)
        v_l = d.get("v_l", 0.0)
        v_r = d.get("v_r", 0.0)
        v_real = d.get("v_real", 0.0)
        mode = d.get("mode", 0)
        prog = d.get("prog", 0)

        self.lbl_wheels_rpm.setText(f"Izq: {rpm_l:5.1f} RPM ({v_l:4.2f} m/s) | Der: {rpm_r:5.1f} RPM ({v_r:4.2f} m/s)")
        self.prog_bar.setValue(prog)

        modos_dict = {
            0: ("Estado: EN REPOSO (IDLE)", "#fbbf24"),
            1: ("Estado: EJECUTANDO MRU", "#10b981"),
            2: ("Estado: EJECUTANDO MRUV", "#38bdf8"),
            3: ("Estado: EJECUTANDO MCU", "#c084fc"),
            4: ("Estado: CONTROL MANUAL", "#fbbf24"),
            5: ("⚠️ FRENO POR COLISIÓN PERIMETRAL", "#ef4444")
        }
        txt, col = modos_dict.get(mode, ("Estado: ACTIVO", "#fbbf24"))
        self.lbl_telemetry_status.setText(txt)
        self.lbl_telemetry_status.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {col}; background: #161b22; padding: 6px 12px; border-radius: 6px; border: 1px solid #30363d;")

        # Actualizar labels de resultados en vivo
        if self.app_state.profile_active:
            x_act = self.app_state.integrated_x
            self.lbl_mru_res_val.setText(f"v_medida = {v_real:.2f} m/s\nx_real = {x_act:.2f} m")
            a_act = self.app_state.buf_a[-1] if self.app_state.buf_a else 0.0
            self.lbl_mruv_res_val.setText(f"a_real = {a_act:.3f} m/s²\nv_inst = {v_real:.2f} m/s")

            omega = (v_r - v_l) / ANCHO_VIA_M
            modo_mcu = self.cbo_mcu_mode.currentText() if hasattr(self, 'cbo_mcu_mode') else "Orbitar"
            if modo_mcu == "Giro sobre su propio eje":
                theta_deg = math.degrees(self.app_state.current_theta)
                self.lbl_mcu_res_val.setText(f"ω_real = {omega:.2f} rad/s\nθ_acum = {theta_deg:.1f}°")
            else:
                r_orb = max(0.05, float(self.spn_mcu_orb_r.value())) if hasattr(self, 'spn_mcu_orb_r') else 0.40
                ac = (v_real * v_real) / r_orb
                self.lbl_mcu_res_val.setText(f"ω_real = {omega:.2f} rad/s\na_c = {ac:.2f} m/s²")

    @Slot(float, float, float, float)
    def _on_profile_point_added(self, t: float, x: float, v: float, a: float):
        cur_tab = self.sub_tabs.currentIndex()

        # 1. Gráficas MRU
        if self.app_state.profile_type == "MRU" or cur_tab == 0:
            self._render_live_mru_plot()
            row = self.tbl_mru_data.rowCount()
            if row < 200: # Limitar filas de tabla para fluidez
                self.tbl_mru_data.insertRow(row)
                rpm_avg = (self.app_state.rpm_l + self.app_state.rpm_r) / 2.0
                for c, val_str in enumerate([f"{t:.2f}", f"{x:.3f}", f"{v:.3f}", f"{a:.3f}", f"{rpm_avg:.1f}"]):
                    self.tbl_mru_data.setItem(row, c, QTableWidgetItem(val_str))
                self.tbl_mru_data.scrollToBottom()

        # 2. Gráficas MRUV
        elif self.app_state.profile_type == "MRUV" or cur_tab == 1:
            self._render_live_mruv_plot()
            row = self.tbl_mruv_data.rowCount()
            if row < 200:
                self.tbl_mruv_data.insertRow(row)
                rpm_avg = (self.app_state.rpm_l + self.app_state.rpm_r) / 2.0
                for c, val_str in enumerate([f"{t:.2f}", f"{x:.3f}", f"{v:.3f}", f"{a:.3f}", f"{rpm_avg:.1f}"]):
                    self.tbl_mruv_data.setItem(row, c, QTableWidgetItem(val_str))
                self.tbl_mruv_data.scrollToBottom()

        # 3. Gráficas MCU
        elif self.app_state.profile_type == "MCU" or cur_tab == 2:
            self._render_live_mcu_plot()
            row = self.tbl_mcu_data.rowCount()
            if row < 200:
                self.tbl_mcu_data.insertRow(row)
                omega = (self.app_state.v_r - self.app_state.v_l) / ANCHO_VIA_M
                modo_mcu = self.cbo_mcu_mode.currentText() if hasattr(self, 'cbo_mcu_mode') else "Orbitar"
                if modo_mcu == "Giro sobre su propio eje":
                    pos_x = 0.0
                    pos_y = 0.0
                    ac = 0.0
                else:
                    pos_x = self.app_state.current_pos_x
                    pos_y = self.app_state.current_pos_y
                    r_orb = max(0.05, float(self.spn_mcu_orb_r.value())) if hasattr(self, 'spn_mcu_orb_r') else 0.40
                    ac = (v * v) / r_orb
                for c, val_str in enumerate([f"{t:.2f}", f"{pos_x:.3f}", f"{pos_y:.3f}", f"{omega:.2f}", f"{ac:.2f}"]):
                    self.tbl_mcu_data.setItem(row, c, QTableWidgetItem(val_str))
                self.tbl_mcu_data.scrollToBottom()

        # 4. Gráficas Movimiento Libre (Trazo vs Medición Real en Vivo)
        elif self.app_state.profile_type == "FREE" or cur_tab == 3:
            t_buf = np.array(self.app_state.buf_t)
            x_buf = np.array(self.app_state.buf_x)
            v_buf = np.array(self.app_state.buf_v)
            if len(t_buf) > 0:
                self.curve_free_x_real.setData(t_buf, x_buf)
                self.curve_free_v_real.setData(t_buf, v_buf)

    # =========================================================================
    # RENDERIZADO DE GRÁFICAS (TEÓRICO VS REAL)
    # =========================================================================
    def _render_live_mru_plot(self):
        t_arr = np.array(self.app_state.buf_t)
        x_arr = np.array(self.app_state.buf_x)
        v_arr = np.array(self.app_state.buf_v)

        if len(t_arr) == 0:
            return

        v_theor = float(self.spn_mru_v.value())
        x_theor = v_theor * t_arr
        v_theor_arr = np.full_like(t_arr, v_theor)

        pen_real = pg.mkPen(color='#00f0ff', width=3)
        pen_theor = pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine)

        if self.mru_view_mode == "xt":
            self.pw_mru_single.clear()
            self.pw_mru_single.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mru_single.setLabel('left', 'Posición x (m)', units='m')
            self.pw_mru_single.plot(t_arr, x_theor, pen=pen_theor, name="Teórico x(t)")
            self.pw_mru_single.plot(t_arr, x_arr, pen=pen_real, name="Medido Real x(t)")
            if self.btn_mru_roi.isChecked():
                self.pw_mru_single.addItem(self.mru_roi)

        elif self.mru_view_mode == "vt":
            self.pw_mru_single.clear()
            self.pw_mru_single.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mru_single.setLabel('left', 'Velocidad v (m/s)', units='m/s')
            self.pw_mru_single.plot(t_arr, v_theor_arr, pen=pen_theor, name="Teórico v(t)")
            self.pw_mru_single.plot(t_arr, v_arr, pen=pg.mkPen(color='#10b981', width=3), name="Medido Real v(t)")
            if self.btn_mru_roi.isChecked():
                self.pw_mru_single.addItem(self.mru_roi)

        else: # simultáneo
            self.pw_mru_sim1.clear()
            self.pw_mru_sim2.clear()
            self.pw_mru_sim1.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mru_sim1.setLabel('left', 'Posición x (m)', units='m')
            self.pw_mru_sim2.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mru_sim2.setLabel('left', 'Velocidad v (m/s)', units='m/s')
            self.pw_mru_sim1.plot(t_arr, x_theor, pen=pen_theor, name="Teórico")
            self.pw_mru_sim1.plot(t_arr, x_arr, pen=pen_real, name="Medido")
            self.pw_mru_sim2.plot(t_arr, v_theor_arr, pen=pen_theor, name="Teórico")
            self.pw_mru_sim2.plot(t_arr, v_arr, pen=pg.mkPen(color='#10b981', width=2), name="Medido")

    def _render_live_mruv_plot(self):
        t_arr = np.array(self.app_state.buf_t)
        x_arr = np.array(self.app_state.buf_x)
        v_arr = np.array(self.app_state.buf_v)
        a_arr = np.array(self.app_state.buf_a)

        if len(t_arr) == 0:
            return

        v0 = float(self.spn_mruv_v0.value())
        vf = float(self.spn_mruv_vf.value())
        a_theor = float(self.spn_mruv_a.value())
        t_dur = max(0.5, float(self.spn_mruv_t.value()))

        x_theor = v0 * t_arr + 0.5 * a_theor * (t_arr ** 2)
        v_theor = v0 + a_theor * t_arr

        pen_theor = pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine)

        if self.mruv_view_mode == "xt":
            self.pw_mruv_single.clear()
            self.pw_mruv_single.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mruv_single.setLabel('left', 'Posición x (m)', units='m')
            self.pw_mruv_single.plot(t_arr, x_theor, pen=pen_theor, name="Teórico x(t)")
            self.pw_mruv_single.plot(t_arr, x_arr, pen=pg.mkPen(color='#00f0ff', width=3), name="Medido x(t)")
            if self.btn_mruv_roi.isChecked():
                self.pw_mruv_single.addItem(self.mruv_roi)

        elif self.mruv_view_mode == "vt":
            self.pw_mruv_single.clear()
            self.pw_mruv_single.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mruv_single.setLabel('left', 'Velocidad v (m/s)', units='m/s')
            self.pw_mruv_single.plot(t_arr, v_theor, pen=pen_theor, name="Teórico v(t)")
            self.pw_mruv_single.plot(t_arr, v_arr, pen=pg.mkPen(color='#10b981', width=3), name="Medido v(t)")
            if self.btn_mruv_roi.isChecked():
                self.pw_mruv_single.addItem(self.mruv_roi)

        elif self.mruv_view_mode == "at":
            self.pw_mruv_single.clear()
            self.pw_mruv_single.setLabel('bottom', 'Tiempo t (s)', units='s')
            self.pw_mruv_single.setLabel('left', 'Aceleración a (m/s²)', units='m/s²')
            self.pw_mruv_single.plot(t_arr, np.full_like(t_arr, a_theor), pen=pen_theor, name="Teórico a(t)")
            self.pw_mruv_single.plot(t_arr, a_arr, pen=pg.mkPen(color='#a855f7', width=3), name="Medido a(t)")
            if self.btn_mruv_roi.isChecked():
                self.pw_mruv_single.addItem(self.mruv_roi)

        else: # simultáneo
            self.pw_mruv_sim1.clear()
            self.pw_mruv_sim2.clear()
            self.pw_mruv_sim3.clear()
            self.pw_mruv_sim1.plot(t_arr, x_theor, pen=pen_theor, name="Teórico")
            self.pw_mruv_sim1.plot(t_arr, x_arr, pen=pg.mkPen(color='#00f0ff', width=2), name="Medido")
            self.pw_mruv_sim2.plot(t_arr, v_theor, pen=pen_theor, name="Teórico")
            self.pw_mruv_sim2.plot(t_arr, v_arr, pen=pg.mkPen(color='#10b981', width=2), name="Medido")
            self.pw_mruv_sim3.plot(t_arr, np.full_like(t_arr, a_theor), pen=pen_theor, name="Teórico")
            self.pw_mruv_sim3.plot(t_arr, a_arr, pen=pg.mkPen(color='#a855f7', width=2), name="Medido")

    def _render_live_mcu_plot(self):
        modo_mcu = self.cbo_mcu_mode.currentText() if hasattr(self, 'cbo_mcu_mode') else "Orbitar"
        if modo_mcu == "Giro sobre su propio eje":
            # REQUERIMIENTO EXPLÍCITO: NO SE DEBE GRAFICAR EN ESTE MODO
            ang_deg = math.degrees(self.app_state.current_theta)
            omega_inst = (self.app_state.v_r - self.app_state.v_l) / ANCHO_VIA_M
            if hasattr(self, 'lbl_mcu_spin_live_info'):
                self.lbl_mcu_spin_live_info.setText(f"Ángulo acumulado en vivo: {ang_deg:.1f}° | ω: {omega_inst:.2f} rad/s")
            return

        traj_x = np.array(self.app_state.buf_traj_x)
        traj_y = np.array(self.app_state.buf_traj_y)

        self.pw_mcu.clear()

        # Dibujar órbita circular teórica si estamos en modo Orbitar
        r = float(self.spn_mcu_orb_r.value()) if hasattr(self, 'spn_mcu_orb_r') else float(self.spn_mcu_r.value())
        if r > 0.02:
            theta_pts = np.linspace(0, 2 * math.pi, 100)
            x_circle = r * np.cos(theta_pts)
            y_circle = r * np.sin(theta_pts)
            self.pw_mcu.plot(x_circle, y_circle, pen=pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine), name="Órbita Teórica")

        # Dibujar trayectoria medida por odometría diferencial
        if len(traj_x) > 0:
            self.pw_mcu.plot(traj_x, traj_y, pen=pg.mkPen(color='#c084fc', width=3), name="Trayectoria Real Medida")
            # Punto de posición actual del robot
            self.pw_mcu.plot([traj_x[-1]], [traj_y[-1]], pen=None, symbol='o', symbolSize=10, symbolBrush=pg.mkBrush('#00f0ff'), name="Posición Robot")
        elif r > 0.02:
            sentido_str = self.cbo_mcu_orb_dir.currentText() if hasattr(self, 'cbo_mcu_orb_dir') else "Horario (CW)"
            is_cw = not ("CCW" in sentido_str or "Antihorario" in sentido_str)
            init_y = +r if is_cw else -r
            self.pw_mcu.plot([0.0], [init_y], pen=None, symbol='o', symbolSize=10, symbolBrush=pg.mkBrush('#00f0ff'), name="Posición Robot (Inicio)")

    # =========================================================================
    # AJUSTES DE CURVA Y REGRESIÓN MATEMÁTICA (ROI / RECUADRO)
    # =========================================================================
    def _toggle_mru_roi(self, checked: bool):
        if checked:
            self.pw_mru_single.addItem(self.mru_roi)
        else:
            self.pw_mru_single.removeItem(self.mru_roi)
        self._recalc_mru_fit()

    def _recalc_mru_fit(self):
        if len(self.app_state.buf_t) < 3:
            return
        t_arr = np.array(self.app_state.buf_t)
        x_arr = np.array(self.app_state.buf_x)

        if self.btn_mru_roi.isChecked():
            min_t, max_t = self.mru_roi.getRegion()
            mask = (t_arr >= min_t) & (t_arr <= max_t)
            if np.count_nonzero(mask) < 3:
                return
            t_fit = t_arr[mask]
            x_fit = x_arr[mask]
        else:
            t_fit = t_arr
            x_fit = x_arr

        mode = self.cbo_mru_fit.currentIndex()
        if mode == 1: # Lineal
            m, b = np.polyfit(t_fit, x_fit, 1)
            pred = m * t_fit + b
            ss_tot = np.sum((x_fit - np.mean(x_fit)) ** 2)
            ss_res = np.sum((x_fit - pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            self.lbl_mru_fit.setText(f"Ajuste Lineal Medido: x(t) = {m:.3f}·t + ({b:.3f}) | v_exp = {m:.3f} m/s | R² = {r2:.4f}")
            self.pw_mru_single.plot(t_fit, pred, pen=pg.mkPen(color='#f59e0b', width=2, style=Qt.DotLine), name="Regresión Lineal")
        elif mode == 2: # Cuadrático
            a2, a1, a0 = np.polyfit(t_fit, x_fit, 2)
            pred = a2 * (t_fit ** 2) + a1 * t_fit + a0
            ss_tot = np.sum((x_fit - np.mean(x_fit)) ** 2)
            ss_res = np.sum((x_fit - pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            self.lbl_mru_fit.setText(f"Ajuste Cuadrático: x(t) = {a2:.3f}·t² + {a1:.3f}·t + ({a0:.3f}) | R² = {r2:.4f}")
            self.pw_mru_single.plot(t_fit, pred, pen=pg.mkPen(color='#f59e0b', width=2, style=Qt.DotLine), name="Regresión Cuadrática")
        else:
            self.lbl_mru_fit.setText("Ajuste Experimental: Ninguno")

    def _toggle_mruv_roi(self, checked: bool):
        if checked:
            self.pw_mruv_single.addItem(self.mruv_roi)
        else:
            self.pw_mruv_single.removeItem(self.mruv_roi)
        self._recalc_mruv_fit()

    def _recalc_mruv_fit(self):
        if len(self.app_state.buf_t) < 3:
            return
        t_arr = np.array(self.app_state.buf_t)
        v_arr = np.array(self.app_state.buf_v)
        x_arr = np.array(self.app_state.buf_x)

        if self.btn_mruv_roi.isChecked():
            min_t, max_t = self.mruv_roi.getRegion()
            mask = (t_arr >= min_t) & (t_arr <= max_t)
            if np.count_nonzero(mask) < 3:
                return
            t_fit = t_arr[mask]
            v_fit = v_arr[mask]
            x_fit = x_arr[mask]
        else:
            t_fit = t_arr
            v_fit = v_arr
            x_fit = x_arr

        mode = self.cbo_mruv_fit.currentIndex()
        if mode == 1: # Cuadrático x(t)
            a2, a1, a0 = np.polyfit(t_fit, x_fit, 2)
            pred = a2 * (t_fit ** 2) + a1 * t_fit + a0
            ss_tot = np.sum((x_fit - np.mean(x_fit)) ** 2)
            ss_res = np.sum((x_fit - pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            a_exp = 2.0 * a2
            self.lbl_mruv_fit.setText(f"Ajuste Cuadrático x(t): x(t) = {a2:.3f}·t² + {a1:.3f}·t + ({a0:.3f}) | a_exp = {a_exp:.3f} m/s² | R² = {r2:.4f}")
            self.pw_mruv_single.plot(t_fit, pred, pen=pg.mkPen(color='#f59e0b', width=2, style=Qt.DotLine), name="Regresión Cuadrática")
        elif mode == 2: # Lineal en v(t)
            m, b = np.polyfit(t_fit, v_fit, 1)
            pred = m * t_fit + b
            ss_tot = np.sum((v_fit - np.mean(v_fit)) ** 2)
            ss_res = np.sum((v_fit - pred) ** 2)
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0
            self.lbl_mruv_fit.setText(f"Ajuste Aceleración: v(t) = {m:.3f}·t + ({b:.3f}) | a_exp = {m:.3f} m/s² | R² = {r2:.4f}")
            self.pw_mruv_single.plot(t_fit, pred, pen=pg.mkPen(color='#f59e0b', width=2, style=Qt.DotLine), name="Regresión v(t)")
        else:
            self.lbl_mruv_fit.setText("Ajuste Experimental: Ninguno | R² = 1.000")

    # =========================================================================
    # RECALCULO TEÓRICO INICIAL Y LIMPIEZA
    # =========================================================================
    def _update_mru_calc_var_mode(self):
        """
        Activa / desactiva los spinboxes según la variable seleccionada para calcular en MRU.
        La variable calculada se deshabilita para edición y adquiere un estilo visual resaltado.
        """
        if not hasattr(self, 'cbo_mru_calc_var') or not hasattr(self, 'spn_mru_v'):
            return

        calc_var = self.cbo_mru_calc_var.currentData()

        # Estilo para spinbox calculado (deshabilitado para edición manual pero destacado y legible)
        style_calc = """
            QDoubleSpinBox:disabled {
                background-color: rgba(2, 132, 199, 0.15);
                color: #38bdf8;
                border: 1.5px dashed #0284c7;
                font-weight: bold;
            }
        """

        is_calc_d = (calc_var == "d")
        is_calc_v = (calc_var == "v")
        is_calc_t = (calc_var == "t")

        self.spn_mru_d.setEnabled(not is_calc_d)
        self.spn_mru_d.setStyleSheet(style_calc if is_calc_d else "")
        self.spn_mru_d.setToolTip(
            "Variable calculada automáticamente (d = v · t)" if is_calc_d
            else "Distancia d (m) - Parámetro editable"
        )

        self.spn_mru_v.setEnabled(not is_calc_v)
        self.spn_mru_v.setStyleSheet(style_calc if is_calc_v else "")
        self.spn_mru_v.setToolTip(
            "Variable calculada automáticamente (v = d / t)" if is_calc_v
            else "Velocidad v (m/s) - Parámetro editable"
        )

        self.spn_mru_t.setEnabled(not is_calc_t)
        self.spn_mru_t.setStyleSheet(style_calc if is_calc_t else "")
        self.spn_mru_t.setToolTip(
            "Variable calculada automáticamente (t = d / v)" if is_calc_t
            else "Tiempo t (s) - Parámetro editable"
        )

        self._recalc_mru_theor()

    def _recalc_mru_theor(self):
        """
        Recalcula la variable seleccionada como calculada a partir de las otras dos
        y actualiza la visualización de la relación MRU teórica.
        """
        if not hasattr(self, 'cbo_mru_calc_var') or not hasattr(self, 'spn_mru_v'):
            return

        calc_var = self.cbo_mru_calc_var.currentData()

        if calc_var == "d":
            v = self.spn_mru_v.value()
            t = self.spn_mru_t.value()
            d = v * t
            d = max(0.05, min(36.00, d))
            self.spn_mru_d.blockSignals(True)
            self.spn_mru_d.setValue(d)
            self.spn_mru_d.blockSignals(False)

        elif calc_var == "v":
            d = self.spn_mru_d.value()
            t = self.spn_mru_t.value()
            v = (d / t) if t > 0 else 0.0
            v = max(0.05, min(1.20, v))
            self.spn_mru_v.blockSignals(True)
            self.spn_mru_v.setValue(v)
            self.spn_mru_v.blockSignals(False)

        elif calc_var == "t":
            d = self.spn_mru_d.value()
            v = self.spn_mru_v.value()
            t = (d / v) if v > 0 else 0.0
            t = max(0.5, min(30.0, t))
            self.spn_mru_t.blockSignals(True)
            self.spn_mru_t.setValue(t)
            self.spn_mru_t.blockSignals(False)

        v_val = self.spn_mru_v.value()
        d_val = self.spn_mru_d.value()
        t_val = self.spn_mru_t.value()

        if hasattr(self, 'lbl_mru_dist_theor'):
            self.lbl_mru_dist_theor.setText(
                f"MRU Teórico: v = {v_val:.2f} m/s | d = {d_val:.2f} m | t = {t_val:.1f} s"
            )

    def _on_mruv_check_toggled(self, checked: bool = False):
        """
        Gestiona la selección de variables en MRUV:
        - Exactamente 3 variables marcadas son las editables.
        - Las 2 no marcadas son las calculadas (spinbox deshabilitado con estilo #21262d / #38bdf8).
        - Si hay 3 marcadas, se deshabilitan los checkboxes no seleccionados para impedir marcar una 4ta.
        """
        if not hasattr(self, 'mruv_checks') or not hasattr(self, 'mruv_spins'):
            return

        selected_keys = [k for k, chk in self.mruv_checks.items() if chk.isChecked()]
        num_selected = len(selected_keys)

        style_calc = """
            QDoubleSpinBox:disabled {
                background-color: #21262d;
                color: #38bdf8;
                border: 1.5px solid #38bdf8;
                border-radius: 4px;
                font-weight: bold;
            }
        """

        if num_selected == 3:
            for k, chk in self.mruv_checks.items():
                spn = self.mruv_spins[k]
                if chk.isChecked():
                    chk.setEnabled(True)
                    spn.setEnabled(True)
                    spn.setStyleSheet("")
                else:
                    chk.setEnabled(False)  # Impedir marcar una 4ta variable
                    spn.setEnabled(False)
                    spn.setStyleSheet(style_calc)

            self.lbl_mruv_status.setText("✓ 3 de 3 variables seleccionadas. Desmarca una para elegir otra.")
            self.lbl_mruv_status.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
            self.btn_ejecutar_mruv.setEnabled(True)
            self._recalc_mruv_theor()

        elif num_selected < 3:
            for k, chk in self.mruv_checks.items():
                chk.setEnabled(True)
                spn = self.mruv_spins[k]
                if chk.isChecked():
                    spn.setEnabled(True)
                    spn.setStyleSheet("")
                else:
                    spn.setEnabled(False)
                    spn.setStyleSheet(style_calc)
                    spn.setToolTip("Variable calculada (selecciona 3 variables para calcular)")

            self.lbl_mruv_status.setText(f"⚠️ Selecciona 3 variables conocidas ({num_selected} de 3 seleccionadas).")
            self.lbl_mruv_status.setStyleSheet("color: #fbbf24; font-size: 11px; font-weight: bold;")
            self.btn_ejecutar_mruv.setEnabled(False)

        else: # Si se intentaran marcar más de 3
            for k in selected_keys[3:]:
                self.mruv_checks[k].setChecked(False)

    def _recalc_mruv_theor(self):
        """
        Calcula las 2 variables incógnitas a partir de las 3 variables seleccionadas en MRUV.
        Soporta analíticamente las 10 combinaciones posibles de {v0, vf, a, d, t}.
        """
        if not hasattr(self, 'mruv_checks') or not hasattr(self, 'mruv_spins'):
            return

        selected_keys = set(k for k, chk in self.mruv_checks.items() if chk.isChecked())
        if len(selected_keys) != 3:
            return

        # Leer valores actuales de los spinboxes
        v0 = float(self.spn_mruv_v0.value())
        vf = float(self.spn_mruv_vf.value())
        a  = float(self.spn_mruv_a.value())
        d  = float(self.spn_mruv_d.value())
        t  = float(self.spn_mruv_t.value())

        tooltips = {}

        # 1. {v0, vf, t} -> calcular a, d
        if selected_keys == {"v0", "vf", "t"}:
            t_safe = max(0.5, t)
            a = (vf - v0) / t_safe
            d = ((v0 + vf) / 2.0) * t_safe
            tooltips["a"] = "Variable calculada: a = (vf - v₀) / t"
            tooltips["d"] = "Variable calculada: d = ((v₀ + vf) / 2) · t"

        # 2. {v0, a, t} -> calcular vf, d
        elif selected_keys == {"v0", "a", "t"}:
            vf = v0 + a * t
            d = v0 * t + 0.5 * a * (t ** 2)
            tooltips["vf"] = "Variable calculada: vf = v₀ + a · t"
            tooltips["d"] = "Variable calculada: d = v₀ · t + ½ · a · t²"

        # 3. {v0, d, t} -> calcular vf, a
        elif selected_keys == {"v0", "d", "t"}:
            t_safe = max(0.5, t)
            vf = (2.0 * d / t_safe) - v0
            a = (vf - v0) / t_safe
            tooltips["vf"] = "Variable calculada: vf = (2·d / t) - v₀"
            tooltips["a"] = "Variable calculada: a = (vf - v₀) / t"

        # 4. {v0, vf, a} -> calcular t, d
        elif selected_keys == {"v0", "vf", "a"}:
            if abs(a) > 1e-4:
                t = abs((vf - v0) / a)
                d = abs((vf ** 2 - v0 ** 2) / (2.0 * a))
            else:
                t = max(0.5, self.spn_mruv_t.value())
                d = v0 * t
            tooltips["t"] = "Variable calculada: t = |vf - v₀| / |a|"
            tooltips["d"] = "Variable calculada: d = (vf² - v₀²) / (2·a)"

        # 5. {v0, vf, d} -> calcular t, a
        elif selected_keys == {"v0", "vf", "d"}:
            sum_v = v0 + vf
            t = (2.0 * d / sum_v) if sum_v > 1e-4 else 5.0
            a = ((vf ** 2 - v0 ** 2) / (2.0 * d)) if d > 1e-4 else 0.0
            tooltips["t"] = "Variable calculada: t = 2·d / (v₀ + vf)"
            tooltips["a"] = "Variable calculada: a = (vf² - v₀²) / (2·d)"

        # 6. {v0, a, d} -> calcular vf, t
        elif selected_keys == {"v0", "a", "d"}:
            rad = max(0.0, (v0 ** 2) + 2.0 * a * d)
            vf = math.sqrt(rad)
            if abs(a) > 1e-4:
                t = abs((vf - v0) / a)
            else:
                t = (d / v0) if v0 > 1e-4 else 5.0
            tooltips["vf"] = "Variable calculada: vf = √(v₀² + 2·a·d)"
            tooltips["t"] = "Variable calculada: t = (vf - v₀) / a"

        # 7. {vf, a, t} -> calcular v0, d
        elif selected_keys == {"vf", "a", "t"}:
            v0 = vf - a * t
            d = vf * t - 0.5 * a * (t ** 2)
            tooltips["v0"] = "Variable calculada: v₀ = vf - a · t"
            tooltips["d"] = "Variable calculada: d = vf · t - ½ · a · t²"

        # 8. {vf, d, t} -> calcular v0, a
        elif selected_keys == {"vf", "d", "t"}:
            t_safe = max(0.5, t)
            v0 = (2.0 * d / t_safe) - vf
            a = (vf - v0) / t_safe
            tooltips["v0"] = "Variable calculada: v₀ = (2·d / t) - vf"
            tooltips["a"] = "Variable calculada: a = (vf - v₀) / t"

        # 9. {vf, a, d} -> calcular v0, t
        elif selected_keys == {"vf", "a", "d"}:
            rad = max(0.0, (vf ** 2) - 2.0 * a * d)
            v0 = math.sqrt(rad)
            if abs(a) > 1e-4:
                t = abs((vf - v0) / a)
            else:
                t = (d / vf) if vf > 1e-4 else 5.0
            tooltips["v0"] = "Variable calculada: v₀ = √(vf² - 2·a·d)"
            tooltips["t"] = "Variable calculada: t = (vf - v₀) / a"

        # 10. {a, d, t} -> calcular v0, vf
        elif selected_keys == {"a", "d", "t"}:
            t_safe = max(0.5, t)
            v0 = (d - 0.5 * a * (t_safe ** 2)) / t_safe
            vf = v0 + a * t_safe
            tooltips["v0"] = "Variable calculada: v₀ = (d - ½·a·t²) / t"
            tooltips["vf"] = "Variable calculada: vf = v₀ + a · t"

        # Clamping físico para spinboxes
        v0_clamped = max(0.00, min(1.20, v0))
        vf_clamped = max(0.00, min(1.20, vf))
        a_clamped  = max(-2.00, min(2.00, a))
        d_clamped  = max(0.05, min(36.00, d))
        t_clamped  = max(0.5, min(30.0, t))

        # Actualizar los 2 spinboxes calculados sin disparar señales
        calc_vars = {"v0", "vf", "a", "d", "t"} - selected_keys
        vals_map = {
            "v0": (self.spn_mruv_v0, v0_clamped),
            "vf": (self.spn_mruv_vf, vf_clamped),
            "a":  (self.spn_mruv_a,  a_clamped),
            "d":  (self.spn_mruv_d,  d_clamped),
            "t":  (self.spn_mruv_t,  t_clamped),
        }

        for var_key in calc_vars:
            spn, val = vals_map[var_key]
            spn.blockSignals(True)
            spn.setValue(val)
            spn.blockSignals(False)
            if var_key in tooltips:
                spn.setToolTip(tooltips[var_key])

        # Actualizar label informativo con todos los valores finales
        v0_disp = self.spn_mruv_v0.value()
        vf_disp = self.spn_mruv_vf.value()
        a_disp  = self.spn_mruv_a.value()
        d_disp  = self.spn_mruv_d.value()
        t_disp  = self.spn_mruv_t.value()

        if hasattr(self, 'lbl_mruv_theor_info'):
            self.lbl_mruv_theor_info.setText(
                f"MRUV Teórico: v₀ = {v0_disp:.2f} m/s | vf = {vf_disp:.2f} m/s | "
                f"a = {a_disp:.3f} m/s² | d = {d_disp:.2f} m | t = {t_disp:.1f} s"
            )

    def _limpiar_graficas_mru(self):
        self.pw_mru_single.clear()
        self.pw_mru_sim1.clear()
        self.pw_mru_sim2.clear()
        self.tbl_mru_data.setRowCount(0)

    def _limpiar_graficas_mruv(self):
        self.pw_mruv_single.clear()
        self.pw_mruv_sim1.clear()
        self.pw_mruv_sim2.clear()
        self.pw_mruv_sim3.clear()
        self.tbl_mruv_data.setRowCount(0)

    def _limpiar_graficas_mcu(self):
        self.pw_mcu.clear()
        self.tbl_mcu_data.setRowCount(0)
        if hasattr(self, 'lbl_mcu_spin_live_info'):
            self.lbl_mcu_spin_live_info.setText("Ángulo acumulado en vivo: 0.0° | ω: 0.00 rad/s")
        if hasattr(self, 'cbo_mcu_mode') and self.cbo_mcu_mode.currentText() == "Orbitar":
            r = float(self.spn_mcu_orb_r.value()) if hasattr(self, 'spn_mcu_orb_r') else float(self.spn_mcu_r.value())
            if r > 0.02:
                theta_pts = np.linspace(0, 2 * math.pi, 100)
                x_circle = r * np.cos(theta_pts)
                y_circle = r * np.sin(theta_pts)
                self.pw_mcu.plot(x_circle, y_circle, pen=pg.mkPen(color='#8b949e', width=2, style=Qt.DashLine), name="Órbita Teórica")
                sentido_str = self.cbo_mcu_orb_dir.currentText() if hasattr(self, 'cbo_mcu_orb_dir') else "Horario (CW)"
                is_cw = not ("CCW" in sentido_str or "Antihorario" in sentido_str)
                init_y = +r if is_cw else -r
                self.pw_mcu.plot([0.0], [init_y], pen=None, symbol='o', symbolSize=10, symbolBrush=pg.mkBrush('#00f0ff'), name="Posición Robot (Inicio)")

    def _set_mru_view_mode(self, mode: str):
        self.mru_view_mode = mode
        if mode == "sim":
            self.mru_stack_layout.setCurrentIndex(1)
        else:
            self.mru_stack_layout.setCurrentIndex(0)
        self._render_live_mru_plot()

    def _set_mruv_view_mode(self, mode: str):
        self.mruv_view_mode = mode
        if mode == "sim":
            self.mruv_stack_layout.setCurrentIndex(1)
        else:
            self.mruv_stack_layout.setCurrentIndex(0)
        self._render_live_mruv_plot()

    # =========================================================================
    # DIBUJO A MANO
    # =========================================================================
    def _on_draw_mode_changed(self):
        mode = "x(t)" if self.rb_draw_x.isChecked() else "v(t)" if self.rb_draw_v.isChecked() else "a(t)"
        self.canvas_widget.set_draw_mode(mode)

    def _on_free_t_max_changed(self, val: float):
        self.canvas_widget.set_t_max(val)

    def _on_clear_canvas(self):
        if hasattr(self, 'free_motion_timer') and self.free_motion_timer.isActive():
            self._detener_trazo_en_robot()
        self.canvas_widget.clear_canvas()
        self.curve_free_x_theor.setData([], [])
        self.curve_free_x_real.setData([], [])
        self.curve_free_v_theor.setData([], [])
        self.curve_free_v_real.setData([], [])
        self.last_canvas_data = None

    def _on_canvas_points_updated(self, data_matrix: np.ndarray):
        self.last_canvas_data = data_matrix
        if data_matrix is None or data_matrix.shape[0] == 0:
            self.curve_free_x_theor.setData([], [])
            self.curve_free_v_theor.setData([], [])
            return
        t_arr = data_matrix[:, 0]
        x_arr = data_matrix[:, 1]
        v_arr = data_matrix[:, 2]

        self.curve_free_x_theor.setData(t_arr, x_arr)
        self.curve_free_v_theor.setData(t_arr, v_arr)

    # =========================================================================
    # EXPORTACIÓN CSV
    # =========================================================================
    def _download_table_csv(self, table: QTableWidget, default_name: str):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Datos de Cinemática", default_name, "Archivos CSV (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
                    f.write(",".join(headers) + "\n")
                    for r in range(table.rowCount()):
                        row_vals = [table.item(r, c).text() if table.item(r, c) else "" for c in range(table.columnCount())]
                        f.write(",".join(row_vals) + "\n")
                QMessageBox.information(self, "Exportación Exitosa", f"Archivo guardado exitosamente:\n{path}")
            except Exception as e:
                QMessageBox.showerror("Error al guardar CSV", f"No se pudo guardar el archivo:\n{e}")

    def _setup_plot_styles(self):
        self._on_theme_changed(self.app_state.theme_mode)

    def _on_theme_changed(self, mode: str):
        bg = '#0d1117' if mode == 'dark' else '#ffffff'
        fg = '#c9d1d9' if mode == 'dark' else '#1f2328'
        for pw in [self.pw_mru_single, self.pw_mru_sim1, self.pw_mru_sim2,
                   self.pw_mruv_single, self.pw_mruv_sim1, self.pw_mruv_sim2, self.pw_mruv_sim3,
                   self.pw_mcu, self.pw_free_x, self.pw_free_v]:
            pw.setBackground(bg)
            pw.getAxis('bottom').setPen(fg)
            pw.getAxis('left').setPen(fg)

        if hasattr(self, 'lbl_mcu_no_plot'):
            card_bg = '#161b22' if mode == 'dark' else '#f8fafc'
            card_fg = '#e2e8f0' if mode == 'dark' else '#1e293b'
            self.lbl_mcu_no_plot.setStyleSheet(f"""
                QLabel {{
                    font-size: 13px;
                    font-weight: bold;
                    color: {card_fg};
                    background-color: {card_bg};
                    border: 1.5px dashed #7c3aed;
                    border-radius: 8px;
                    padding: 20px;
                    line-height: 1.5;
                }}
            """)

    def _retranslate_ui(self, lang: str):
        self.sub_tabs.setTabText(0, tr("subtab_mru", lang))
        self.sub_tabs.setTabText(1, tr("subtab_mruv", lang))
        self.sub_tabs.setTabText(2, tr("subtab_mcu", lang))
        self.sub_tabs.setTabText(3, tr("subtab_free", lang))

        if hasattr(self, 'grp_mru'):
            self.grp_mru.setTitle(tr("grp_mru_title", lang))
        if hasattr(self, 'lbl_mru_calc_var'):
            self.lbl_mru_calc_var.setText(tr("lbl_mru_target", lang) if lang == "en" else "Variable a calcular:")
        if hasattr(self, 'cbo_mru_calc_var'):
            self.cbo_mru_calc_var.blockSignals(True)
            self.cbo_mru_calc_var.setItemText(0, f"{tr('opt_distance', lang)} (d)")
            self.cbo_mru_calc_var.setItemText(1, f"{tr('opt_velocity', lang)} (v)")
            self.cbo_mru_calc_var.setItemText(2, f"{tr('opt_time', lang)} (t)")
            self.cbo_mru_calc_var.blockSignals(False)
        if hasattr(self, 'grp_mru_res'):
            self.grp_mru_res.setTitle(tr("grp_calculated_results", lang))
        if hasattr(self, 'btn_mru_xt'):
            self.btn_mru_xt.setText(tr("plot_pos", lang))
            self.btn_mru_vt.setText(tr("plot_vel", lang))
            self.btn_mru_sim.setText(tr("plot_simultaneous", lang))
        self._recalc_mru_theor()

        if hasattr(self, 'grp_mruv'):
            self.grp_mruv.setTitle(tr("grp_mruv_title", lang))
        if hasattr(self, 'lbl_mruv_known'):
            self.lbl_mruv_known.setText(tr("lbl_mruv_known", lang))
        if hasattr(self, 'chk_mruv_v0'):
            self.chk_mruv_v0.setText(f"{tr('chk_v0', lang)}:")
            self.chk_mruv_vf.setText(f"{tr('chk_vf', lang)}:")
            self.chk_mruv_a.setText(f"{tr('chk_accel', lang)}:")
            self.chk_mruv_d.setText(f"{tr('chk_distance', lang)}:")
            self.chk_mruv_t.setText(f"{tr('chk_time', lang)}:")
        if hasattr(self, 'grp_mruv_res'):
            self.grp_mruv_res.setTitle(tr("grp_calculated_results", lang))
        if hasattr(self, 'btn_mruv_xt'):
            self.btn_mruv_xt.setText(tr("plot_pos", lang))
            self.btn_mruv_vt.setText(tr("plot_vel", lang))
            self.btn_mruv_at.setText(tr("plot_acc", lang))
            self.btn_mruv_sim.setText(tr("plot_simultaneous", lang))
        self._recalc_mruv_theor()

        if hasattr(self, 'grp_mcu'):
            self.grp_mcu.setTitle(tr("grp_mcu_title", lang))
        if hasattr(self, 'grp_mcu_res'):
            self.grp_mcu_res.setTitle(tr("grp_calculated_results", lang))
        self._recalc_mcu_theor()
