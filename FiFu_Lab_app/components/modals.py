"""
Modal Dialogs and Wizards for FiFu Lab Studio.
Full Spanish & English translation support, clean UI notation, and dynamic Action Trigger dropdowns.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QSpinBox, QDoubleSpinBox, QWidget, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget, QGroupBox, QComboBox, QCheckBox, QMessageBox,
    QLineEdit
)
from PySide6.QtCore import Qt
import time
from typing import List, Dict, Any
from models.variables import AppState, ProfileItem
from models.translations import tr
from libs.esp32_client import MAX_COMP_MM

# --- 0. Settings Modal ---
class SettingsModal(QDialog):
    """Ventana de Configuración de la Plataforma (Tema e Idioma)."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        lang = self.app_state.language

        self.setWindowTitle(tr("settings_title", lang))
        self.setMinimumWidth(440)
        self._init_ui()

    def _init_ui(self):
        lang = self.app_state.language
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel(tr("settings_title", lang))
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl_title)

        # 1. Theme Selector
        grp_theme = QGroupBox(tr("grp_theme", lang))
        l_theme = QVBoxLayout(grp_theme)

        self.rb_dark = QRadioButton(tr("theme_dark", lang))
        self.rb_light = QRadioButton(tr("theme_light", lang))

        if self.app_state.theme_mode == "dark":
            self.rb_dark.setChecked(True)
        else:
            self.rb_light.setChecked(True)

        l_theme.addWidget(self.rb_dark)
        l_theme.addWidget(self.rb_light)
        layout.addWidget(grp_theme)

        # 2. Language Selector
        grp_lang = QGroupBox(tr("grp_lang", lang))
        l_lang = QVBoxLayout(grp_lang)

        h_lang = QHBoxLayout()
        h_lang.addWidget(QLabel(tr("lbl_select_lang", lang)))
        self.cbo_lang = QComboBox()
        self.cbo_lang.addItems(["Español (ES)", "English (EN)"])
        self.cbo_lang.setCurrentIndex(0 if self.app_state.language == "es" else 1)
        h_lang.addWidget(self.cbo_lang)

        l_lang.addLayout(h_lang)
        layout.addWidget(grp_lang)

        layout.addStretch()

        h_btn = QHBoxLayout()
        btn_cancel = QPushButton(tr("btn_cancel", lang))
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton(tr("btn_apply_save", lang))
        btn_save.setObjectName("btn_play")
        btn_save.clicked.connect(self._on_save)

        h_btn.addWidget(btn_cancel)
        h_btn.addStretch()
        h_btn.addWidget(btn_save)

        layout.addLayout(h_btn)

    def _on_save(self):
        theme_sel = "dark" if self.rb_dark.isChecked() else "light"
        lang_sel = "es" if self.cbo_lang.currentIndex() == 0 else "en"

        self.app_state.set_theme(theme_sel)
        self.app_state.set_language(lang_sel)

        msg = "Settings applied successfully." if lang_sel == "en" else "Configuración aplicada con éxito."
        QMessageBox.information(self, tr("settings_title", lang_sel), msg)
        self.accept()


