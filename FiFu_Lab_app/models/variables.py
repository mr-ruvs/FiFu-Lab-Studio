"""
Models and Reactive State Containers for FiFu Lab Studio.
Integrates live telemetry streaming, profile execution buffers,
and centralized Qt Signals for all UI views.
"""

from PySide6.QtCore import QObject, Signal, QTimer, QDateTime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
import math

from libs.esp32_client import (
    ESP32ClientThread, ANCHO_VIA_M, PASO_MM_POR_GRADO,
    ANGULO_COMP_0MM, ANGULO_COMP_MAX, MAX_COMP_MM, ANGULO_TOPE_MIN
)

@dataclass
class ProfileItem:
    id: str
    name: str
    motion_type: str  # "MRU", "MRUV", "MCU_SPIN", "MCU_ORBIT", "LAUNCHER"
    params: Dict[str, Any]
    trigger_start: str = "play"  # "play", "sw_izq", "sw_der", "cny_izq", "cny_der", "touch", "after_profile:<id>"
    trigger_end: str = "auto"    # "auto", "sw_izq", "sw_der", "cny_izq", "cny_der", "touch"
    status: str = "pending"      # "pending", "running", "completed"

@dataclass
class ESP32Status:
    id: str = "ESP32_LAUNCHER_01"
    name: str = "ESP32 Lanzador Parabólico"
    connected: bool = False
    battery: int = 0
    baudrate: int = 115200
    latency_ms: int = 0

@dataclass
class HistoryEntry:
    time_str: str = ""
    date_str: str = ""
    motion_name: str = "MRU - Medición 1"
    module_type: str = "Unidad Móvil"
    details: str = "v = 1.2 m/s, d = 3.6 m"

