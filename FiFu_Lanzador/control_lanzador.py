import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports

class ControlLanzadorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Control Seguro de Servos y Cronógrafo CNY70 (ESP32-S3)")
        self.root.geometry("620x680")
        self.root.configure(bg="#18181b")

        self.ser = None
        self.running = False
        self.sincronizado = False

        self.ret_en = False
        self.gat_en = False

        self._construir_ui()
        self.actualizar_puertos()

    def _construir_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # --- BARRA DE CONEXIÓN SERIAL ---
        frame_conn = tk.LabelFrame(self.root, text=" 1. Conexión USB Serial (ESP32-S3) ",
                                   bg="#27272a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=10, pady=8)
        frame_conn.pack(fill="x", padx=12, pady=8)

        self.combo_ports = ttk.Combobox(frame_conn, width=22, state="readonly")
        self.combo_ports.pack(side="left", padx=5)

        tk.Button(frame_conn, text="🔄", command=self.actualizar_puertos,
                  bg="#3f3f46", fg="white", relief="flat", padx=6).pack(side="left", padx=2)

        self.btn_conn = tk.Button(frame_conn, text="Conectar", command=self.toggle_conexion,
                                  bg="#0284c7", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12)
        self.btn_conn.pack(side="left", padx=8)

        self.lbl_status = tk.Label(frame_conn, text="🔴 Desconectado", bg="#27272a", fg="#f87171", font=("Segoe UI", 9, "bold"))
        self.lbl_status.pack(side="right", padx=5)

        # --- PANEL SERVO RETRÁCTIL (PIN 8) ---
        frame_s8 = tk.LabelFrame(self.root, text=" 2. Servo Retráctil (Pin 8) - Control Protegido ",
                                 bg="#27272a", fg="#a7f3d0", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        frame_s8.pack(fill="x", padx=12, pady=6)

        top_s8 = tk.Frame(frame_s8, bg="#27272a")
        top_s8.pack(fill="x")

        self.lbl_s8_val = tk.Label(top_s8, text="Última posición guardada: --°", bg="#27272a", fg="white", font=("Consolas", 11, "bold"))
        self.lbl_s8_val.pack(side="left")

        self.btn_s8_en = tk.Button(top_s8, text="🔓 HABILITAR PWM (Attach)", command=self.toggle_servo_ret,
                                   bg="#4b5563", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10)
        self.btn_s8_en.pack(side="right")

        ctrl_s8 = tk.Frame(frame_s8, bg="#27272a", pady=8)
        ctrl_s8.pack(fill="x")

        tk.Button(ctrl_s8, text="-5°", command=lambda: self.paso_servo(8, -5), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)
        tk.Button(ctrl_s8, text="-1°", command=lambda: self.paso_servo(8, -1), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)

        self.slider_s8 = tk.Scale(ctrl_s8, from_=0, to=180, orient="horizontal", bg="#27272a", fg="white",
                                  highlightthickness=0, troughcolor="#18181b", activebackground="#10b981",
                                  command=self.on_slider_s8)
        self.slider_s8.set(90)
        self.slider_s8.pack(side="left", fill="x", expand=True, padx=8)

        tk.Button(ctrl_s8, text="+1°", command=lambda: self.paso_servo(8, 1), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)
        tk.Button(ctrl_s8, text="+5°", command=lambda: self.paso_servo(8, 5), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)

        # --- PANEL SERVO GATILLO (PIN 9) ---
        frame_s9 = tk.LabelFrame(self.root, text=" 3. Servo Gatillo (Pin 9) - Control Protegido ",
                                 bg="#27272a", fg="#fde047", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        frame_s9.pack(fill="x", padx=12, pady=6)

        top_s9 = tk.Frame(frame_s9, bg="#27272a")
        top_s9.pack(fill="x")

        self.lbl_s9_val = tk.Label(top_s9, text="Última posición guardada: --°", bg="#27272a", fg="white", font=("Consolas", 11, "bold"))
        self.lbl_s9_val.pack(side="left")

        self.btn_s9_en = tk.Button(top_s9, text="🔓 HABILITAR PWM (Attach)", command=self.toggle_servo_gat,
                                   bg="#4b5563", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=10)
        self.btn_s9_en.pack(side="right")

        ctrl_s9 = tk.Frame(frame_s9, bg="#27272a", pady=8)
        ctrl_s9.pack(fill="x")

        tk.Button(ctrl_s9, text="-5°", command=lambda: self.paso_servo(9, -5), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)
        tk.Button(ctrl_s9, text="-1°", command=lambda: self.paso_servo(9, -1), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)

        self.slider_s9 = tk.Scale(ctrl_s9, from_=0, to=180, orient="horizontal", bg="#27272a", fg="white",
                                  highlightthickness=0, troughcolor="#18181b", activebackground="#eab308",
                                  command=self.on_slider_s9)
        self.slider_s9.set(90)
        self.slider_s9.pack(side="left", fill="x", expand=True, padx=8)

        tk.Button(ctrl_s9, text="+1°", command=lambda: self.paso_servo(9, 1), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)
        tk.Button(ctrl_s9, text="+5°", command=lambda: self.paso_servo(9, 5), bg="#3f3f46", fg="white", width=4).pack(side="left", padx=2)

        # --- PANEL SENSORES ÓPTICOS CNY70 (PINES 5 Y 6 - 8 MM) ---
        frame_cny = tk.LabelFrame(self.root, text=" 4. Cronógrafo Balístico CNY70 (Pines 5 y 6 | Distancia = 8 mm) ",
                                  bg="#27272a", fg="#c084fc", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        frame_cny.pack(fill="both", expand=True, padx=12, pady=8)

        # Indicadores de estado en tiempo real de los pines 5 y 6
        pins_frame = tk.Frame(frame_cny, bg="#27272a")
        pins_frame.pack(fill="x", pady=4)

        self.lbl_cny1 = tk.Label(pins_frame, text="CNY70 #1 (Pin 5): --", bg="#18181b", fg="white",
                                 font=("Consolas", 10, "bold"), width=24, pady=6)
        self.lbl_cny1.pack(side="left", padx=4, expand=True, fill="x")

        self.lbl_cny2 = tk.Label(pins_frame, text="CNY70 #2 (Pin 6): --", bg="#18181b", fg="white",
                                 font=("Consolas", 10, "bold"), width=24, pady=6)
        self.lbl_cny2.pack(side="left", padx=4, expand=True, fill="x")

        # Métricas de Delta t y Velocidad
        metrics_frame = tk.Frame(frame_cny, bg="#18181b", pady=12)
        metrics_frame.pack(fill="x", pady=8)

        self.lbl_dt = tk.Label(metrics_frame, text="Δt: 0.000 ms (0 µs)", bg="#18181b", fg="#38bdf8",
                               font=("Consolas", 14, "bold"))
        self.lbl_dt.pack(pady=2)

        self.lbl_vel = tk.Label(metrics_frame, text="Velocidad: 0.00 m/s", bg="#18181b", fg="#4ade80",
                                font=("Consolas", 20, "bold"))
        self.lbl_vel.pack(pady=4)

        # Botones de control de sensores
        btn_cny_frame = tk.Frame(frame_cny, bg="#27272a")
        btn_cny_frame.pack(fill="x", pady=4)

        tk.Button(btn_cny_frame, text="🔄 Reiniciar Medición", command=self.reset_cronografo,
                  bg="#7c3aed", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", padx=12, pady=5).pack(side="left", padx=4)

        self.flanco_actual = "LOW"
        self.btn_flanco = tk.Button(btn_cny_frame, text="Flanco Activo: LOW (1 ➔ 0)", command=self.toggle_flanco,
                                    bg="#3f3f46", fg="white", font=("Segoe UI", 9), relief="flat", padx=10, pady=5)
        self.btn_flanco.pack(side="right", padx=4)

    def actualizar_puertos(self):
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_ports["values"] = puertos
        if puertos:
            self.combo_ports.current(0)

    def toggle_conexion(self):
        if self.ser and self.ser.is_open:
            self.running = False
            self.ser.close()
            self.lbl_status.config(text="🔴 Desconectado", fg="#f87171")
            self.btn_conn.config(text="Conectar", bg="#0284c7")
            return

        puerto = self.combo_ports.get()
        if not puerto:
            messagebox.showwarning("Puerto", "Selecciona un puerto serial primero.")
            return

        try:
            self.ser = serial.Serial(puerto, 115200, timeout=0.1)
            self.running = True
            self.sincronizado = False
            self.lbl_status.config(text="🟢 Conectado (NeoPixel Verde)", fg="#4ade80")
            self.btn_conn.config(text="Desconectar", bg="#dc2626")

            threading.Thread(target=self.hilo_lectura_serial, daemon=True).start()
            self.enviar_json({"cmd": "sync"})
        except Exception as e:
            messagebox.showerror("Error de conexión", str(e))

    def enviar_json(self, data):
        if self.ser and self.ser.is_open:
            try:
                linea = json.dumps(data) + "\n"
                self.ser.write(linea.encode("utf-8"))
            except Exception:
                pass

    # --- FUNCIONES DE SERVOS ---
    def toggle_servo_ret(self):
        self.ret_en = not self.ret_en
        ang = int(self.slider_s8.get())
        self.enviar_json({"cmd": "servo_ret", "en": self.ret_en, "ang": ang})

    def toggle_servo_gat(self):
        self.gat_en = not self.gat_en
        ang = int(self.slider_s9.get())
        self.enviar_json({"cmd": "servo_gat", "en": self.gat_en, "ang": ang})

    def on_slider_s8(self, val):
        if not self.sincronizado:
            return
        ang = int(float(val))
        self.lbl_s8_val.config(text=f"Posición Pin 8: {ang}°")
        self.enviar_json({"cmd": "servo_ret", "ang": ang})

    def on_slider_s9(self, val):
        if not self.sincronizado:
            return
        ang = int(float(val))
        self.lbl_s9_val.config(text=f"Posición Pin 9: {ang}°")
        self.enviar_json({"cmd": "servo_gat", "ang": ang})

    def paso_servo(self, pin, delta):
        if pin == 8:
            nuevo = max(0, min(180, int(self.slider_s8.get()) + delta))
            self.slider_s8.set(nuevo)
        elif pin == 9:
            nuevo = max(0, min(180, int(self.slider_s9.get()) + delta))
            self.slider_s9.set(nuevo)

    # --- FUNCIONES DE SENSORES CNY70 ---
    def reset_cronografo(self):
        self.enviar_json({"cmd": "reset_crono"})

    def toggle_flanco(self):
        self.flanco_actual = "HIGH" if self.flanco_actual == "LOW" else "LOW"
        texto = "Flanco Activo: HIGH (0 ➔ 1)" if self.flanco_actual == "HIGH" else "Flanco Activo: LOW (1 ➔ 0)"
        self.btn_flanco.config(text=texto)
        self.enviar_json({"cmd": "set_flanco", "val": self.flanco_actual})

    # --- RECEPCIÓN DE DATOS ---
    def hilo_lectura_serial(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                linea = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if linea.startswith("{") and linea.endswith("}"):
                    datos = json.loads(linea)
                    self.root.after(0, self.actualizar_ui, datos)
            except Exception:
                pass

    def actualizar_ui(self, d):
        # Sincronizar sliders por primera vez con el ángulo guardado en el ESP32
        if not self.sincronizado:
            self.slider_s8.set(d.get("ret_ang", 90))
            self.slider_s9.set(d.get("gat_ang", 90))
            self.sincronizado = True

        self.ret_en = d.get("ret_en", False)
        self.gat_en = d.get("gat_en", False)

        self.lbl_s8_val.config(text=f"Posición Pin 8: {d.get('ret_ang', 90)}°")
        self.lbl_s9_val.config(text=f"Posición Pin 9: {d.get('gat_ang', 90)}°")

        if self.ret_en:
            self.btn_s8_en.config(text="🟢 ACTIVO (Click para Liberar)", bg="#059669")
        else:
            self.btn_s8_en.config(text="🔓 HABILITAR PWM (Attach)", bg="#4b5563")

        if self.gat_en:
            self.btn_s9_en.config(text="🟢 ACTIVO (Click para Liberar)", bg="#059669")
        else:
            self.btn_s9_en.config(text="🔓 HABILITAR PWM (Attach)", bg="#4b5563")

        # Estado de sensores CNY70
        c1 = d.get("cny1", 1)
        c2 = d.get("cny2", 1)
        self.lbl_cny1.config(text=f"CNY70 #1 (Pin 5): {c1}", bg="#065f46" if c1 == 0 else "#18181b")
        self.lbl_cny2.config(text=f"CNY70 #2 (Pin 6): {c2}", bg="#065f46" if c2 == 0 else "#18181b")

        # Tiempo y Velocidad
        dt_us = d.get("dt_us", 0)
        dt_ms = d.get("dt_ms", 0.0)
        vel_ms = d.get("vel_ms", 0.0)

        self.lbl_dt.config(text=f"Δt: {dt_ms:.3f} ms ({dt_us} µs)")
        self.lbl_vel.config(text=f"Velocidad: {vel_ms:.2f} m/s ({vel_ms*100:.1f} cm/s)")

if __name__ == "__main__":
    root = tk.Tk()
    app = ControlLanzadorApp(root)
    root.mainloop()