# --- 1. Shoot Configuration Modal ---
class ShootModal(QDialog):
    """Ventana de Configuración de SHOOT."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        title = "Shoot Config" if app_state.language == "en" else "Configuración de Disparo"
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self._init_ui()

    def _init_ui(self):
        lang = self.app_state.language
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        t_lbl = "Configure Launch Timing" if lang == "en" else "Configurar tiempo de lanzamiento"
        lbl_title = QLabel(t_lbl)
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl_title)

        opt1 = "Instantaneous (on play click)" if lang == "en" else "Instantáneo (al presionar play)"
        opt2 = "Delay (configure time in seconds)" if lang == "en" else "Retardo (configurar tiempo en segundos)"
        self.rb_instant = QRadioButton(opt1)
        self.rb_delay = QRadioButton(opt2)

        if self.app_state.launcher_shoot_config["mode"] == "instant":
            self.rb_instant.setChecked(True)
        else:
            self.rb_delay.setChecked(True)

        layout.addWidget(self.rb_instant)
        layout.addWidget(self.rb_delay)

        delay_box = QHBoxLayout()
        delay_box.setContentsMargins(20, 0, 0, 0)
        lbl_sec = QLabel("Seconds of delay:" if lang == "en" else "Segundos de retardo:")
        self.spn_delay = QDoubleSpinBox()
        self.spn_delay.setRange(0.1, 60.0)
        self.spn_delay.setValue(self.app_state.launcher_shoot_config.get("delay_seconds", 2.0))
        self.spn_delay.setSuffix(" s")
        delay_box.addWidget(lbl_sec)
        delay_box.addWidget(self.spn_delay)
        layout.addLayout(delay_box)

        layout.addStretch()

        btn_save = QPushButton(tr("btn_save", lang))
        btn_save.setObjectName("btn_play")
        btn_save.clicked.connect(self._on_save)
        layout.addWidget(btn_save)

    def _on_save(self):
        mode = "instant" if self.rb_instant.isChecked() else "delay"
        self.app_state.launcher_shoot_config["mode"] = mode
        self.app_state.launcher_shoot_config["delay_seconds"] = self.spn_delay.value()
        self.accept()


# --- 2. Calibrate K Wizard Modal ---
class CalibrateKModal(QDialog):
    """Ventana Emergente de CALIBRATE K (3 Step Wizard)."""

    def __init__(self, app_state: AppState, parent=None):
        super().__init__(parent)
        self.app_state = app_state

        self.shot_done: List[bool] = [False, False, False, False, False]
        self.shot_buttons: List[QPushButton] = []

        title = "Calibrate K Wizard" if app_state.language == "en" else "Calibrar Constante K"
        self.setWindowTitle(title)
        self.setMinimumSize(680, 480)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)

        lang = self.app_state.language
        header_layout = QHBoxLayout()
        s1 = "(1) Setup" if lang == "en" else "(1) Configuración"
        s2 = "(2) Shots" if lang == "en" else "(2) Tiros"
        s3 = "(3) Coefficient" if lang == "en" else "(3) Coeficiente"
        self.btn_step1 = QPushButton(s1)
        self.btn_step2 = QPushButton(s2)
        self.btn_step3 = QPushButton(s3)

        header_layout.addWidget(self.btn_step1)
        header_layout.addWidget(self.btn_step2)
        header_layout.addWidget(self.btn_step3)
        main_layout.addLayout(header_layout)

        self.stacked = QStackedWidget()

        self.page1 = self._build_page1()
        self.page2 = self._build_page2()
        self.page3 = self._build_page3()

        self.stacked.addWidget(self.page1)
        self.stacked.addWidget(self.page2)
        self.stacked.addWidget(self.page3)

        main_layout.addWidget(self.stacked)
        self._update_header_style()

    def _update_header_style(self):
        idx = self.stacked.currentIndex()
        for i, btn in enumerate([self.btn_step1, self.btn_step2, self.btn_step3]):
            if i == idx:
                btn.setStyleSheet("background-color: #1f6beb; color: white; font-weight: bold;")
            else:
                btn.setStyleSheet("background-color: #1c2128; color: #8b949e;")

    def _build_page1(self) -> QWidget:
        p = QWidget()
        layout = QVBoxLayout(p)
        layout.setSpacing(16)

        lang = self.app_state.language
        grp_t = "Physical K Constant Calibration" if lang == "en" else "Ajuste de Constante K Física"
        grp = QGroupBox(grp_t)
        grp_layout = QVBoxLayout(grp)

        info_str = ("The launcher uses a spring with theoretical constant.\nBy calibrating effective K, we compensate mechanical friction losses."
                    if lang == "en" else
                    "El módulo lanzador utiliza un resorte con constante teórica.\nAl calibrar el K efectivo, compensamos las pérdidas mecánicas de fricción.")
        lbl_info = QLabel(info_str)
        lbl_info.setStyleSheet("color: #8b949e; font-size: 13px;")
        grp_layout.addWidget(lbl_info)
        layout.addWidget(grp)

        form_layout = QVBoxLayout()

        h1 = QHBoxLayout()
        lbl_m = QLabel(tr("lbl_ball_mass", lang))
        self.spn_cal_mass = QDoubleSpinBox()
        self.spn_cal_mass.setValue(self.app_state.launcher_mass)
        self.spn_cal_mass.setSuffix(" g")
        h1.addWidget(lbl_m)
        h1.addWidget(self.spn_cal_mass)
        form_layout.addLayout(h1)

        h2 = QHBoxLayout()
        lbl_dx = QLabel(tr("lbl_spring_comp", lang))
        self.spn_cal_dx = QDoubleSpinBox()
        self.spn_cal_dx.setRange(0.0, MAX_COMP_MM)
        self.spn_cal_dx.setDecimals(2)
        self.spn_cal_dx.setValue(min(MAX_COMP_MM, self.app_state.launcher_compression))
        self.spn_cal_dx.setSuffix(" mm")
        h2.addWidget(lbl_dx)
        h2.addWidget(self.spn_cal_dx)
        form_layout.addLayout(h2)

        layout.addLayout(form_layout)
        layout.addStretch()

        btn_next = QPushButton(tr("btn_next", lang))
        btn_next.setObjectName("btn_play")
        btn_next.clicked.connect(lambda: self._goto_page(1))
        layout.addWidget(btn_next, alignment=Qt.AlignRight)

        return p

    def _build_page2(self) -> QWidget:
        p = QWidget()
        layout = QVBoxLayout(p)

        lang = self.app_state.language
        instr = ("Perform remote launcher shot, optical sensors will measure exit velocity.\nRecord at least 3 shots."
                 if lang == "en" else
                 "Realiza el tiro teledirigido del lanzador, los sensores ópticos medirán la velocidad de eyección.\nRegistra un mínimo de 3 tiros.")
        lbl_instruct = QLabel(instr)
        lbl_instruct.setStyleSheet("color: #8b949e;")
        layout.addWidget(lbl_instruct)

        self.tbl_shots = QTableWidget(5, 3)
        h_shot = "Shot" if lang == "en" else "Tiro"
        h_v = "Exit v (m/s)" if lang == "en" else "v de salida (m/s)"
        h_act = "Action" if lang == "en" else "Acción"
        self.tbl_shots.setHorizontalHeaderLabels([h_shot, h_v, h_act])
        self.tbl_shots.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.shot_buttons.clear()
        for row in range(5):
            self.tbl_shots.setItem(row, 0, QTableWidgetItem(f"{row+1}"))
            self.tbl_shots.setItem(row, 1, QTableWidgetItem("-"))

            act_str = tr("btn_launch_shot", lang)
            btn_action = QPushButton(act_str)
            btn_action.setObjectName("btn_action")
            btn_action.clicked.connect(lambda _, r=row: self._simulate_shot(r))
            self.tbl_shots.setCellWidget(row, 2, btn_action)
            self.shot_buttons.append(btn_action)

        layout.addWidget(self.tbl_shots)

        h_sum = QHBoxLayout()
        add_str = "Add another shot" if lang == "en" else "Agregar otro tiro"
        btn_add = QPushButton(add_str)
        btn_add.clicked.connect(self._add_shot_row)
        h_sum.addWidget(btn_add)

        self.lbl_summary = QLabel()
        self._update_assays_summary()
        self.lbl_summary.setStyleSheet("font-weight: bold; color: #00f0ff;")
        h_sum.addWidget(self.lbl_summary, alignment=Qt.AlignRight)
        layout.addLayout(h_sum)

        h_nav = QHBoxLayout()
        btn_back = QPushButton(tr("btn_back", lang))
        btn_back.clicked.connect(lambda: self._goto_page(0))

        btn_next = QPushButton(tr("btn_next", lang))
        btn_next.setObjectName("btn_play")
        btn_next.clicked.connect(lambda: self._goto_page(2))

        h_nav.addWidget(btn_back)
        h_nav.addStretch()
        h_nav.addWidget(btn_next)
        layout.addLayout(h_nav)

        return p

    def _build_page3(self) -> QWidget:
        p = QWidget()
        layout = QVBoxLayout(p)
        layout.setSpacing(20)

        lang = self.app_state.language
        lbl_t = QLabel("K Regression Calibration Results" if lang == "en" else "Resultados de Calibración de Regresión K")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl_t)

        cards_layout = QHBoxLayout()

        c1 = QFrame()
        c1.setStyleSheet("border: 1px solid #30363d; border-radius: 8px; padding: 12px;")
        l1 = QVBoxLayout(c1)
        l1.addWidget(QLabel("CALCULATED K" if lang == "en" else "K CALCULADO"))
        val_k = QLabel("148.5 N/m")
        val_k.setStyleSheet("font-size: 20px; font-weight: bold; color: #10b981;")
        l1.addWidget(val_k)
        l1.addWidget(QLabel("Mass: 50.0 g | dx: 10.0 mm" if lang == "en" else "Masa: 50.0 g | dx: 10.0 mm"))
        cards_layout.addWidget(c1)

        c2 = QFrame()
        c2.setStyleSheet("border: 1px solid #30363d; border-radius: 8px; padding: 12px;")
        l2 = QVBoxLayout(c2)
        l2.addWidget(QLabel("UNCERTAINTY (+-)" if lang == "en" else "INCERTIDUMBRE (+-)"))
        val_unc = QLabel("± 1.2 N/m")
        val_unc.setStyleSheet("font-size: 20px; font-weight: bold; color: #f59e0b;")
        l2.addWidget(val_unc)
        cards_layout.addWidget(c2)

        c3 = QFrame()
        c3.setStyleSheet("border: 1px solid #30363d; border-radius: 8px; padding: 12px;")
        l3 = QVBoxLayout(c3)
        l3.addWidget(QLabel("R² COEFFICIENT" if lang == "en" else "COEFICIENTE R²"))
        val_r2 = QLabel("0.994")
        val_r2.setStyleSheet("font-size: 20px; font-weight: bold; color: #00f0ff;")
        l3.addWidget(val_r2)
        cards_layout.addWidget(c3)

        layout.addLayout(cards_layout)
        layout.addStretch()

        h_nav = QHBoxLayout()
        btn_back = QPushButton(tr("btn_back", lang))
        btn_back.clicked.connect(lambda: self._goto_page(1))

        btn_apply = QPushButton(tr("btn_apply_save", lang))
        btn_apply.setObjectName("btn_play")
        btn_apply.clicked.connect(self._on_apply_and_save)

        h_nav.addWidget(btn_back)
        h_nav.addStretch()
        h_nav.addWidget(btn_apply)
        layout.addLayout(h_nav)

        return p

    def _goto_page(self, index: int):
        self.stacked.setCurrentIndex(index)
        self._update_header_style()

    def _simulate_shot(self, row: int):
        import random
        lang = self.app_state.language
        new_v = round(2.40 + random.random() * 0.15, 2)
        self.tbl_shots.setItem(row, 1, QTableWidgetItem(str(new_v)))

        self.shot_done[row] = True
        repeat_str = tr("btn_repeat_shot", lang)
        self.shot_buttons[row].setText(repeat_str)
        self._update_assays_summary()

    def _update_assays_summary(self):
        lang = self.app_state.language
        done_count = sum(1 for d in self.shot_done if d)
        total_count = len(self.shot_done)
        if lang == "en":
            self.lbl_summary.setText(f"Shots ready: {done_count}/{total_count} | Estimated K: 148.5 N/m")
        else:
            self.lbl_summary.setText(f"Ensayos listos: {done_count}/{total_count} | K estimado: 148.5 N/m")

    def _add_shot_row(self):
        row = self.tbl_shots.rowCount()
        self.tbl_shots.insertRow(row)
        self.tbl_shots.setItem(row, 0, QTableWidgetItem(f"{row+1}"))
        self.tbl_shots.setItem(row, 1, QTableWidgetItem("-"))

        self.shot_done.append(False)
        act_str = tr("btn_launch_shot", self.app_state.language)
        btn_action = QPushButton(act_str)
        btn_action.setObjectName("btn_action")
        btn_action.clicked.connect(lambda _, r=row: self._simulate_shot(r))
        self.tbl_shots.setCellWidget(row, 2, btn_action)
        self.shot_buttons.append(btn_action)
        self._update_assays_summary()

    def _on_apply_and_save(self):
        self.app_state.launcher_k_constant = 148.5
        self.accept()


# --- 3. Action Trigger Modal (Pages 9 & 10) ---
class ActionTriggerModal(QDialog):
    """Ventana Emergente de ACCIÓN / ACCIÓN LANZADOR (Pages 9 & 10)."""

    def __init__(self, app_state: AppState, is_launcher: bool = False, parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.is_launcher = is_launcher

        lang = app_state.language
        title = "Ventana Emergente de ACCIÓN LANZADOR" if is_launcher else "Ventana Emergente de ACCIÓN"
        if lang == "en":
            title = "Launcher Action Triggers" if is_launcher else "Action Triggers"
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._init_ui()

    def _init_ui(self):
        lang = self.app_state.language
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Section 1: Comenzar (Start Trigger)
        grp_start_t = "Comenzar: (solo puede escoger una acción)" if lang == "es" else "Start: (select only one action)"
        grp_start = QGroupBox(grp_start_t)
        l_start = QVBoxLayout(grp_start)
        l_start.setSpacing(10)

        self.rb_start_none = QRadioButton("Ninguno (Por defecto)" if lang == "es" else "None (Default)")
        self.rb_start_none.setChecked(True)

        # Physical / Sensor Trigger with Dropdown Options
        phys_text = "Físico: al presionar..." if lang == "es" else "Physical: on pressing..."
        self.rb_start_phys = QRadioButton(phys_text)

        self.cbo_start_phys = QComboBox()
        self.cbo_start_phys.addItems([
            "PLAY",
            "Tactil 1",
            "Tactil 2",
            "Switch",
            "Sensor frontal izquierdo",
            "Sensor frontal derecho",
            "Espalda izquierdo",
            "Espalda derecho"
        ])
        self.cbo_start_phys.setEnabled(False)

        h_start_phys = QHBoxLayout()
        h_start_phys.setContentsMargins(24, 0, 0, 0)
        h_start_phys.addWidget(QLabel("Opción:" if lang == "es" else "Option:"))
        h_start_phys.addWidget(self.cbo_start_phys)

        # Digital Trigger with Dropdown Options
        digi_text = "Digital: al terminar..." if lang == "es" else "Digital: on finishing profile..."
        self.rb_start_digi = QRadioButton(digi_text)

        self.cbo_start_digi = QComboBox()
        self.cbo_start_digi.addItems([
            "Movimiento 2",
            "Movimiento 3",
            "MRU - Perfil Guardado 1",
            "MRUV - Perfil Guardado 2",
            "MCU - Perfil Guardado 3"
        ])
        self.cbo_start_digi.setEnabled(False)

        h_start_digi = QHBoxLayout()
        h_start_digi.setContentsMargins(24, 0, 0, 0)
        h_start_digi.addWidget(QLabel("Perfil:" if lang == "es" else "Profile:"))
        h_start_digi.addWidget(self.cbo_start_digi)

        # Time Trigger with [min]:[segundos] Spinboxes + Constraint Validation
        time_text = "Tiempo: en el tiempo / transcurrir..." if lang == "es" else "Time: at clock / elapsed duration..."
        self.rb_start_time = QRadioButton(time_text)

        h_start_time = QHBoxLayout()
        h_start_time.setContentsMargins(24, 0, 0, 0)
        self.spn_start_min = QSpinBox()
        self.spn_start_min.setRange(0, 59)
        self.spn_start_min.setSuffix(" min")
        self.spn_start_sec = QSpinBox()
        self.spn_start_sec.setRange(0, 59)
        self.spn_start_sec.setSuffix(" s")
        self.spn_start_min.setEnabled(False)
        self.spn_start_sec.setEnabled(False)

        h_start_time.addWidget(QLabel("Tiempo [min:s]:"))
        h_start_time.addWidget(self.spn_start_min)
        h_start_time.addWidget(self.spn_start_sec)

        # Connect radio buttons to toggle enabled state of dropdowns/inputs
        self.rb_start_none.toggled.connect(lambda chk: self._update_start_controls(chk, "none"))
        self.rb_start_phys.toggled.connect(lambda chk: self._update_start_controls(chk, "phys"))
        self.rb_start_digi.toggled.connect(lambda chk: self._update_start_controls(chk, "digi"))
        self.rb_start_time.toggled.connect(lambda chk: self._update_start_controls(chk, "time"))

        l_start.addWidget(self.rb_start_none)
        l_start.addWidget(self.rb_start_phys)
        l_start.addLayout(h_start_phys)
        l_start.addWidget(self.rb_start_digi)
        l_start.addLayout(h_start_digi)
        l_start.addWidget(self.rb_start_time)
        l_start.addLayout(h_start_time)

        layout.addWidget(grp_start)

        # Section 2: Detener (Stop Trigger)
        grp_stop_t = "Detener: (solo puede escoger una acción)" if lang == "es" else "Stop: (select only one action)"
        grp_stop = QGroupBox(grp_stop_t)
        l_stop = QVBoxLayout(grp_stop)
        l_stop.setSpacing(10)

        self.rb_stop_none = QRadioButton("Ninguno (Por defecto)" if lang == "es" else "None (Default)")
        self.rb_stop_none.setChecked(True)

        self.rb_stop_phys = QRadioButton("Físico: al presionar..." if lang == "es" else "Physical: on pressing...")
        self.cbo_stop_phys = QComboBox()
        self.cbo_stop_phys.addItems([
            "PLAY",
            "Tactil 1",
            "Tactil 2",
            "Switch",
            "Sensor frontal izquierdo",
            "Sensor frontal derecho",
            "Espalda izquierdo",
            "Espalda derecho"
        ])
        self.cbo_stop_phys.setEnabled(False)

        h_stop_phys = QHBoxLayout()
        h_stop_phys.setContentsMargins(24, 0, 0, 0)
        h_stop_phys.addWidget(QLabel("Opción:" if lang == "es" else "Option:"))
        h_stop_phys.addWidget(self.cbo_stop_phys)

        self.rb_stop_time = QRadioButton("Tiempo: al transcurrir..." if lang == "es" else "Time: elapsed duration...")
        self.spn_stop_min = QSpinBox()
        self.spn_stop_min.setRange(0, 59)
        self.spn_stop_min.setSuffix(" min")
        self.spn_stop_sec = QSpinBox()
        self.spn_stop_sec.setRange(0, 59)
        self.spn_stop_sec.setSuffix(" s")
        self.spn_stop_min.setEnabled(False)
        self.spn_stop_sec.setEnabled(False)

        h_stop_time = QHBoxLayout()
        h_stop_time.setContentsMargins(24, 0, 0, 0)
        h_stop_time.addWidget(QLabel("Tiempo [min:s]:"))
        h_stop_time.addWidget(self.spn_stop_min)
        h_stop_time.addWidget(self.spn_stop_sec)

        self.rb_stop_none.toggled.connect(lambda chk: self._update_stop_controls(chk, "none"))
        self.rb_stop_phys.toggled.connect(lambda chk: self._update_stop_controls(chk, "phys"))
        self.rb_stop_time.toggled.connect(lambda chk: self._update_stop_controls(chk, "time"))

        l_stop.addWidget(self.rb_stop_none)
        l_stop.addWidget(self.rb_stop_phys)
        l_stop.addLayout(h_stop_phys)
        l_stop.addWidget(self.rb_stop_time)
        l_stop.addLayout(h_stop_time)

        layout.addWidget(grp_stop)

        # Dialog Buttons
        h_btn = QHBoxLayout()
        btn_cancel = QPushButton(tr("btn_cancel", lang))
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton(tr("btn_save", lang))
        btn_save.setObjectName("btn_play")
        btn_save.clicked.connect(self._on_save)

        h_btn.addWidget(btn_cancel)
        h_btn.addStretch()
        h_btn.addWidget(btn_save)

        layout.addLayout(h_btn)

    def _update_start_controls(self, checked: bool, mode: str):
        if checked:
            self.cbo_start_phys.setEnabled(mode == "phys")
            self.cbo_start_digi.setEnabled(mode == "digi")
            self.spn_start_min.setEnabled(mode == "time")
            self.spn_start_sec.setEnabled(mode == "time")

    def _update_stop_controls(self, checked: bool, mode: str):
        if checked:
            self.cbo_stop_phys.setEnabled(mode == "phys")
            self.spn_stop_min.setEnabled(mode == "time")
            self.spn_stop_sec.setEnabled(mode == "time")

    def _on_save(self):
        lang = self.app_state.language

        # Time constraint check: start/stop time must be less than current motion total time if motion is active
        if self.rb_start_time.isChecked():
            start_total_sec = self.spn_start_min.value() * 60 + self.spn_start_sec.value()
            if self.app_state.is_running and start_total_sec >= self.app_state.elapsed_seconds and self.app_state.elapsed_seconds > 0:
                msg = "Time must be less than current motion total time!" if lang == "en" else "¡El tiempo configurado debe ser menor al tiempo del movimiento actual!"
                QMessageBox.warning(self, "Validation Error", msg)
                return

        start_sel = "Ninguno"
        if self.rb_start_phys.isChecked():
            start_sel = f"Físico ({self.cbo_start_phys.currentText()})"
        elif self.rb_start_digi.isChecked():
            start_sel = f"Digital ({self.cbo_start_digi.currentText()})"
        elif self.rb_start_time.isChecked():
            start_sel = f"Tiempo ({self.spn_start_min.value()}m {self.spn_start_sec.value()}s)"

        stop_sel = "Ninguno"
        if self.rb_stop_phys.isChecked():
            stop_sel = f"Físico ({self.cbo_stop_phys.currentText()})"
        elif self.rb_stop_time.isChecked():
            stop_sel = f"Tiempo ({self.spn_stop_min.value()}m {self.spn_stop_sec.value()}s)"

        if not hasattr(self.app_state, "action_triggers"):
            self.app_state.action_triggers = {}
        self.app_state.action_triggers["start"] = {"type": start_sel}
        self.app_state.action_triggers["stop"] = {"type": stop_sel}
        QMessageBox.information(self, "Action Triggers Saved", f"Start trigger: {start_sel}\nStop trigger: {stop_sel}\nConfiguration saved.")
        self.accept()


# --- 4. Module Test Modal ---
class ModuleTestModal(QDialog):
    """Ventana emergente para probar luces y buzzer del módulo."""

    def __init__(self, module_name: str, parent=None):
        super().__init__(parent)
        self.module_name = module_name
        self.setWindowTitle(f"Diagnostic Test - {module_name}")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl = QLabel(f"LED & Buzzer Diagnostic: {module_name}")
        lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl)

        btn_led = QPushButton("Flash RGB LED Lights")
        btn_led.clicked.connect(lambda: QMessageBox.information(self, "Test LED", f"RGB command sent to {module_name}"))
        layout.addWidget(btn_led)

        btn_buzzer = QPushButton("Emit Diagnostic Buzzer Tone")
        btn_buzzer.clicked.connect(lambda: QMessageBox.information(self, "Test Buzzer", f"1kHz tone emitted at {module_name}"))
        layout.addWidget(btn_buzzer)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


# --- 5. Step-by-Step Guide Modal ---
class StepByStepGuideModal(QDialog):
    """Ventana emergente de guía paso a paso."""

    def __init__(self, exp_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Step-by-Step Guide - {exp_name}")
        self.setMinimumSize(500, 360)

        layout = QVBoxLayout(self)

        lbl_t = QLabel(f"Lab Guide: {exp_name}")
        lbl_t.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl_t)

        txt_info = QLabel(
            f"1. Connect the corresponding unit ({exp_name}).\n"
            f"2. Setup initial parameters in dedicated tab.\n"
            f"3. Verify telemetry battery > 20% and baud 115200 Bd/s.\n"
            f"4. Press PLAY button to start data acquisition.\n"
            f"5. Export results to CSV for post-lab analysis."
        )
        txt_info.setStyleSheet("line-height: 1.6; padding: 16px; border-radius: 6px;")
        layout.addWidget(txt_info)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("btn_play")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)


# --- 6. Profile Save Modal ---
class ProfileSaveModal(QDialog):
    """Ventana modal interactiva para guardar un perfil con triggers de Inicio y Fin."""

    def __init__(self, app_state: AppState, motion_type: str, params: Dict[str, Any], default_name: str = "", parent=None):
        super().__init__(parent)
        self.app_state = app_state
        self.motion_type = motion_type
        self.params = params
        self.default_name = default_name

        self.setWindowTitle("Guardar Perfil Cinemático")
        self.setMinimumWidth(480)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # Encabezado
        lbl_title = QLabel("💾 Guardar Perfil en Cola de Ejecución")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00f0ff;")
        layout.addWidget(lbl_title)

        # Nombre del Perfil
        grp_name = QGroupBox("1. Identificación del Perfil")
        grp_name.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; }")
        l_name = QVBoxLayout(grp_name)
        self.txt_name = QLineEdit(self.default_name or f"Perfil {self.motion_type}")
        self.txt_name.setStyleSheet("font-size: 13px; font-weight: bold; padding: 6px; background: #161b22; color: #ffffff; border: 1px solid #30363d; border-radius: 6px;")
        l_name.addWidget(self.txt_name)
        layout.addWidget(grp_name)

        # Trigger de Inicio
        grp_start = QGroupBox("2. Condición de Inicio (Trigger Inicio)")
        grp_start.setStyleSheet("QGroupBox { font-weight: bold; color: #10b981; }")
        l_start = QVBoxLayout(grp_start)
        l_start.setSpacing(6)

        lbl_start_info = QLabel("Selecciona el evento único que disparará el inicio de este perfil:")
        lbl_start_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        l_start.addWidget(lbl_start_info)

        self.cbo_start = QComboBox()
        self.cbo_start.setStyleSheet("padding: 6px; font-size: 12px; font-weight: bold;")
        self.cbo_start.addItem("▶ Botón Play (manual o desde Dashboard)", "play")
        self.cbo_start.addItem("👁 Óptico Frontal Izquierdo (al detectar aire / desnivel)", "cny_izq")
        self.cbo_start.addItem("👁 Óptico Frontal Derecho (al detectar aire / desnivel)", "cny_der")
        self.cbo_start.addItem("🕹 Switch Frontal Izquierdo (contacto / impacto)", "sw_izq")
        self.cbo_start.addItem("🕹 Switch Frontal Derecho (contacto / impacto)", "sw_der")
        self.cbo_start.addItem("👆 Sensor Touch P4 (contacto táctil)", "touch")

        # Agregar opción de encadenamiento secuencial si ya existen perfiles previos
        if self.app_state.profile_queue:
            for p in self.app_state.profile_queue:
                self.cbo_start.addItem(f"⛓ Al finalizar perfil: '{p.name}' ({p.motion_type})", f"after_profile:{p.id}")
            # Por defecto, si ya hay perfiles previos, sugerir encadenar tras el último
            self.cbo_start.setCurrentIndex(self.cbo_start.count() - 1)

        l_start.addWidget(self.cbo_start)
        layout.addWidget(grp_start)

        # Trigger de Fin
        grp_end = QGroupBox("3. Condición de Finalización (Trigger Fin)")
        grp_end.setStyleSheet("QGroupBox { font-weight: bold; color: #f59e0b; }")
        l_end = QVBoxLayout(grp_end)
        l_end.setSpacing(6)

        lbl_end_info = QLabel("Selecciona cómo debe concluir este perfil:")
        lbl_end_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        l_end.addWidget(lbl_end_info)

        self.cbo_end = QComboBox()
        self.cbo_end.setStyleSheet("padding: 6px; font-size: 12px; font-weight: bold;")
        if self.motion_type == "LAUNCHER":
            self.cbo_end.addItem("Inmediato (Disparo de gatillo completado)", "auto")
            self.cbo_end.setEnabled(False)
        else:
            self.cbo_end.addItem("⏱ Por defecto (al concluir la duración / distancia calculada)", "auto")
            self.cbo_end.addItem("👁 Terminar antes si Óptico Frontal Izq detecta aire", "cny_izq")
            self.cbo_end.addItem("👁 Terminar antes si Óptico Frontal Der detecta aire", "cny_der")
            self.cbo_end.addItem("🕹 Terminar antes si Switch Frontal Izq detecta impacto", "sw_izq")
            self.cbo_end.addItem("🕹 Terminar antes si Switch Frontal Der detecta impacto", "sw_der")
            self.cbo_end.addItem("👆 Terminar antes si Sensor Touch P4 es tocado", "touch")

        l_end.addWidget(self.cbo_end)
        layout.addWidget(grp_end)

        # Resumen de Parámetros
        txt_params = " | ".join(f"{k}: {v}" for k, v in self.params.items())
        lbl_params = QLabel(f"Tipo: {self.motion_type} | Parámetros: {txt_params}")
        lbl_params.setStyleSheet("color: #9ca3af; font-size: 11px; background: #0d1117; padding: 6px 10px; border-radius: 4px;")
        layout.addWidget(lbl_params)

        # Botones de Acción
        h_btns = QHBoxLayout()
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setStyleSheet("padding: 8px 16px; background-color: #374151; color: white; border-radius: 6px;")
        btn_cancel.clicked.connect(self.reject)

        btn_save = QPushButton("💾 Guardar Perfil")
        btn_save.setStyleSheet("padding: 8px 20px; background-color: #059669; color: white; font-weight: bold; border-radius: 6px;")
        btn_save.clicked.connect(self._on_save)

        h_btns.addWidget(btn_cancel)
        h_btns.addStretch()
        h_btns.addWidget(btn_save)
        layout.addLayout(h_btns)

    def _on_save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre requerido", "Ingresa un nombre para el perfil.")
            return

        start_trigger = self.cbo_start.currentData()
        end_trigger = self.cbo_end.currentData()

        prof_id = f"prof_{len(self.app_state.profile_queue) + 1}_{int(time.time())}"
        item = ProfileItem(
            id=prof_id,
            name=name,
            motion_type=self.motion_type,
            params=dict(self.params),
            trigger_start=start_trigger,
            trigger_end=end_trigger,
            status="pending"
        )
        self.app_state.add_profile(item)
        QMessageBox.information(
            self,
            "Perfil Guardado",
            f"El perfil '{name}' ({self.motion_type}) ha sido agregado exitosamente a la cola de perfiles.\n"
            f"Puedes ejecutarlo o encadenarlo desde el Dashboard General."
        )
        self.accept()