class AppState(QObject):
    """Global Reactive Application State Container with Qt Signals."""

    # Enlace y Estado
    dongle_connection_changed = Signal(bool)
    mobile_connection_changed = Signal(bool)
    launcher_connection_changed = Signal(bool)

    # Telemetría en tiempo real
    mobile_telemetry_updated = Signal(dict)
    launcher_telemetry_updated = Signal(dict)
    battery_updated = Signal(float, float, int)  # vbat, ibat, pct
    shot_recorded = Signal(dict)

    # Ejecución de Perfiles y Cronómetro
    execution_state_changed = Signal(bool, str)
    stopwatch_tick = Signal(str)
    profile_point_added = Signal(float, float, float, float)  # t, x, v, a
    history_updated = Signal()

    # Sistema de Perfiles Secuenciales y Gráfica General
    profile_queue_updated = Signal()
    sequence_state_changed = Signal(bool, str)  # is_running, status_msg
    sequence_point_added = Signal(float, float, float)  # t_global, v, x
    sequence_marker_added = Signal(float, str)  # t_global, marker_label
    sequence_cleared = Signal()

    # Parámetros y Configuración
    launcher_params_changed = Signal(dict)
    mobile_params_changed = Signal(dict)
    theme_changed = Signal(str)      # "dark" or "light"
    language_changed = Signal(str)   # "es" or "en"

    def __init__(self):
        super().__init__()

        # Configuración Global
        self.theme_mode: str = "dark"   # "dark" or "light"
        self.language: str = "es"       # "es" or "en"

        # Hilo de comunicación Serial unificado con el Dongle
        self.client = ESP32ClientThread()
        self._wire_client_signals()

        # Estados de enlace
        self.dongle_connected: bool = False
        self.mobile_connected: bool = False
        self.launcher_connected: bool = False

        self.launcher_status = ESP32Status(id="ESP32_S3_LANZADOR", name="ESP32 Lanzador Parabólico", connected=False, battery=0, latency_ms=10)
        self.mobile_status = ESP32Status(id="ESP32_S3_MOVIL", name="ESP32 Unidad Móvil Diferencial", connected=False, battery=0, latency_ms=10)

        # Variables de Batería (INA226)
        self.vbat: float = 0.0
        self.ibat: float = 0.0
        self.battery_pct: int = 0

        # Variables de Telemetría Unidad Móvil (ID = 1)
        self.mobile_mode: int = 0
        self.mobile_prog: int = 0
        self.perim_byte: int = 0xFF
        self.rpm_l: float = 0.0
        self.rpm_r: float = 0.0
        self.sp_l: float = 0.0
        self.sp_r: float = 0.0
        self.v_l: float = 0.0
        self.v_r: float = 0.0
        self.v_real: float = 0.0

        # Variables de Telemetría Módulo Lanzador (ID = 2)
        self.launcher_gat_ang: int = 90
        self.launcher_ret_ang: int = 45
        self.launcher_ret_mm: float = 0.0
        self.launcher_canon_ang: int = 90
        self.launcher_tiro_deg: int = 0
        self.launcher_flags: int = 0
        self.launcher_shot_id: int = 0
        self.launcher_dt_us: int = 0
        self.launcher_v0_ms: float = 0.0
        self.launcher_shot_history: List[dict] = []

        # Parámetros Físicos del Lanzador (Cinemática y Dinámica)
        self.launcher_angle: float = 45.0
        self.launcher_compression: float = MAX_COMP_MM
        self.launcher_mass: float = 50.0
        self.launcher_k_constant: float = 148.5
        self.launcher_shoot_config: Dict[str, Any] = {
            "mode": "instant",
            "delay_seconds": 2.0
        }
        self.action_triggers: Dict[str, Any] = {
            "start": {"type": "Ninguno"},
            "stop": {"type": "Ninguno"}
        }

        # Buffers de Adquisición para Gráficas en Tiempo Real
        self.profile_active: bool = False
        self.profile_type: str = "IDLE"  # "MRU", "MRUV", "MCU", "FREE"
        self.profile_start_time: float = 0.0
        self.last_sample_time: float = 0.0
        self.integrated_x: float = 0.0
        self.current_theta: float = 0.0
        self.current_pos_x: float = 0.0
        self.current_pos_y: float = 0.0

        self.buf_t: List[float] = []
        self.buf_x: List[float] = []
        self.buf_v: List[float] = []
        self.buf_a: List[float] = []
        self.buf_sp_v: List[float] = []
        self.buf_traj_x: List[float] = []
        self.buf_traj_y: List[float] = []

        # Cola de Perfiles y Secuencia Multi-Perfil
        self.profile_queue: List[ProfileItem] = []
        self.is_sequence_running: bool = False
        self.active_profile_index: int = -1
        self.active_profile_start_time: float = 0.0
        self.sequence_start_time: float = 0.0
        self.sequence_buf_t: List[float] = []
        self.sequence_buf_v: List[float] = []
        self.sequence_buf_x: List[float] = []
        self.sequence_markers: List[Tuple[float, str]] = []

        # Estado en tiempo real de sensores perimetrales
        self.sw_der: bool = False
        self.sw_izq: bool = False
        self.cny_der_suelo: bool = True
        self.cny_der_aire: bool = False
        self.cny_izq_suelo: bool = True
        self.cny_izq_aire: bool = False
        self.touch_activo: bool = False

        # Estado de Ejecución y Cronómetro
        self.is_running: bool = False
        self.current_motion_name: str = "Ninguno"
        self.elapsed_seconds: float = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_timer_tick)

        # Historial de Ensayos
        self.history_log: List[HistoryEntry] = []

        # Iniciar hilo de comunicación serie
        self.client.start()

    def _wire_client_signals(self):
        self.client.dongle_connection_changed.connect(self._on_dongle_connection_changed)
        self.client.mobile_connection_changed.connect(self._on_mobile_connection_changed)
        self.client.launcher_connection_changed.connect(self._on_launcher_connection_changed)
        self.client.mobile_telemetry_received.connect(self._on_mobile_telemetry)
        self.client.launcher_telemetry_received.connect(self._on_launcher_telemetry)
        self.client.shot_detected.connect(self._on_shot_detected)

    def _on_dongle_connection_changed(self, connected: bool):
        self.dongle_connected = connected
        self.dongle_connection_changed.emit(connected)
        if not connected:
            self.mobile_connected = False
            self.launcher_connected = False
            self.mobile_status.connected = False
            self.launcher_status.connected = False
            self.mobile_connection_changed.emit(False)
            self.launcher_connection_changed.emit(False)

    def _on_mobile_connection_changed(self, connected: bool):
        self.mobile_connected = connected
        self.mobile_status.connected = connected
        self.mobile_connection_changed.emit(connected)

    def _on_launcher_connection_changed(self, connected: bool):
        self.launcher_connected = connected
        self.launcher_status.connected = connected
        self.launcher_connection_changed.emit(connected)

    def _on_mobile_telemetry(self, d: dict):
        self.vbat = d.get("vbat", self.vbat)
        self.ibat = d.get("ibat", self.ibat)
        self.battery_pct = d.get("pct_bat", self.battery_pct)
        self.mobile_status.battery = self.battery_pct

        self.mobile_mode = int(d.get("mode", self.mobile_mode))
        self.mobile_prog = int(d.get("prog", self.mobile_prog))
        self.perim_byte = int(d.get("perim", self.perim_byte))

        self.rpm_l = float(d.get("rpm_l", 0.0))
        self.rpm_r = float(d.get("rpm_r", 0.0))
        self.sp_l = float(d.get("sp_l", 0.0))
        self.sp_r = float(d.get("sp_r", 0.0))
        self.v_l = float(d.get("v_l", 0.0))
        self.v_r = float(d.get("v_r", 0.0))
        self.v_real = float(d.get("v_real", 0.0))

        # Actualizar banderas de sensores (PCF8574):
        # Bit 0 (P0): CNY70 Frontal Izq (1 = suelo detectado, 0 = en el aire/desnivel)
        # Bit 1 (P1): CNY70 Frontal Der (1 = suelo detectado, 0 = en el aire/desnivel)
        # Bit 2 (P2): Switch Frontal Izq (0 = impacto/contacto, 1 = libre)
        # Bit 3 (P3): Switch Frontal Der (0 = impacto/contacto, 1 = libre)
        # Bit 4 (P4): Sensor Touch (1 = contacto touch detectado, 0 = libre)
        self.cny_izq_suelo = d.get("cny_izq_suelo", ((self.perim_byte >> 0) & 1) == 1)
        self.cny_izq_aire = d.get("cny_izq_aire", ((self.perim_byte >> 0) & 1) == 0)
        self.cny_der_suelo = d.get("cny_der_suelo", ((self.perim_byte >> 1) & 1) == 1)
        self.cny_der_aire = d.get("cny_der_aire", ((self.perim_byte >> 1) & 1) == 0)
        self.sw_izq = d.get("sw_izq", ((self.perim_byte >> 2) & 1) == 0)
        self.sw_der = d.get("sw_der", ((self.perim_byte >> 3) & 1) == 0)
        self.touch_activo = d.get("touch", ((self.perim_byte >> 4) & 1) == 1)

        self.battery_updated.emit(self.vbat, self.ibat, self.battery_pct)
        self.mobile_telemetry_updated.emit(d)

        # Proceso de Secuencia Multi-Perfil (si está activa)
        if self.is_sequence_running:
            now_seq = time.time()
            t_seq = max(0.0, now_seq - self.sequence_start_time)
            self.sequence_buf_t.append(t_seq)
            self.sequence_buf_v.append(self.v_real)
            self.sequence_buf_x.append(self.integrated_x)
            self.sequence_point_added.emit(t_seq, self.v_real, self.integrated_x)

            if 0 <= self.active_profile_index < len(self.profile_queue):
                curr_prof = self.profile_queue[self.active_profile_index]
                if curr_prof.status == "running":
                    t_in_prof = now_seq - self.active_profile_start_time
                    dur_target = float(curr_prof.params.get("dur", 5.0))

                    # Verificar condición de fin de perfil
                    cond_end = curr_prof.trigger_end
                    end_reached = False
                    if cond_end == "auto" and t_in_prof >= dur_target:
                        end_reached = True
                    elif cond_end == "sw_izq" and self.sw_izq:
                        end_reached = True
                    elif cond_end == "sw_der" and self.sw_der:
                        end_reached = True
                    elif cond_end == "cny_izq" and self.cny_izq_aire:
                        end_reached = True
                    elif cond_end == "cny_der" and self.cny_der_aire:
                        end_reached = True
                    elif cond_end == "touch" and self.touch_activo:
                        end_reached = True

                    if end_reached:
                        curr_prof.status = "completed"
                        self._advance_sequence()

                elif curr_prof.status == "pending":
                    # Esperando activación por sensor
                    cond_start = curr_prof.trigger_start
                    start_reached = False
                    if cond_start == "sw_izq" and self.sw_izq:
                        start_reached = True
                    elif cond_start == "sw_der" and self.sw_der:
                        start_reached = True
                    elif cond_start == "cny_izq" and self.cny_izq_aire:
                        start_reached = True
                    elif cond_start == "cny_der" and self.cny_der_aire:
                        start_reached = True
                    elif cond_start == "touch" and self.touch_activo:
                        start_reached = True

                    if start_reached:
                        self._start_profile_item(curr_prof)

        # Si hay un perfil activo en ejecución, registrar la muestra en tiempo real
        if self.profile_active:
            now = time.time()
            dt = now - self.last_sample_time if self.last_sample_time > 0 else 0.10
            self.last_sample_time = now
            t_rel = max(0.0, now - self.profile_start_time)

            # Integración de posición lineal
            self.integrated_x += self.v_real * dt

            # Estimación de aceleración lineal instantánea
            prev_v = self.buf_v[-1] if self.buf_v else self.v_real
            acc = (self.v_real - prev_v) / dt if dt > 0.001 else 0.0

            # Integración diferencial de trayectoria 2D (MCU / Odometría)
            d_theta = ((self.v_r - self.v_l) / ANCHO_VIA_M) * dt
            self.current_theta += d_theta
            self.current_pos_x += self.v_real * math.cos(self.current_theta) * dt
            self.current_pos_y += self.v_real * math.sin(self.current_theta) * dt

            # Almacenar en buffers
            self.buf_t.append(t_rel)
            self.buf_x.append(self.integrated_x)
            self.buf_v.append(self.v_real)
            self.buf_a.append(acc)
            self.buf_sp_v.append((self.sp_l + self.sp_r) * 2.0 * math.pi * 0.030 / 120.0)
            self.buf_traj_x.append(self.current_pos_x)
            self.buf_traj_y.append(self.current_pos_y)

            self.profile_point_added.emit(t_rel, self.integrated_x, self.v_real, acc)

            # Si el robot vuelve a estado 0 (IDLE) o 5 (COLISIÓN) y ya transcurrió más de 0.5s, detener el perfil
            if self.mobile_mode in (0, 5) and t_rel > 0.5:
                self.stop_motion()

    def _on_launcher_telemetry(self, d: dict):
        self.launcher_gat_ang = int(d.get("gat", self.launcher_gat_ang))
        self.launcher_ret_ang = int(d.get("ret", self.launcher_ret_ang))
        self.launcher_ret_mm = float(d.get("comp_mm", self.launcher_ret_mm))
        self.launcher_canon_ang = int(d.get("can", self.launcher_canon_ang))
        self.launcher_tiro_deg = int(d.get("tiro_deg", self.launcher_tiro_deg))
        self.launcher_flags = int(d.get("flags", self.launcher_flags))
        self.launcher_shot_id = int(d.get("shot_id", self.launcher_shot_id))
        self.launcher_dt_us = int(d.get("dt_us", self.launcher_dt_us))
        self.launcher_v0_ms = float(d.get("v_ms", self.launcher_v0_ms))

        self.launcher_telemetry_updated.emit(d)

    def _on_shot_detected(self, d: dict):
        comp_mm = float(d.get("comp_mm", 0.0))
        if comp_mm < 1.0:
            return

        hora = datetime.now().strftime("%H:%M:%S")
        shot_entry = {
            "id": d.get("shot_id", 0),
            "hora": hora,
            "comp_mm": comp_mm,
            "ang_ret": d.get("ret", 45),
            "ang_tiro": d.get("tiro_deg", 0),
            "dt_us": d.get("dt_us", 0),
            "v_ms": d.get("v_ms", 0.0),
            "v_kmh": d.get("v_kmh", 0.0)
        }
        self.launcher_shot_history.insert(0, shot_entry)
        self.shot_recorded.emit(shot_entry)

        # Agregar al historial general
        entry = HistoryEntry(
            time_str=hora,
            date_str=datetime.now().strftime("%d/%m/%Y"),
            motion_name=f"Disparo #{shot_entry['id']} ({shot_entry['ang_tiro']}°)",
            module_type="Lanzador Parabólico",
            details=f"v0 = {shot_entry['v_ms']:.3f} m/s, comp = {shot_entry['comp_mm']:.1f} mm, dt = {shot_entry['dt_us']} µs"
        )
        self.history_log.insert(0, entry)
        self.history_updated.emit()

    def set_theme(self, mode: str):
        if mode in ("dark", "light"):
            self.theme_mode = mode
            self.theme_changed.emit(mode)

    def set_language(self, lang: str):
        if lang in ("es", "en"):
            self.language = lang
            self.language_changed.emit(lang)

    def start_motion(self, name: str = "Movimiento Personalizado", profile_type: str = "MRU", initial_pos: Tuple[float, float] = (0.0, 0.0), initial_x: float = 0.0):
        self.is_running = True
        self.current_motion_name = name
        self.elapsed_seconds = 0.0

        # Reiniciar buffers para adquisición limpia
        self.profile_active = True
        self.profile_type = profile_type
        self.profile_start_time = time.time()
        self.last_sample_time = self.profile_start_time
        self.integrated_x = float(initial_x)
        self.current_theta = 0.0
        self.current_pos_x = float(initial_pos[0])
        self.current_pos_y = float(initial_pos[1])

        self.buf_t.clear()
        self.buf_x.clear()
        self.buf_v.clear()
        self.buf_a.clear()
        self.buf_sp_v.clear()
        self.buf_traj_x.clear()
        self.buf_traj_y.clear()

        if profile_type == "MCU" and (initial_pos[0] != 0.0 or initial_pos[1] != 0.0):
            self.buf_traj_x.append(self.current_pos_x)
            self.buf_traj_y.append(self.current_pos_y)

        self._timer.start()
        self.execution_state_changed.emit(True, self.current_motion_name)

    def stop_motion(self):
        if not self.is_running and not self.profile_active:
            return
        self.is_running = False
        self.profile_active = False
        self._timer.stop()
        self.execution_state_changed.emit(False, self.current_motion_name)

        if self.elapsed_seconds > 0:
            now = QDateTime.currentDateTime()
            dist_final = self.integrated_x if self.buf_x else 0.0
            new_entry = HistoryEntry(
                time_str=now.toString("hh:mm:ss"),
                date_str=now.toString("dd/MM/yyyy"),
                motion_name=self.current_motion_name,
                module_type="Unidad Móvil",
                details=f"t = {self.elapsed_seconds:.2f} s, d_real = {dist_final:.2f} m"
            )
            self.history_log.insert(0, new_entry)
            self.history_updated.emit()

    def _on_timer_tick(self):
        if self.is_running:
            self.elapsed_seconds += 0.1
            minutes = int(self.elapsed_seconds) // 60
            seconds = int(self.elapsed_seconds) % 60
            millis = int((self.elapsed_seconds - int(self.elapsed_seconds)) * 100)
            time_str = f"{minutes:02d}:{seconds:02d}.{millis:02d}"
            self.stopwatch_tick.emit(time_str)

    def reset_state(self):
        self.stop_motion()
        self.elapsed_seconds = 0.0
        self.stopwatch_tick.emit("00:00.00")
        self.integrated_x = 0.0
        self.current_theta = 0.0
        self.current_pos_x = 0.0
        self.current_pos_y = 0.0
        self.buf_t.clear()
        self.buf_x.clear()
        self.buf_v.clear()
        self.buf_a.clear()
        self.buf_sp_v.clear()
        self.buf_traj_x.clear()
        self.buf_traj_y.clear()

    def clear_history(self):
        self.history_log.clear()
        self.history_updated.emit()

    # =========================================================================
    # GESTOR DE COLA DE PERFILES Y SECUENCIA MULTI-PERFIL
    # =========================================================================
    def add_profile(self, item: ProfileItem) -> str:
        self.profile_queue.append(item)
        self.profile_queue_updated.emit()
        return item.id

    def remove_profile(self, profile_id: str):
        self.profile_queue = [p for p in self.profile_queue if p.id != profile_id]
        self.profile_queue_updated.emit()

    def clear_profiles(self):
        self.stop_sequence()
        self.profile_queue.clear()
        self.profile_queue_updated.emit()

    def start_sequence(self):
        if not self.profile_queue:
            return
        self.is_sequence_running = True
        self.sequence_start_time = time.time()
        self.sequence_buf_t.clear()
        self.sequence_buf_v.clear()
        self.sequence_buf_x.clear()
        self.sequence_markers.clear()
        self.sequence_cleared.emit()

        for p in self.profile_queue:
            p.status = "pending"

        self.active_profile_index = 0
        self.sequence_state_changed.emit(True, f"Ejecutando Secuencia ({len(self.profile_queue)} perfiles)")
        self.profile_queue_updated.emit()

        p0 = self.profile_queue[0]
        if p0.trigger_start == "play" or p0.trigger_start.startswith("after_profile"):
            self._start_profile_item(p0)

    def stop_sequence(self):
        self.is_sequence_running = False
        self.client.send_mobile_stop()
        self.stop_motion()
        self.sequence_state_changed.emit(False, "Secuencia Detenida")
        self.profile_queue_updated.emit()

    def _start_profile_item(self, prof: ProfileItem):
        prof.status = "running"
        now = time.time()
        self.active_profile_start_time = now
        t_seq = max(0.0, now - self.sequence_start_time)
        marker_label = f"P{self.active_profile_index + 1}: {prof.name}"
        self.sequence_markers.append((t_seq, marker_label))
        self.sequence_marker_added.emit(t_seq, marker_label)
        self.profile_queue_updated.emit()

        if prof.motion_type == "MRU":
            v = float(prof.params.get("v", 0.3))
            dur = float(prof.params.get("dur", 3.0))
            self.start_motion(f"MRU: {prof.name}", profile_type="MRU")
            self.client.send_mobile_mru(v, dur)
        elif prof.motion_type == "MRUV":
            v0 = float(prof.params.get("v0", 0.1))
            vf = float(prof.params.get("vf", 0.5))
            dur = float(prof.params.get("dur", 3.0))
            self.start_motion(f"MRUV: {prof.name}", profile_type="MRUV")
            self.client.send_mobile_mruv(v0, vf, dur)
        elif prof.motion_type == "MCU_SPIN":
            vl = float(prof.params.get("v_l", 0.2))
            vr = float(prof.params.get("v_r", -0.2))
            dur = float(prof.params.get("dur", 3.0))
            self.start_motion(f"MCU Giro: {prof.name}", profile_type="MCU")
            self.client.send_mobile_mcu(vl, vr, dur)
        elif prof.motion_type == "MCU_ORBIT":
            vl = float(prof.params.get("v_l", 0.3))
            vr = float(prof.params.get("v_r", 0.1))
            dur = float(prof.params.get("dur", 5.0))
            r = float(prof.params.get("r", 0.20))
            init_y = +r if (vl >= vr) else -r
            self.start_motion(f"MCU Órbita: {prof.name}", profile_type="MCU", initial_pos=(0.0, init_y))
            self.client.send_mobile_mcu(vl, vr, dur)
        elif prof.motion_type == "LAUNCHER":
            ang = int(prof.params.get("angle", 108))
            self.client.send_launcher_gatillo_liberar(ang)
            prof.status = "completed"
            self._advance_sequence()

    def _advance_sequence(self):
        self.active_profile_index += 1
        if self.active_profile_index >= len(self.profile_queue):
            self.stop_sequence()
            self.client.send_mobile_stop()
            self.sequence_state_changed.emit(False, "Secuencia de Perfiles Finalizada")
            self.profile_queue_updated.emit()
            return

        next_prof = self.profile_queue[self.active_profile_index]
        prev_prof = self.profile_queue[self.active_profile_index - 1]
        self.profile_queue_updated.emit()

        if next_prof.trigger_start in ("play", f"after_profile:{prev_prof.id}") or next_prof.trigger_start.startswith("after_profile"):
            self._start_profile_item(next_prof)
