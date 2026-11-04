"""
Tab 1: Dashboard General for FiFu Lab Studio.
Full Spanish & English translation support, live connection status monitoring,
global execution control, sequential profile engine, multi-profile live graph
with time transition markers, profile queue manager, and data history table.
"""

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, Slot
from models.variables import AppState
from models.translations import tr
from components.modals import ModuleTestModal, SettingsModal


class DashboardTab(QWidget):
    """Pestaña 1: Dashboard General."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.seq_lines = []

        self._init_ui()
        self._connect_signals()
        self._refresh_history_table()
        self._refresh_profiles_table()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 12, 16, 12)

        lang = self.app_state.language

        # Barra Superior de Encabezado
        top_header = QHBoxLayout()
        self.lbl_dash_title = QLabel("Dashboard General — Panel de Control y Secuencia de Perfiles")
        self.lbl_dash_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")

        self.btn_settings = QPushButton(tr("btn_settings", lang))
        self.btn_settings.setStyleSheet("background-color: #1f6beb; color: white; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        self.btn_settings.clicked.connect(self._open_settings_modal)

        top_header.addWidget(self.lbl_dash_title)
        top_header.addStretch()
        top_header.addWidget(self.btn_settings)
        main_layout.addLayout(top_header)

        # Fila Superior: Tarjetas de Módulos + Gráfica General de Perfiles
        top_row = QHBoxLayout()
        top_row.setSpacing(14)

        # Grupo Izquierdo: Módulos Hardware Enlazados
        self.grp_general = QGroupBox("Módulos de Hardware Enlazados (ESP-NOW)")
        self.grp_general.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        l_general = QVBoxLayout(self.grp_general)
        l_general.setSpacing(10)

        self.card_lanzador = self._create_module_card(
            title="Unidad del Lanzador Parabólico",
            device_id="ESP32-S3 (ID 2)",
            is_launcher=True
        )
        l_general.addWidget(self.card_lanzador)

        self.card_movil = self._create_module_card(
            title="Unidad Móvil Diferencial",
            device_id="ESP32-S3 (ID 1)",
            is_launcher=False
        )
        l_general.addWidget(self.card_movil)

        top_row.addWidget(self.grp_general, stretch=2)

        # Grupo Derecho: GRÁFICA GENERAL DE PERFILES Y SECUENCIA
        # (Reemplaza al antiguo bloque de "Configuración Básica / Guías")
        self.grp_sequence = QGroupBox("Gráfica General de Perfiles (Secuencia y Transiciones)")
        self.grp_sequence.setStyleSheet("QGroupBox { font-weight: bold; color: #10b981; }")
        l_seq = QVBoxLayout(self.grp_sequence)
        l_seq.setSpacing(8)

        # Barra de control de secuencia
        h_seq_ctrl = QHBoxLayout()
        h_seq_ctrl.setSpacing(10)

        self.btn_play_seq = QPushButton("▶ PLAY SECUENCIA")
        self.btn_play_seq.setStyleSheet("""
            QPushButton {
                background-color: #059669; color: white; font-weight: bold; font-size: 13px;
                padding: 6px 16px; border-radius: 6px; border: 1px solid #10b981;
            }
            QPushButton:hover { background-color: #10b981; color: black; }
        """)
        self.btn_play_seq.clicked.connect(self._on_play_sequence)

        self.btn_stop_seq = QPushButton("⏹ DETENER")
        self.btn_stop_seq.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: bold; font-size: 12px;
                padding: 6px 12px; border-radius: 6px; border: 1px solid #ef4444;
            }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.btn_stop_seq.clicked.connect(self._on_stop_sequence)

        self.btn_clear_seq = QPushButton("🗑 Limpiar Cola")
        self.btn_clear_seq.setStyleSheet("""
            QPushButton {
                background-color: #374151; color: #f0f6fc; font-weight: bold; font-size: 11px;
                padding: 6px 10px; border-radius: 6px;
            }
            QPushButton:hover { background-color: #4b5563; }
        """)
        self.btn_clear_seq.clicked.connect(self._on_clear_sequence)

        self.lbl_seq_status = QLabel("Secuencia: En reposo (0 perfiles)")
        self.lbl_seq_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #fbbf24; padding-left: 6px;")

        h_seq_ctrl.addWidget(self.btn_play_seq)
        h_seq_ctrl.addWidget(self.btn_stop_seq)
        h_seq_ctrl.addWidget(self.btn_clear_seq)
        h_seq_ctrl.addStretch()
        h_seq_ctrl.addWidget(self.lbl_seq_status)
        l_seq.addLayout(h_seq_ctrl)

        # PlotWidget para la gráfica continua global de perfiles
        self.pw_general = pg.PlotWidget()
        self.pw_general.setBackground("#0d1117")
        self.pw_general.showGrid(x=True, y=True, alpha=0.3)
        self.pw_general.setLabel('bottom', 'Tiempo Global t (s)', units='s')
        self.pw_general.setLabel('left', 'Velocidad v (m/s)', units='m/s')
        self.pw_general.setMinimumHeight(200)
        self.pw_general.addLegend(offset=(10, 10))
        self.curve_seq_v = self.pw_general.plot([], [], pen=pg.mkPen(color='#00f0ff', width=3), name="Velocidad Real v(t)")

        l_seq.addWidget(self.pw_general)
        top_row.addWidget(self.grp_sequence, stretch=4)

        main_layout.addLayout(top_row)

        # Fila Central A: Cola de Perfiles Guardados (Secuencia Interactiva)
        self.grp_profiles_table = QGroupBox("Cola de Perfiles Configurados (Secuencia Automatizada)")
        self.grp_profiles_table.setStyleSheet("QGroupBox { font-weight: bold; color: #c084fc; }")
        l_prof_tab = QVBoxLayout(self.grp_profiles_table)
        l_prof_tab.setSpacing(6)

        self.tbl_profiles = QTableWidget(0, 6)
        self.tbl_profiles.setHorizontalHeaderLabels([
            "#", "Nombre del Perfil", "Tipo Cinemático", "Trigger Inicio", "Trigger Fin", "Estado"
        ])
        self.tbl_profiles.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_profiles.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tbl_profiles.setFixedHeight(120)
        l_prof_tab.addWidget(self.tbl_profiles)

        main_layout.addWidget(self.grp_profiles_table)

        # Fila Central B: Barra de Control de Ejecución (STOP | Reset | Cronómetro)
        exec_bar = QFrame()
        exec_bar.setStyleSheet("""
            QFrame {
                border: 1px solid #30363d;
                border-radius: 8px;
                padding: 6px 12px;
                background-color: #161b22;
            }
        """)
        l_exec = QHBoxLayout(exec_bar)
        l_exec.setSpacing(12)

        self.lbl_motion_status = QLabel("Ejecutando: [Ninguno]")
        self.lbl_motion_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #8b949e;")

        self.btn_stop = QPushButton("🛑 PARO GENERAL")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #dc2626; color: white; font-weight: bold;
                border: 1px solid #ef4444; border-radius: 6px; padding: 6px 16px;
            }
            QPushButton:hover { background-color: #b91c1c; }
        """)
        self.btn_stop.clicked.connect(self._on_stop)

        self.btn_reset = QPushButton("🔄 Reset")
        self.btn_reset.setStyleSheet("background-color: #30363d; color: #f0f6fc; font-weight: bold; padding: 6px 14px; border-radius: 6px;")
        self.btn_reset.clicked.connect(self._on_reset)

        self.lbl_timer_title = QLabel("Tiempo de Ejecución:")
        self.lbl_timer_title.setStyleSheet("color: #8b949e; font-size: 12px;")

        self.lbl_stopwatch = QLabel("00:00.00")
        self.lbl_stopwatch.setObjectName("lbl_stopwatch")

        l_exec.addWidget(self.lbl_motion_status)
        l_exec.addStretch()
        l_exec.addWidget(self.btn_stop)
        l_exec.addWidget(self.btn_reset)
        l_exec.addSpacing(16)
        l_exec.addWidget(self.lbl_timer_title)
        l_exec.addWidget(self.lbl_stopwatch)

        main_layout.addWidget(exec_bar)

        # Fila Inferior: Historial Global de Ensayos
        self.grp_history = QGroupBox(tr("grp_history", lang))
        l_hist = QVBoxLayout(self.grp_history)
        l_hist.setSpacing(6)

        h_hist_ctrl = QHBoxLayout()
        h_hist_ctrl.addStretch()

        self.btn_clear = QPushButton(tr("btn_clear_history", lang))
        self.btn_clear.clicked.connect(self._on_clear_history)

        self.btn_export_all = QPushButton(tr("btn_export_all", lang))
        self.btn_export_all.clicked.connect(self._on_export_all)

        h_hist_ctrl.addWidget(self.btn_clear)
        h_hist_ctrl.addWidget(self.btn_export_all)
        l_hist.addLayout(h_hist_ctrl)

        self.tbl_history = QTableWidget(0, 5)
        self.tbl_history.setHorizontalHeaderLabels([
            tr("tbl_col_time", lang),
            tr("tbl_col_date", lang),
            tr("tbl_col_exp", lang),
            tr("tbl_col_module", lang),
            tr("tbl_col_details", lang)
        ])
        self.tbl_history.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_history.setFixedHeight(120)
        l_hist.addWidget(self.tbl_history)

        main_layout.addWidget(self.grp_history)

    def _create_module_card(self, title: str, device_id: str, is_launcher: bool = False) -> QFrame:
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet("background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px;")
        l = QVBoxLayout(card)
        l.setSpacing(6)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #f0f6fc;")
        id_lbl = QLabel(f"ID: {device_id}")
        id_lbl.setStyleSheet("font-size: 11px; color: #8b949e;")

        l_conn = QLabel("🔴 Desconectado")
        l_conn.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 12px;")

        l_bat = QLabel("Batería: --.-- V (--%)")
        l_bat.setStyleSheet("font-size: 12px; color: #38bdf8;")

        btn_diag = QPushButton("Diagnóstico / Test")
        btn_diag.setStyleSheet("background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 5px; padding: 4px;")
        btn_diag.clicked.connect(lambda: ModuleTestModal(title, self).exec())

        l.addWidget(t_lbl)
        l.addWidget(id_lbl)
        l.addWidget(l_conn)
        l.addWidget(l_bat)
        l.addWidget(btn_diag)

        if is_launcher:
            self.lbl_card_lanz_conn = l_conn
            self.lbl_card_lanz_bat = l_bat
        else:
            self.lbl_card_movil_conn = l_conn
            self.lbl_card_movil_bat = l_bat

        return card

    # =========================================================================
    # CONEXIONES Y GESTIÓN DE SECUENCIA
    # =========================================================================
    def _connect_signals(self):
        self.app_state.dongle_connection_changed.connect(self._on_dongle_conn_changed)
        self.app_state.mobile_connection_changed.connect(self._on_mobile_conn_changed)
        self.app_state.launcher_connection_changed.connect(self._on_launcher_conn_changed)
        self.app_state.battery_updated.connect(self._on_battery_updated)
        self.app_state.execution_state_changed.connect(self._on_execution_changed)
        self.app_state.stopwatch_tick.connect(self.lbl_stopwatch.setText)
        self.app_state.history_updated.connect(self._refresh_history_table)
        self.app_state.theme_changed.connect(self._on_theme_changed)

        # Señales de la Secuencia de Perfiles
        self.app_state.profile_queue_updated.connect(self._refresh_profiles_table)
        self.app_state.sequence_state_changed.connect(self._on_sequence_state_changed)
        self.app_state.sequence_point_added.connect(self._on_sequence_point_added)
        self.app_state.sequence_marker_added.connect(self._on_sequence_marker_added)
        self.app_state.sequence_cleared.connect(self._on_sequence_cleared)

    def _on_play_sequence(self):
        if not self.app_state.profile_queue:
            QMessageBox.information(
                self,
                "Cola de Perfiles Vacía",
                "No hay perfiles en la cola. Ve a las pestañas de Unidad Móvil (MRU, MRUV, MCU) "
                "o Módulo Lanzador y pulsa 'Guardar Perfil' para agregar perfiles a la cola."
            )
            return

        if not self.app_state.dongle_connected:
            QMessageBox.warning(self, "Dongle Desconectado", "Conecta primero el Dongle ESP8266.")
            return

        self.app_state.start_sequence()

    def _on_stop_sequence(self):
        self.app_state.stop_sequence()

    def _on_clear_sequence(self):
        self.app_state.clear_profiles()
        self._on_sequence_cleared()

    @Slot(bool, str)
    def _on_sequence_state_changed(self, is_running: bool, status_msg: str):
        self.lbl_seq_status.setText(status_msg)
        self.lbl_seq_status.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {'#10b981' if is_running else '#fbbf24'}; padding-left: 6px;"
        )
        self.btn_play_seq.setEnabled(not is_running)

    @Slot(float, float, float)
    def _on_sequence_point_added(self, t_rel: float, v: float, x: float):
        if len(self.app_state.sequence_buf_t) > 0:
            self.curve_seq_v.setData(self.app_state.sequence_buf_t, self.app_state.sequence_buf_v)

    @Slot(float, str)
    def _on_sequence_marker_added(self, t_rel: float, marker_label: str):
        # Marcador visual en el eje de tiempo con nombre del perfil
        line = pg.InfiniteLine(
            pos=t_rel,
            angle=90,
            pen=pg.mkPen(color='#fbbf24', width=2, style=Qt.DashLine),
            label=marker_label,
            labelOpts={'position': 0.85, 'color': '#fbbf24', 'fill': '#161b22'}
        )
        self.pw_general.addItem(line)
        self.seq_lines.append(line)

    @Slot()
    def _on_sequence_cleared(self):
        self.curve_seq_v.setData([], [])
        for line in self.seq_lines:
            try:
                self.pw_general.removeItem(line)
            except Exception:
                pass
        self.seq_lines.clear()

    def _refresh_profiles_table(self):
        self.tbl_profiles.setRowCount(0)
        n_prof = len(self.app_state.profile_queue)
        if not self.app_state.is_sequence_running:
            self.lbl_seq_status.setText(f"Secuencia: En reposo ({n_prof} perfiles)")

        for idx, p in enumerate(self.app_state.profile_queue):
            row = self.tbl_profiles.rowCount()
            self.tbl_profiles.insertRow(row)

            # Icono y estado
            st_map = {
                "pending": "⏳ Pendiente",
                "running": "▶ EN EJECUCIÓN",
                "completed": "✓ Completado"
            }
            st_txt = st_map.get(p.status, p.status)

            # Formato amigable de trigger inicio
            tr_start = p.trigger_start
            if tr_start == "play":
                tr_start_txt = "▶ Botón Play"
            elif tr_start == "sw_izq":
                tr_start_txt = "🕹 Switch Izq"
            elif tr_start == "sw_der":
                tr_start_txt = "🕹 Switch Der"
            elif tr_start == "cny_izq":
                tr_start_txt = "👁 CNY70 Izq (Aire)"
            elif tr_start == "cny_der":
                tr_start_txt = "👁 CNY70 Der (Aire)"
            elif tr_start == "touch":
                tr_start_txt = "👆 Touch P4"
            elif tr_start.startswith("after_profile:"):
                tr_start_txt = "⛓ Al fin de perfil previo"
            else:
                tr_start_txt = tr_start

            # Formato trigger fin
            tr_end = p.trigger_end
            if tr_end == "auto":
                tr_end_txt = f"⏱ Duración ({p.params.get('dur', 0.0):.1f}s)" if 'dur' in p.params else "⏱ Auto"
            elif tr_end == "sw_izq":
                tr_end_txt = "🕹 Switch Izq"
            elif tr_end == "sw_der":
                tr_end_txt = "🕹 Switch Der"
            elif tr_end == "cny_izq":
                tr_end_txt = "👁 CNY70 Izq"
            elif tr_end == "cny_der":
                tr_end_txt = "👁 CNY70 Der"
            elif tr_end == "touch":
                tr_end_txt = "👆 Touch P4"
            else:
                tr_end_txt = tr_end

            items = [
                str(idx + 1),
                p.name,
                p.motion_type,
                tr_start_txt,
                tr_end_txt,
                st_txt
            ]

            for c, txt in enumerate(items):
                it = QTableWidgetItem(txt)
                if p.status == "running":
                    it.setBackground(pg.mkBrush("#064e3b"))
                    it.setForeground(pg.mkBrush("#6ee7b7"))
                elif p.status == "completed":
                    it.setForeground(pg.mkBrush("#a1a1aa"))
                self.tbl_profiles.setItem(row, c, it)

    # =========================================================================
    # ENLACE Y CONTROL GLOBAL
    # =========================================================================
    @Slot(bool)
    def _on_dongle_conn_changed(self, connected: bool):
        pass

    @Slot(bool)
    def _on_mobile_conn_changed(self, connected: bool):
        if connected:
            self.lbl_card_movil_conn.setText("🟢 Enlazado y Activo")
            self.lbl_card_movil_conn.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
        else:
            self.lbl_card_movil_conn.setText("🔴 Desconectado")
            self.lbl_card_movil_conn.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 12px;")

    @Slot(bool)
    def _on_launcher_conn_changed(self, connected: bool):
        if connected:
            self.lbl_card_lanz_conn.setText("🟢 Enlazado y Activo")
            self.lbl_card_lanz_conn.setStyleSheet("color: #10b981; font-weight: bold; font-size: 12px;")
        else:
            self.lbl_card_lanz_conn.setText("🔴 Desconectado")
            self.lbl_card_lanz_conn.setStyleSheet("color: #fca5a5; font-weight: bold; font-size: 12px;")

    @Slot(float, float, int)
    def _on_battery_updated(self, vbat: float, ibat: float, pct: int):
        txt = f"Batería: {vbat:.2f} V ({pct}%)"
        self.lbl_card_movil_bat.setText(txt)
        self.lbl_card_lanz_bat.setText(txt)

    @Slot(bool, str)
    def _on_execution_changed(self, is_running: bool, motion_name: str):
        if is_running:
            self.lbl_motion_status.setText(f"Ejecutando: [{motion_name}]")
            self.lbl_motion_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #10b981;")
        else:
            self.lbl_motion_status.setText(f"Finalizado: [{motion_name}]")
            self.lbl_motion_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #8b949e;")

    def _on_stop(self):
        self.app_state.stop_sequence()
        self.app_state.client.send_mobile_stop()
        self.app_state.stop_motion()

    def _on_reset(self):
        self.app_state.reset_state()
        self.lbl_motion_status.setText("Ejecutando: [Ninguno]")
        self.lbl_stopwatch.setText("00:00.00")

    def _refresh_history_table(self):
        self.tbl_history.setRowCount(0)
        for entry in self.app_state.history_log:
            row = self.tbl_history.rowCount()
            self.tbl_history.insertRow(row)
            self.tbl_history.setItem(row, 0, QTableWidgetItem(entry.time_str))
            self.tbl_history.setItem(row, 1, QTableWidgetItem(entry.date_str))
            self.tbl_history.setItem(row, 2, QTableWidgetItem(entry.motion_name))
            self.tbl_history.setItem(row, 3, QTableWidgetItem(entry.module_type))
            self.tbl_history.setItem(row, 4, QTableWidgetItem(entry.details))

    def _on_clear_history(self):
        self.app_state.clear_history()

    def _on_export_all(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar Historial Completo", "FiFuLab_Historial.csv", "Archivos CSV (*.csv)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("Hora,Fecha,Nombre,Modulo,Detalles\n")
                    for entry in self.app_state.history_log:
                        f.write(f'"{entry.time_str}","{entry.date_str}","{entry.motion_name}","{entry.module_type}","{entry.details}"\n')
                QMessageBox.information(self, "Exportación Exitosa", f"Historial guardado exitosamente en:\n{path}")
            except Exception as e:
                QMessageBox.showerror("Error", f"No se pudo guardar:\n{e}")

    def _open_settings_modal(self):
        SettingsModal(self.app_state, self).exec()

    def _on_theme_changed(self, mode: str):
        bg = '#0d1117' if mode == 'dark' else '#ffffff'
        fg = '#c9d1d9' if mode == 'dark' else '#1f2328'
        self.pw_general.setBackground(bg)
        self.pw_general.getAxis('bottom').setPen(fg)
        self.pw_general.getAxis('left').setPen(fg)
