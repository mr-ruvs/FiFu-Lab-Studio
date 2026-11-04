"""
ESP32 / ESP-NOW Dongle Serial Client Thread for FiFuLab Studio.
Handles real-time telemetry streaming and command dispatching
via USB Serial Dongle (ESP8266 ESP-NOW Bridge) connected to:
  1. Robot Móvil (ESP32-S3 ID=1)
  2. Módulo Lanzador (ESP32-S3 ID=2)
"""

import time
import json
import math
from typing import List, Tuple, Optional
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

# --- CONSTANTES FÍSICAS Y CALIBRACIÓN ---
RADIO_RUEDA_M = 0.030        # Radio de ruedas motrices: 30 mm (0.030 m)
ANCHO_VIA_M = 0.133          # Separación entre ruedas: 133 mm (0.133 m)
MS_TO_RPM = 60.0 / (2.0 * math.pi * RADIO_RUEDA_M)  # 318.309886 RPM por m/s
ANGULO_TOPE_MIN = 20.0       # 20° = Límite mínimo para ajuste del tope mecánico
ANGULO_COMP_0MM = 45.0       # 45° = 0.0 mm de compresión
ANGULO_COMP_MAX = 95.0       # 95° = Distancia máxima de compresión
PASO_MM_POR_GRADO = (16.0 * math.pi) / 360.0  # Módulo m=1mm, Z=16 -> (16*pi)/360 =~ 0.13962634 mm/°
MAX_COMP_MM = (ANGULO_COMP_MAX - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO  # 50° * PASO =~ 6.9813 mm


def list_available_ports() -> List[Tuple[str, str]]:
    """Returns a list of tuples (device_path, description) of all available serial ports."""
    if not SERIAL_AVAILABLE:
        return []
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append((p.device, p.description or p.device))
    return ports


class ESP32ClientThread(QThread):
    """
    Worker thread that maintains communication with the ESP8266 Dongle (ESP-NOW bridge)
    and relays bidirectional telemetry and commands with the Mobile Robot and Launcher.
    """

    # Señales de enlace
    dongle_connection_changed = Signal(bool)
    mobile_connection_changed = Signal(bool)
    launcher_connection_changed = Signal(bool)

    # Señales de telemetría procesada
    mobile_telemetry_received = Signal(dict)
    launcher_telemetry_received = Signal(dict)

    # Señal de disparo nuevo del cronógrafo balístico
    shot_detected = Signal(dict)

    def __init__(self, port: Optional[str] = None, baudrate: int = 115200, parent=None):
        super().__init__(parent)
        self.port = port
        self.baudrate = baudrate

        self._running = True
        self._mutex = QMutex()
        self._cmd_queue = []
        self._serial_handle = None

        # Estados de enlace y Watchdogs (2.5 segundos de timeout)
        self._dongle_connected = False
        self._mobile_connected = False
        self._mobile_last_packet_time = 0.0

        self._launcher_connected = False
        self._launcher_last_packet_time = 0.0

        self._ultimo_shot_id = 0

    def set_serial_config(self, port: Optional[str], baudrate: int = 115200):
        """Update target serial port and baudrate, triggering reconnect."""
        with QMutexLocker(self._mutex):
            self.port = port.strip() if port else None
            self.baudrate = int(baudrate)
            if self._serial_handle:
                try:
                    self._serial_handle.close()
                except Exception:
                    pass
                self._serial_handle = None
            self._dongle_connected = False
            self._mobile_connected = False
            self._launcher_connected = False
            self.dongle_connection_changed.emit(False)
            self.mobile_connection_changed.emit(False)
            self.launcher_connection_changed.emit(False)

    def disconnect_client(self):
        """Close active serial connection and reset all device link states."""
        with QMutexLocker(self._mutex):
            if self._serial_handle:
                try:
                    self._serial_handle.close()
                except Exception:
                    pass
                self._serial_handle = None
            self._dongle_connected = False
            self._mobile_connected = False
            self._launcher_connected = False
            self.dongle_connection_changed.emit(False)
            self.mobile_connection_changed.emit(False)
            self.launcher_connection_changed.emit(False)

    def stop(self):
        """Terminate the thread safely."""
        with QMutexLocker(self._mutex):
            self._running = False
        self.wait(1000)
        self.disconnect_client()

    def is_dongle_connected(self) -> bool:
        return self._dongle_connected

    def is_mobile_connected(self) -> bool:
        return self._mobile_connected

    def is_launcher_connected(self) -> bool:
        return self._launcher_connected

    # =========================================================================
    # COMANDOS HACIA UNIDAD MÓVIL (target = 1)
    # =========================================================================
    def send_mobile_cmd(self, mode: int, p1: float, p2: float, dur: float):
        """
        Envia un comando cinemático a la Unidad Móvil.
        Mode: 0=STOP, 1=MRU, 2=MRUV, 3=MCU, 4=DIRECT_RPM.
        Nota: perim_stop se fija en 0 para que el microcontrolador no aborte el movimiento
        ni active paradas de emergencia por lectura de sensores.
        """
        payload = {
            "target": 1,
            "mode": int(mode),
            "perim_stop": 0,
            "p1": round(float(p1), 4),
            "p2": round(float(p2), 4),
            "dur": round(float(dur), 2)
        }
        self._queue_command(payload)

    def send_mobile_mru(self, v: float, dur: float):
        """Ejecuta MRU a velocidad v (m/s) durante dur (s)."""
        self.send_mobile_cmd(mode=1, p1=v, p2=0.0, dur=dur)

    def send_mobile_mruv(self, v0: float, vf: float, dur: float):
        """Ejecuta MRUV de v0 (m/s) a vf (m/s) durante dur (s)."""
        self.send_mobile_cmd(mode=2, p1=v0, p2=vf, dur=dur)

    def send_mobile_mcu(self, v_l: float, v_r: float, dur: float):
        """Ejecuta MCU con velocidades tangenciales de rueda v_l y v_r (m/s)."""
        self.send_mobile_cmd(mode=3, p1=v_l, p2=v_r, dur=dur)

    def send_mobile_rpm(self, rpm_l: float, rpm_r: float, dur: float = 1.0):
        """Control directo en RPM para lazo abierto o pruebas (modo 4)."""
        self.send_mobile_cmd(mode=4, p1=rpm_l, p2=rpm_r, dur=dur)

    def send_mobile_stop(self):
        """Paro inmediato para la Unidad Móvil."""
        self.send_mobile_cmd(mode=0, p1=0.0, p2=0.0, dur=0.0)

    # =========================================================================
    # COMANDOS HACIA UNIDAD LANZADOR (target = 2)
    # =========================================================================
    def send_launcher_cmd(self, action: int, pin: int, ang: int):
        """
        Envia un comando al Módulo Lanzador.
        Action: 1=Mover Servo, 2=Buzzer, 3=Reset Crono, 4=Disparo Rápido + Re-anclar Auto
        Pin: 8=Gatillo, 9=Retráctil, 10=Cañón
        """
        payload = {
            "target": 2,
            "action": int(action),
            "pin": int(pin),
            "ang": int(ang)
        }
        self._queue_command(payload)

    def send_launcher_retractil(self, ang_deg: int):
        """Posiciona el servo de retracción/compresión (IO9, 20° a 95°)."""
        deg = max(int(ANGULO_TOPE_MIN), min(int(ANGULO_COMP_MAX), int(ang_deg)))
        self.send_launcher_cmd(action=1, pin=9, ang=deg)

    def send_launcher_compression_mm(self, comp_mm: float):
        """Posiciona la compresión en milímetros (0.0 a MAX_COMP_MM mm)."""
        mm = max(0.0, min(MAX_COMP_MM, float(comp_mm)))
        deg = int(round(ANGULO_COMP_0MM + (mm / PASO_MM_POR_GRADO)))
        self.send_launcher_retractil(deg)

    def send_launcher_canon(self, tiro_deg: int):
        """Posiciona el cañón de 0° (horizontal, servo 90°) a 90° (vertical, servo 180°)."""
        tiro = max(0, min(90, int(tiro_deg)))
        servo_ang = 90 + tiro
        self.send_launcher_cmd(action=1, pin=10, ang=servo_ang)

    def send_launcher_gatillo_anclar(self):
        """Ancla el resorte en el gatillo mecánico (IO8 a 90°)."""
        self.send_launcher_cmd(action=1, pin=8, ang=90)

    def send_launcher_gatillo_liberar(self, ang_deg: int = 108):
        """Libera manualmente el resorte (IO8 a ang_deg, típicamente 108°)."""
        ang = max(95, min(160, int(ang_deg)))
        self.send_launcher_cmd(action=1, pin=8, ang=ang)

    def send_launcher_disparo_auto(self, ang_deg: int = 108):
        """Dispara liberando a ang_deg y re-ancla automáticamente a 90° tras 950 ms."""
        ang = max(95, min(160, int(ang_deg)))
        self.send_launcher_cmd(action=4, pin=8, ang=ang)

    def send_launcher_buzzer(self):
        """Emite un beep sonoro de confirmación en el buzzer del lanzador."""
        self.send_launcher_cmd(action=2, pin=0, ang=0)

    def send_launcher_reset_crono(self):
        """Reinicia el cronógrafo balístico para una nueva medición."""
        self.send_launcher_cmd(action=3, pin=0, ang=0)

    def _queue_command(self, cmd_dict: dict):
        with QMutexLocker(self._mutex):
            # Optimización de streaming continuo: Si ya hay un comando de RPM (modo 4) pendiente de envío,
            # actualizarlo con la consigna más reciente para evitar sobrecarga o retardo acumulativo
            if cmd_dict.get("target") == 1 and cmd_dict.get("mode") == 4 and self._cmd_queue:
                if self._cmd_queue[-1].get("target") == 1 and self._cmd_queue[-1].get("mode") == 4:
                    self._cmd_queue[-1] = cmd_dict
                    return
            self._cmd_queue.append(cmd_dict)

    # =========================================================================
    # BUCLE PRINCIPAL DEL HILO
    # =========================================================================
    def run(self):
        buffer = ""

        while self._running:
            with QMutexLocker(self._mutex):
                target_port = self.port
                target_baud = self.baudrate

            if not target_port or not SERIAL_AVAILABLE:
                time.sleep(0.05)
                continue

            # 1. Abrir o reabrir el puerto serie
            if self._serial_handle is None or not self._serial_handle.is_open:
                try:
                    self._serial_handle = serial.Serial(target_port, target_baud, timeout=0.03)
                    self._serial_handle.reset_input_buffer()
                    self._dongle_connected = True
                    self.dongle_connection_changed.emit(True)
                    time.sleep(0.05)
                except Exception:
                    if self._dongle_connected:
                        self._dongle_connected = False
                        self.dongle_connection_changed.emit(False)
                    if self._mobile_connected:
                        self._mobile_connected = False
                        self.mobile_connection_changed.emit(False)
                    if self._launcher_connected:
                        self._launcher_connected = False
                        self.launcher_connection_changed.emit(False)
                    time.sleep(0.5)
                    continue

            # 2. Transmitir comandos pendientes por el puerto serie
            cmds_to_send = []
            with QMutexLocker(self._mutex):
                if self._cmd_queue:
                    cmds_to_send = list(self._cmd_queue)
                    self._cmd_queue.clear()

            for c in cmds_to_send:
                try:
                    line = json.dumps(c) + "\n"
                    self._serial_handle.write(line.encode("utf-8"))
                    self._serial_handle.flush()
                except Exception as e:
                    print(f"Error TX Serial: {e}")

            # 3. Leer líneas entrantes desde el Dongle ESP8266
            try:
                n = self._serial_handle.in_waiting if self._serial_handle else 0
                if n > 0:
                    chunk = self._serial_handle.read(n).decode("utf-8", errors="ignore")
                    buffer += chunk

                    while "\n" in buffer:
                        linea, buffer = buffer.split("\n", 1)
                        linea = linea.strip()
                        if linea.startswith("{") and linea.endswith("}"):
                            try:
                                d = json.loads(linea)
                                self._dispatch_incoming_packet(d)
                            except json.JSONDecodeError:
                                pass
            except Exception:
                try:
                    self._serial_handle.close()
                except Exception:
                    pass
                self._serial_handle = None
                self._dongle_connected = False
                self.dongle_connection_changed.emit(False)
                if self._mobile_connected:
                    self._mobile_connected = False
                    self.mobile_connection_changed.emit(False)
                if self._launcher_connected:
                    self._launcher_connected = False
                    self.launcher_connection_changed.emit(False)

            # 4. Watchdogs independientes para Móvil y Lanzador (2.5 segundos)
            now = time.time()
            if self._mobile_connected and (now - self._mobile_last_packet_time > 2.5):
                self._mobile_connected = False
                self.mobile_connection_changed.emit(False)

            if self._launcher_connected and (now - self._launcher_last_packet_time > 2.5):
                self._launcher_connected = False
                self.launcher_connection_changed.emit(False)

            time.sleep(0.01)

    def _dispatch_incoming_packet(self, d: dict):
        src = d.get("src", 0)

        # Caso 1: Telemetría de la Unidad Móvil (src == 1)
        if src == 1:
            self._mobile_last_packet_time = time.time()
            if not self._mobile_connected:
                self._mobile_connected = True
                self.mobile_connection_changed.emit(True)

            # Calcular variables derivadas para conveniencia
            vbat = float(d.get("vbat", 0.0))
            ibat = float(d.get("ibat", 0.0))
            pct = int(max(0.0, min(100.0, ((vbat - 12.8) / (16.8 - 12.8)) * 100.0)))

            rpm_l = float(d.get("rpm_l", 0.0))
            rpm_r = float(d.get("rpm_r", 0.0))
            sp_l = float(d.get("sp_l", 0.0))
            sp_r = float(d.get("sp_r", 0.0))

            v_l = (rpm_l * 2.0 * math.pi * RADIO_RUEDA_M) / 60.0
            v_r = (rpm_r * 2.0 * math.pi * RADIO_RUEDA_M) / 60.0
            v_real = (v_l + v_r) / 2.0

            # Decodificación de Sensores de la Placa Perimetral (PCF8574):
            # P0 (Bit 0): CNY70 Frontal Izquierdo (1 = suelo detectado, 0 = en el aire/desnivel)
            # P1 (Bit 1): CNY70 Frontal Derecho (1 = suelo detectado, 0 = en el aire/desnivel)
            # P2 (Bit 2): Switch Frontal Izquierdo (0 = impacto/contacto, 1 = libre)
            # P3 (Bit 3): Switch Frontal Derecho (0 = impacto/contacto, 1 = libre)
            # P4 (Bit 4): Sensor Touch (1 = contacto touch detectado, 0 = libre)
            perim = int(d.get("perim", 0xFF))
            cny_izq_suelo = ((perim >> 0) & 1) == 1
            cny_izq_aire = ((perim >> 0) & 1) == 0
            cny_der_suelo = ((perim >> 1) & 1) == 1
            cny_der_aire = ((perim >> 1) & 1) == 0
            sw_izq = ((perim >> 2) & 1) == 0
            sw_der = ((perim >> 3) & 1) == 0
            touch = ((perim >> 4) & 1) == 1

            d["cny_izq_suelo"] = cny_izq_suelo
            d["cny_izq_aire"] = cny_izq_aire
            d["cny_der_suelo"] = cny_der_suelo
            d["cny_der_aire"] = cny_der_aire
            d["sw_izq"] = sw_izq
            d["sw_der"] = sw_der
            d["touch"] = touch

            d["vbat"] = vbat
            d["ibat"] = ibat
            d["pct_bat"] = pct
            d["v_l"] = v_l
            d["v_r"] = v_r
            d["v_real"] = v_real
            d["rpm_l"] = rpm_l
            d["rpm_r"] = rpm_r
            d["sp_l"] = sp_l
            d["sp_r"] = sp_r
            d["timestamp"] = self._mobile_last_packet_time

            self.mobile_telemetry_received.emit(d)

        # Caso 2: Telemetría de la Unidad del Lanzador (src == 2)
        elif src == 2:
            self._launcher_last_packet_time = time.time()
            if not self._launcher_connected:
                self._launcher_connected = True
                self.launcher_connection_changed.emit(True)

            flags = int(d.get("flags", 0))
            d["act8"] = bool(flags & (1 << 0))
            d["act10"] = bool(flags & (1 << 1))
            d["cny1"] = bool(flags & (1 << 2))
            d["cny2"] = bool(flags & (1 << 3))
            d["armado"] = bool(flags & (1 << 4))
            d["touch"] = bool(flags & (1 << 5))

            ang_ret = int(d.get("ret", 45))
            comp_mm = max(0.0, min(MAX_COMP_MM, (ang_ret - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO))
            ang_can = int(d.get("can", 90))
            tiro_deg = max(0, ang_can - 90)

            d["comp_mm"] = comp_mm
            d["tiro_deg"] = tiro_deg
            d["timestamp"] = self._launcher_last_packet_time

            shot_id = int(d.get("shot_id", 0))
            d["v_ms"] = float(d.get("v_ms", 0.0))
            d["v_kmh"] = d["v_ms"] * 3.6
            d["dt_us"] = int(d.get("dt_us", 0))

            self.launcher_telemetry_received.emit(d)

            # Notificar si hay un nuevo disparo registrado (solo si la retracción es >= 1.0 mm)
            if shot_id > 0 and shot_id != self._ultimo_shot_id:
                self._ultimo_shot_id = shot_id
                if comp_mm >= 1.0:
                    self.shot_detected.emit(d)
