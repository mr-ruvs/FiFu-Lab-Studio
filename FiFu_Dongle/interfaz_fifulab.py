# archivo: interfaz_fifulab.py
import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import json
import time
import math
from datetime import datetime

# --- CONSTANTES FÍSICAS Y DE CALIBRACIÓN ---
PASO_MM_POR_GRADO = 0.1396   # Cremallera 16T: 0.1396 mm por grado de servo
ANGULO_COMP_0MM   = 45.0     # 45° = 0.0 mm de compresión
ANGULO_COMP_MAX   = 125.0    # 125° = 11.17 mm de compresión máxima
MAX_COMP_MM       = (ANGULO_COMP_MAX - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO
ANCHO_VIA_M       = 0.140    # Separación entre ruedas motrices L = 140 mm (0.140 m)


class FiFuLabApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FiFu Lab Studio - Plataforma Unificada ESP-NOW (Móvil + Lanzador)")
        self.root.geometry("960x760")
        self.root.configure(bg="#18181b")

        self.serial_port = None
        self.running = False
        self.serial_lock = threading.Lock()

        # Marcas de tiempo para detección independiente de módulos
        self.last_rx_movil = 0.0
        self.last_rx_lanzador = 0.0
        self.ultimo_shot_id = 0

        self._configurar_estilos()
        self._construir_encabezado()
        self._construir_pestanas()
        self._actualizar_puertos()
        self._loop_watchdog()

    def _configurar_estilos(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#18181b", borderwidth=0)
        style.configure("TNotebook.Tab", background="#27272a", foreground="#e4e4e7",
                        padding=[16, 8], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", "#0284c7")],
                  foreground=[("selected", "#ffffff")])

    # =========================================================================
    # 1. ENCABEZADO GLOBAL (CONEXIÓN DONGLE, ESTADO INDEPENDIENTE Y BATERÍA)
    # =========================================================================
    def _construir_encabezado(self):
        header = tk.Frame(self.root, bg="#27272a", padx=12, pady=8, highlightbackground="#3f3f46", highlightthickness=1)
        header.pack(fill="x", padx=12, pady=(10, 6))

        tk.Label(header, text="Dongle (ESP8266):", bg="#27272a", fg="#38bdf8", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.combo_puertos = ttk.Combobox(header, width=13, state="readonly")
        self.combo_puertos.pack(side="left", padx=2)

        tk.Button(header, text="🔄", command=self._actualizar_puertos, bg="#3f3f46", fg="#ffffff", relief="flat", width=3).pack(side="left", padx=2)
        self.btn_conectar = tk.Button(header, text="Conectar Dongle", command=self._toggle_conexion,
                                      bg="#0284c7", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8)
        self.btn_conectar.pack(side="left", padx=6)

        self.lbl_link_movil = tk.Label(header, text="🔴 MÓVIL: OFF", bg="#3f3f46", fg="#fca5a5",
                                       font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        self.lbl_link_movil.pack(side="left", padx=6)

        self.lbl_link_lanz = tk.Label(header, text="🔴 LANZADOR: OFF", bg="#3f3f46", fg="#fca5a5",
                                      font=("Segoe UI", 9, "bold"), padx=8, pady=4)
        self.lbl_link_lanz.pack(side="left", padx=4)

        f_bat = tk.Frame(header, bg="#18181b", padx=10, pady=3)
        f_bat.pack(side="right", padx=4)
        self.lbl_bat_v = tk.Label(f_bat, text="🔋 --.-- V (--%)", bg="#18181b", fg="#4ade80", font=("Consolas", 11, "bold"))
        self.lbl_bat_v.pack(side="left", padx=(0, 8))
        self.lbl_bat_i = tk.Label(f_bat, text="⚡ 0.000 A", bg="#18181b", fg="#38bdf8", font=("Consolas", 11, "bold"))
        self.lbl_bat_i.pack(side="left")

    # =========================================================================
    # 2. PESTAÑAS PRINCIPALES (MÓVIL Y LANZADOR)
    # =========================================================================
    def _construir_pestanas(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=6)

        self.tab_movil = tk.Frame(self.notebook, bg="#18181b")
        self.tab_lanzador = tk.Frame(self.notebook, bg="#18181b")

        self.notebook.add(self.tab_movil, text=" 🚗 Unidad Móvil (MRU / MRUV / MCU & Perimetral) ")
        self.notebook.add(self.tab_lanzador, text=" 🎯 Unidad del Lanzador (Retracción / Ángulo / Gatillo / v₀) ")

        self._construir_tab_movil()
        self._construir_tab_lanzador()

    # -------------------------------------------------------------------------
    # PESTAÑA 1: UNIDAD MÓVIL
    # -------------------------------------------------------------------------
    def _construir_tab_movil(self):
        f_top = tk.Frame(self.tab_movil, bg="#18181b")
        f_top.pack(fill="x", padx=10, pady=8)

        f_tele = tk.LabelFrame(f_top, text=" Telemetría de Tracción Diferencial (Izq: Bus 1 Wire1 | Der: Bus 0 Wire) ",
                               bg="#27272a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        f_tele.pack(side="left", fill="both", expand=True, padx=(0, 8))

        self.lbl_rpm_izq = tk.Label(f_tele, text="Rueda Izq:   0.0 RPM ( 0.00 m/s)", bg="#27272a", fg="#ffffff", font=("Consolas", 12, "bold"))
        self.lbl_rpm_izq.grid(row=0, column=0, sticky="w", padx=8, pady=2)

        self.lbl_rpm_der = tk.Label(f_tele, text="Rueda Der:   0.0 RPM ( 0.00 m/s)", bg="#27272a", fg="#ffffff", font=("Consolas", 12, "bold"))
        self.lbl_rpm_der.grid(row=1, column=0, sticky="w", padx=8, pady=2)

        self.lbl_modo_movil = tk.Label(f_tele, text="Estado: EN REPOSO (IDLE)", bg="#27272a", fg="#fbbf24", font=("Segoe UI", 10, "bold"))
        self.lbl_modo_movil.grid(row=0, column=1, padx=20, sticky="w")

        self.prog_bar = ttk.Progressbar(f_tele, orient="horizontal", length=180, mode="determinate", maximum=1000)
        self.prog_bar.grid(row=1, column=1, padx=20, pady=4)

        btn_estop = tk.Button(f_top, text="🛑 PARO DE\nEMERGENCIA", command=self._paro_emergencia_movil,
                              bg="#dc2626", fg="#ffffff", font=("Segoe UI", 12, "bold"), width=14, relief="flat")
        btn_estop.pack(side="right", fill="y")

        # Fila central: Perfiles MRU, MRUV y MCU en 3 columnas
        f_perfiles = tk.Frame(self.tab_movil, bg="#18181b")
        f_perfiles.pack(fill="x", padx=10, pady=6)

        # --- Columna 1: Perfil MRU ---
        lf_mru = tk.LabelFrame(f_perfiles, text=" Perfil MRU (Velocidad Constante) ", bg="#27272a", fg="#4ade80",
                               font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        lf_mru.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(lf_mru, text="Velocidad v (m/s):", bg="#27272a", fg="#e4e4e7").grid(row=0, column=0, sticky="w", pady=4)
        self.var_mru_v = tk.StringVar(value="0.35")
        ttk.Entry(lf_mru, textvariable=self.var_mru_v, width=8, font=("Consolas", 10, "bold")).grid(row=0, column=1, pady=4)

        tk.Label(lf_mru, text="Duración t (s):", bg="#27272a", fg="#e4e4e7").grid(row=1, column=0, sticky="w", pady=4)
        self.var_mru_t = tk.StringVar(value="4.0")
        ttk.Entry(lf_mru, textvariable=self.var_mru_t, width=8, font=("Consolas", 10, "bold")).grid(row=1, column=1, pady=4)

        self.lbl_mru_dist = tk.Label(lf_mru, text="Distancia teórica x = 1.40 m", bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 9))
        self.lbl_mru_dist.grid(row=2, column=0, columnspan=2, pady=6)

        tk.Button(lf_mru, text="▶ Ejecutar MRU", command=self._ejecutar_mru, bg="#059669", fg="#ffffff",
                  font=("Segoe UI", 9, "bold"), relief="flat", width=18).grid(row=3, column=0, columnspan=2, pady=8)

        # --- Columna 2: Perfil MRUV ---
        lf_mruv = tk.LabelFrame(f_perfiles, text=" Perfil MRUV (Aceleración Uniforme) ", bg="#27272a", fg="#38bdf8",
                                font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        lf_mruv.pack(side="left", fill="both", expand=True, padx=6)

        tk.Label(lf_mruv, text="Vel. Inicial v₀ (m/s):", bg="#27272a", fg="#e4e4e7").grid(row=0, column=0, sticky="w", pady=3)
        self.var_mruv_v0 = tk.StringVar(value="0.15")
        ttk.Entry(lf_mruv, textvariable=self.var_mruv_v0, width=8, font=("Consolas", 10, "bold")).grid(row=0, column=1, pady=3)

        tk.Label(lf_mruv, text="Vel. Final v_f (m/s):", bg="#27272a", fg="#e4e4e7").grid(row=1, column=0, sticky="w", pady=3)
        self.var_mruv_vf = tk.StringVar(value="0.65")
        ttk.Entry(lf_mruv, textvariable=self.var_mruv_vf, width=8, font=("Consolas", 10, "bold")).grid(row=1, column=1, pady=3)

        tk.Label(lf_mruv, text="Duración t (s):", bg="#27272a", fg="#e4e4e7").grid(row=2, column=0, sticky="w", pady=3)
        self.var_mruv_t = tk.StringVar(value="5.0")
        ttk.Entry(lf_mruv, textvariable=self.var_mruv_t, width=8, font=("Consolas", 10, "bold")).grid(row=2, column=1, pady=3)

        self.lbl_mruv_acc = tk.Label(lf_mruv, text="a = 0.100 m/s² | x = 2.00 m", bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 9))
        self.lbl_mruv_acc.grid(row=3, column=0, columnspan=2, pady=4)

        tk.Button(lf_mruv, text="▶ Ejecutar MRUV", command=self._ejecutar_mruv, bg="#0284c7", fg="#ffffff",
                  font=("Segoe UI", 9, "bold"), relief="flat", width=18).grid(row=4, column=0, columnspan=2, pady=4)

        # --- Columna 3: Perfil MCU y Giro sobre su Propio Eje ---
        lf_mcu = tk.LabelFrame(f_perfiles, text=" Perfil MCU y Giro sobre Propio Eje ", bg="#27272a", fg="#c084fc",
                               font=("Segoe UI", 10, "bold"), padx=10, pady=10)
        lf_mcu.pack(side="left", fill="both", expand=True, padx=(6, 0))

        tk.Label(lf_mcu, text="Modalidad MCU:", bg="#27272a", fg="#fde047", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        self.var_mcu_modo = tk.StringVar(value="Círculo con Radio R")
        self.combo_mcu_modo = ttk.Combobox(
            lf_mcu,
            textvariable=self.var_mcu_modo,
            values=[
                "Círculo con Radio R",
                "Propio Eje (Por Tiempo)",
                "Propio Eje (Por Ángulo °)"
            ],
            width=21,
            state="readonly"
        )
        self.combo_mcu_modo.grid(row=0, column=1, pady=2)
        self.combo_mcu_modo.bind("<<ComboboxSelected>>", self._on_mcu_modo_changed)

        tk.Label(lf_mcu, text="Velocidad Rueda v (m/s):", bg="#27272a", fg="#e4e4e7").grid(row=1, column=0, sticky="w", pady=2)
        self.var_mcu_v = tk.StringVar(value="0.30")
        ttk.Entry(lf_mcu, textvariable=self.var_mcu_v, width=8, font=("Consolas", 10, "bold")).grid(row=1, column=1, sticky="w", pady=2)

        self.lbl_mcu_param2 = tk.Label(lf_mcu, text="Radio Giro R (m):", bg="#27272a", fg="#e4e4e7")
        self.lbl_mcu_param2.grid(row=2, column=0, sticky="w", pady=2)
        self.var_mcu_r = tk.StringVar(value="0.35")
        self.entry_mcu_r = ttk.Entry(lf_mcu, textvariable=self.var_mcu_r, width=8, font=("Consolas", 10, "bold"))
        self.entry_mcu_r.grid(row=2, column=1, sticky="w", pady=2)

        self.lbl_mcu_param3 = tk.Label(lf_mcu, text="Sentido / Duración (s):", bg="#27272a", fg="#e4e4e7")
        self.lbl_mcu_param3.grid(row=3, column=0, sticky="w", pady=2)
        f_mcu_sub = tk.Frame(lf_mcu, bg="#27272a")
        f_mcu_sub.grid(row=3, column=1, sticky="w", pady=2)
        self.var_mcu_dir = tk.StringVar(value="CW")
        ttk.Combobox(f_mcu_sub, textvariable=self.var_mcu_dir, values=["CW", "CCW"], width=5, state="readonly").pack(side="left", padx=(0, 4))
        self.var_mcu_t = tk.StringVar(value="5.0")
        self.entry_mcu_t = ttk.Entry(f_mcu_sub, textvariable=self.var_mcu_t, width=6, font=("Consolas", 9, "bold"))
        self.entry_mcu_t.pack(side="left")

        self.lbl_mcu_info = tk.Label(lf_mcu, text="ω = 0.86 rad/s | a_c = 0.26 m/s²", bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 9))
        self.lbl_mcu_info.grid(row=4, column=0, columnspan=2, pady=3)

        f_btns_mcu = tk.Frame(lf_mcu, bg="#27272a")
        f_btns_mcu.grid(row=5, column=0, columnspan=2, pady=3)
        tk.Button(f_btns_mcu, text="▶ Ejecutar MCU", command=self._ejecutar_mcu, bg="#7c3aed", fg="#ffffff",
                  font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=3)
        tk.Button(f_btns_mcu, text="🔄 Girar en Propio Eje Ya", command=self._ejecutar_giro_propio_eje_directo,
                  bg="#9333ea", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=3)

        # Fila inferior: Placa Perimetral Frontal (PCF8574 - 0x20)
        lf_perim = tk.LabelFrame(self.tab_movil, text=" Placa Perimetral Frontal (PCF8574 @ 0x20 - Switches & Ópticos CNY70) ",
                                 bg="#27272a", fg="#fde047", font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        lf_perim.pack(fill="x", padx=10, pady=8)

        self.var_freno_perim = tk.BooleanVar(value=True)
        chk_perim = tk.Checkbutton(lf_perim, text="Frenado automático de emergencia al detectar impacto frontal",
                                   variable=self.var_freno_perim, bg="#27272a", fg="#ffffff",
                                   selectcolor="#18181b", activebackground="#27272a", font=("Segoe UI", 9, "bold"))
        chk_perim.pack(anchor="w", pady=(0, 8))

        f_bits = tk.Frame(lf_perim, bg="#27272a")
        f_bits.pack(fill="x")
        nombres_sensores = [
            "P0: Switch Frontal Izq",
            "P1: Switch Frontal Der",
            "P2: CNY70 Frontal Izq",
            "P3: CNY70 Frontal Der"
        ]
        self.lbls_perim = []
        for nombre in enumerate(nombres_sensores):
            lbl = tk.Label(f_bits, text=f"{nombre[1]}\nLIBRE", bg="#3f3f46", fg="#e4e4e7",
                           font=("Segoe UI", 9, "bold"), height=2, relief="flat")
            lbl.pack(side="left", fill="x", expand=True, padx=4)
            self.lbls_perim.append(lbl)

    # -------------------------------------------------------------------------
    # PESTAÑA 2: UNIDAD DEL LANZADOR PARABÓLICO
    # -------------------------------------------------------------------------
    def _construir_tab_lanzador(self):
        # 1. Cronógrafo Balístico (Velocidad de Salida de la Pelota - CNY70 IO5/IO6)
        lf_crono = tk.LabelFrame(self.tab_lanzador, text=" Cronógrafo Balístico: Velocidad de Salida de la Pelota v₀ (CNY70: Separación 8 mm) ",
                                 bg="#27272a", fg="#34d399", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        lf_crono.pack(fill="x", padx=10, pady=6)

        f_crono_top = tk.Frame(lf_crono, bg="#27272a")
        f_crono_top.pack(fill="x")

        self.lbl_v0_ms = tk.Label(f_crono_top, text="0.000 m/s", bg="#18181b", fg="#10b981",
                                  font=("Consolas", 26, "bold"), width=12, relief="solid", bd=1)
        self.lbl_v0_ms.pack(side="left", padx=6, pady=4)

        f_crono_info = tk.Frame(f_crono_top, bg="#27272a")
        f_crono_info.pack(side="left", fill="both", expand=True, padx=10)

        self.lbl_v0_kmh = tk.Label(f_crono_info, text="Equivalente: 0.00 km/h | Δt: 0 µs", bg="#27272a", fg="#ffffff", font=("Segoe UI", 10, "bold"), anchor="w")
        self.lbl_v0_kmh.pack(fill="x")

        self.lbl_estado_cny = tk.Label(f_crono_info, text="Barreras Ópticas -> S1 (IO5): LIBRE | S2 (IO6): LIBRE", bg="#27272a", fg="#fbbf24", font=("Segoe UI", 9, "bold"), anchor="w")
        self.lbl_estado_cny.pack(fill="x", pady=2)

        tk.Button(f_crono_top, text="🔔 Probar Buzzer", command=lambda: self._enviar_cmd_lanzador(2, 0, 0),
                  bg="#7c3aed", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=6).pack(side="right", padx=4)

        cols = ("num", "hora", "comp_mm", "ang_tiro", "dt_us", "v_ms", "v_kmh")
        self.tree_shots = ttk.Treeview(lf_crono, columns=cols, show="headings", height=3)
        for col, txt, w in [
            ("num", "#", 40), ("hora", "Hora", 85), ("comp_mm", "Compresión (mm)", 115),
            ("ang_tiro", "Ángulo Tiro (°)", 105), ("dt_us", "Δt (µs)", 90),
            ("v_ms", "v₀ (m/s)", 100), ("v_kmh", "v₀ (km/h)", 100)
        ]:
            self.tree_shots.heading(col, text=txt)
            self.tree_shots.column(col, width=w, anchor="center")
        self.tree_shots.pack(fill="x", pady=4)

        # 2. Control de Retracción / Compresión del Resorte (IO9 - Siempre Activo)
        lf_ret = tk.LabelFrame(self.tab_lanzador, text=" 1. Retracción / Compresión del Resorte (Servo IO9 - PWM Continuo) ",
                               bg="#27272a", fg="#fde047", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        lf_ret.pack(fill="x", padx=10, pady=5)

        f_ret_btns = tk.Frame(lf_ret, bg="#27272a")
        f_ret_btns.pack(fill="x", pady=2)

        tk.Button(f_ret_btns, text="Tope Inicial (20°)", command=lambda: self._set_retractil_deg(20),
                  bg="#3f3f46", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(f_ret_btns, text="Posición 0.0 mm (45°)", command=lambda: self._set_retractil_deg(45),
                  bg="#059669", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(f_ret_btns, text=f"Máximo Riel {MAX_COMP_MM:.1f} mm (125°)", command=lambda: self._set_retractil_deg(125),
                  bg="#d97706", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)

        f_ret_inputs = tk.Frame(lf_ret, bg="#27272a")
        f_ret_inputs.pack(fill="x", pady=6)

        tk.Label(f_ret_inputs, text="Compresión deseada (mm):", bg="#27272a", fg="#ffffff").pack(side="left", padx=4)
        self.var_ret_mm = tk.StringVar(value="0.0")
        e_mm = ttk.Entry(f_ret_inputs, textvariable=self.var_ret_mm, width=7, font=("Consolas", 10, "bold"))
        e_mm.pack(side="left", padx=4)
        e_mm.bind("<KeyRelease>", self._on_mm_changed)

        tk.Label(f_ret_inputs, text="↔ Ángulo Servo IO9 (20° a 125°):", bg="#27272a", fg="#ffffff").pack(side="left", padx=10)
        self.var_ret_deg = tk.StringVar(value="45")
        e_deg = ttk.Entry(f_ret_inputs, textvariable=self.var_ret_deg, width=7, font=("Consolas", 10, "bold"))
        e_deg.pack(side="left", padx=4)
        e_deg.bind("<KeyRelease>", self._on_deg_changed)

        tk.Button(f_ret_inputs, text="Aplicar Retracción", command=self._aplicar_retractil,
                  bg="#0284c7", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=12).pack(side="right", padx=6)

        # 3. Control de Ángulo de Lanzamiento Parabólico (IO10 - Bajo demanda 800 ms)
        lf_can = tk.LabelFrame(self.tab_lanzador, text=" 2. Ángulo de Lanzamiento Parabólico (Servo IO10 - Pulso 800 ms con Enclavamiento) ",
                               bg="#27272a", fg="#38bdf8", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        lf_can.pack(fill="x", padx=10, pady=5)

        f_can = tk.Frame(lf_can, bg="#27272a")
        f_can.pack(fill="x", pady=4)

        tk.Button(f_can, text="0° Horizontal (Servo 90°)", command=lambda: self._set_canon_tiro(0),
                  bg="#3f3f46", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(f_can, text="45° Alcance Máx (Servo 135°)", command=lambda: self._set_canon_tiro(45),
                  bg="#3f3f46", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(f_can, text="90° Vertical (Servo 180°)", command=lambda: self._set_canon_tiro(90),
                  bg="#3f3f46", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=8).pack(side="left", padx=4)

        tk.Label(f_can, text="Ángulo Tiro (0°-90°):", bg="#27272a", fg="#ffffff").pack(side="left", padx=(14, 4))
        self.var_tiro_deg = tk.StringVar(value="0")
        ttk.Spinbox(f_can, from_=0, to=90, textvariable=self.var_tiro_deg, width=5, font=("Consolas", 10, "bold")).pack(side="left", padx=4)

        self.lbl_estado_io10 = tk.Label(f_can, text="IO10: CORTE LOW", bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 8, "bold"))
        self.lbl_estado_io10.pack(side="right", padx=6)

        tk.Button(f_can, text="Cambiar Ángulo", command=self._aplicar_canon,
                  bg="#059669", fg="#ffffff", font=("Segoe UI", 9, "bold"), relief="flat", padx=10).pack(side="right", padx=6)

        # 4. Control del Gatillo (IO8 - LEDC directo con cola FreeRTOS)
        lf_gat = tk.LabelFrame(self.tab_lanzador, text=" 3. Mecanismo de Gatillo (Servo IO8 - Respuesta Inmediata LEDC 800 ms) ",
                               bg="#27272a", fg="#f87171", font=("Segoe UI", 10, "bold"), padx=12, pady=8)
        lf_gat.pack(fill="x", padx=10, pady=5)

        f_gat = tk.Frame(lf_gat, bg="#27272a")
        f_gat.pack(fill="x")

        tk.Button(f_gat, text="🔒 ANCLAR (90°)", command=lambda: self._enviar_cmd_lanzador(1, 8, 90),
                  bg="#0284c7", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=16, relief="flat", pady=4).pack(side="left", padx=4)

        tk.Button(f_gat, text="🔓 LIBERAR GATILLO", command=self._disparar_gatillo_manual,
                  bg="#ea580c", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=18, relief="flat", pady=4).pack(side="left", padx=4)

        tk.Button(f_gat, text="🚀 DISPARO + RE-ANCLAR AUTO", command=self._disparar_y_reanclar_auto,
                  bg="#dc2626", fg="#ffffff", font=("Segoe UI", 10, "bold"), width=25, relief="flat", pady=4).pack(side="left", padx=4)

        tk.Label(f_gat, text="Áng. Disparo (°):", bg="#27272a", fg="#e4e4e7", font=("Segoe UI", 9)).pack(side="left", padx=(8, 2))
        self.var_gat_lib_deg = tk.StringVar(value="108")
        ttk.Spinbox(f_gat, from_=98, to=145, textvariable=self.var_gat_lib_deg, width=4, font=("Consolas", 10, "bold")).pack(side="left", padx=2)

        self.lbl_estado_io8 = tk.Label(f_gat, text="IO8: CORTE LOW", bg="#27272a", fg="#a1a1aa", font=("Segoe UI", 8, "bold"))
        self.lbl_estado_io8.pack(side="right", padx=6)

    # =========================================================================
    # LÓGICA DE CONVERSIÓN Y COMANDOS (MÓVIL Y LANZADOR)
    # =========================================================================
    def _on_mcu_modo_changed(self, event=None):
        modo = self.var_mcu_modo.get()
        if modo == "Círculo con Radio R":
            self.lbl_mcu_param2.config(text="Radio Giro R (m):")
            self.entry_mcu_r.config(state="normal")
            self.var_mcu_r.set("0.35")
            self.entry_mcu_t.config(state="normal")
        elif modo == "Propio Eje (Por Tiempo)":
            self.lbl_mcu_param2.config(text="Radio R (Fijo 0 m):")
            self.var_mcu_r.set("0.00")
            self.entry_mcu_r.config(state="disabled")
            self.entry_mcu_t.config(state="normal")
        elif modo == "Propio Eje (Por Ángulo °)":
            self.lbl_mcu_param2.config(text="Ángulo Giro (°):")
            self.entry_mcu_r.config(state="normal")
            self.var_mcu_r.set("180")
            self.entry_mcu_t.config(state="disabled")

    def _disparar_gatillo_manual(self):
        try:
            ang = max(95, min(160, int(float(self.var_gat_lib_deg.get().strip()))))
        except ValueError:
            ang = 108
        self._enviar_cmd_lanzador(1, 8, ang)

    def _disparar_y_reanclar_auto(self):
        try:
            ang = max(95, min(160, int(float(self.var_gat_lib_deg.get().strip()))))
        except ValueError:
            ang = 108
        # action=4 ejecuta Liberación en ang y re-ancla a 90° tras 950 ms en el ESP32
        self._enviar_cmd_lanzador(4, 8, ang)

    def _on_mm_changed(self, event=None):
        try:
            mm = max(0.0, min(MAX_COMP_MM, float(self.var_ret_mm.get().strip())))
            deg = int(round(ANGULO_COMP_0MM + (mm / PASO_MM_POR_GRADO)))
            self.var_ret_deg.set(str(deg))
        except ValueError:
            pass

    def _on_deg_changed(self, event=None):
        try:
            deg = max(20.0, min(ANGULO_COMP_MAX, float(self.var_ret_deg.get().strip())))
            mm = 0.0 if deg < ANGULO_COMP_0MM else (deg - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO
            self.var_ret_mm.set(f"{mm:.1f}")
        except ValueError:
            pass

    def _set_retractil_deg(self, deg):
        self.var_ret_deg.set(str(deg))
        self._on_deg_changed()
        self._aplicar_retractil()

    def _aplicar_retractil(self):
        try:
            deg = max(20, min(125, int(float(self.var_ret_deg.get().strip()))))
            self._enviar_cmd_lanzador(1, 9, deg)
        except ValueError:
            messagebox.showerror("Error", "Ingresa un ángulo válido para el servo retráctil (20° a 125°).")

    def _set_canon_tiro(self, tiro_deg):
        self.var_tiro_deg.set(str(tiro_deg))
        self._aplicar_canon()

    def _aplicar_canon(self):
        try:
            tiro = max(0, min(90, int(float(self.var_tiro_deg.get().strip()))))
            servo_ang = 90 + tiro
            self._enviar_cmd_lanzador(1, 10, servo_ang)
        except ValueError:
            messagebox.showerror("Error", "Ingresa un ángulo de tiro entre 0° y 90°.")

    def _ejecutar_mru(self):
        try:
            v = float(self.var_mru_v.get())
            t = max(0.2, float(self.var_mru_t.get()))
            self.lbl_mru_dist.config(text=f"Distancia teórica x = {v * t:.2f} m")
            self._enviar_cmd_movil(mode=1, p1=v, p2=0.0, dur=t)
        except ValueError:
            messagebox.showerror("Error", "Verifica los valores numéricos de MRU.")

    def _ejecutar_mruv(self):
        try:
            v0 = float(self.var_mruv_v0.get())
            vf = float(self.var_mruv_vf.get())
            t  = max(0.2, float(self.var_mruv_t.get()))
            a  = (vf - v0) / t
            x  = ((v0 + vf) / 2.0) * t
            self.lbl_mruv_acc.config(text=f"a = {a:.3f} m/s² | x = {x:.2f} m")
            self._enviar_cmd_movil(mode=2, p1=v0, p2=vf, dur=t)
        except ValueError:
            messagebox.showerror("Error", "Verifica los valores numéricos de MRUV.")

    def _ejecutar_giro_propio_eje_directo(self):
        """Fuerza inmediatamente un giro sobre el propio eje usando la velocidad y duración actuales."""
        self.var_mcu_modo.set("Propio Eje (Por Tiempo)")
        self._on_mcu_modo_changed()
        self._ejecutar_mcu()

    def _ejecutar_mcu(self):
        try:
            modo = self.var_mcu_modo.get()
            v = abs(float(self.var_mcu_v.get()))
            if v < 0.08:
                messagebox.showwarning("Velocidad muy baja", "Usa al menos v = 0.15 m/s para vencer la fricción en giros.")
                return

            sentido = 1.0 if self.var_mcu_dir.get() == "CW" else -1.0

            if modo == "Propio Eje (Por Tiempo)":
                t = max(0.2, float(self.var_mcu_t.get()))
                v_l = sentido * v
                v_r = -sentido * v
                omega = (2.0 * v) / ANCHO_VIA_M
                grados_tot = math.degrees(omega * t)
                self.lbl_mcu_info.config(text=f"Propio Eje: ω = {omega:.2f} rad/s | Giro ≈ {grados_tot:.0f}°")
                self._enviar_cmd_movil(mode=3, p1=v_l, p2=v_r, dur=t)

            elif modo == "Propio Eje (Por Ángulo °)":
                ang_grados = max(10.0, float(self.var_mcu_r.get()))
                ang_rad = math.radians(ang_grados)
                omega = (2.0 * v) / ANCHO_VIA_M
                t = max(0.2, ang_rad / omega)
                self.var_mcu_t.set(f"{t:.2f}")
                v_l = sentido * v
                v_r = -sentido * v
                self.lbl_mcu_info.config(text=f"Giro {ang_grados:.0f}° en t = {t:.2f} s (ω = {omega:.2f} rad/s)")
                self._enviar_cmd_movil(mode=3, p1=v_l, p2=v_r, dur=t)

            else:  # Círculo con Radio R
                r = float(self.var_mcu_r.get())
                t = max(0.2, float(self.var_mcu_t.get()))
                if r <= 0.02:
                    v_l = sentido * v
                    v_r = -sentido * v
                    omega = (2.0 * v) / ANCHO_VIA_M
                    ac = 0.0
                else:
                    omega = v / r
                    ac = (v * v) / r
                    delta_v = (omega * ANCHO_VIA_M) / 2.0
                    if sentido > 0:  # Horario CW (rueda izquierda exterior más rápida)
                        v_l = v + delta_v
                        v_r = v - delta_v
                    else:            # Antihorario CCW (rueda derecha exterior más rápida)
                        v_l = v - delta_v
                        v_r = v + delta_v
                self.lbl_mcu_info.config(text=f"ω = {omega:.2f} rad/s | a_c = {ac:.2f} m/s²")
                self._enviar_cmd_movil(mode=3, p1=v_l, p2=v_r, dur=t)

        except ValueError:
            messagebox.showerror("Error", "Verifica los valores numéricos de MCU.")

    def _paro_emergencia_movil(self):
        self._enviar_cmd_movil(mode=0, p1=0.0, p2=0.0, dur=0.0)

    def _enviar_cmd_movil(self, mode, p1, p2, dur):
        payload = {
            "target": 1,
            "mode": mode,
            "perim_stop": 1 if self.var_freno_perim.get() else 0,
            "p1": round(p1, 4),
            "p2": round(p2, 4),
            "dur": round(dur, 2)
        }
        self._enviar_json(payload)

    def _enviar_cmd_lanzador(self, action, pin, ang):
        payload = {
            "target": 2,
            "action": action,
            "pin": pin,
            "ang": int(ang)
        }
        self._enviar_json(payload)

    # =========================================================================
    # COMUNICACIÓN SERIAL Y PROCESAMIENTO DE TELEMETRÍA
    # =========================================================================
    def _actualizar_puertos(self):
        puertos = [p.device for p in serial.tools.list_ports.comports()]
        self.combo_puertos["values"] = puertos
        if puertos:
            self.combo_puertos.current(0)

    def _toggle_conexion(self):
        if not self.running:
            puerto = self.combo_puertos.get()
            if not puerto:
                messagebox.showwarning("Puerto requerido", "Selecciona el puerto del Dongle ESP8266.")
                return
            try:
                self.serial_port = serial.Serial(puerto, 115200, timeout=0.05)
                self.serial_port.reset_input_buffer()
                self.running = True
                self.btn_conectar.config(text="Desconectar Dongle", bg="#dc2626")
                threading.Thread(target=self._hilo_lectura_serial, daemon=True).start()
            except Exception as e:
                messagebox.showerror("Error de Conexión", f"No se pudo abrir {puerto}:\n{e}")
        else:
            self.running = False
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
            self.btn_conectar.config(text="Conectar Dongle", bg="#0284c7")

    def _enviar_json(self, data):
        if self.running and self.serial_port and self.serial_port.is_open:
            try:
                with self.serial_lock:
                    linea = json.dumps(data) + "\n"
                    self.serial_port.write(linea.encode("utf-8"))
            except Exception as e:
                print(f"Error TX Serial: {e}")
        else:
            messagebox.showwarning("Dongle desconectado", "Conecta primero el Dongle ESP8266.")

    def _hilo_lectura_serial(self):
        buffer = ""
        while self.running:
            if self.serial_port and self.serial_port.is_open:
                try:
                    with self.serial_lock:
                        n = self.serial_port.in_waiting
                        chunk = self.serial_port.read(n).decode("utf-8", errors="ignore") if n > 0 else ""
                    if chunk:
                        buffer += chunk
                        while "\n" in buffer:
                            linea, buffer = buffer.split("\n", 1)
                            linea = linea.strip()
                            if linea.startswith("{") and linea.endswith("}"):
                                try:
                                    d = json.loads(linea)
                                    self.root.after(0, self._procesar_json_entrante, d)
                                except json.JSONDecodeError:
                                    pass
                except Exception:
                    pass
            time.sleep(0.01)

    def _procesar_json_entrante(self, d):
        src = d.get("src", 0)

        # --- TELEMETRÍA DE LA UNIDAD MÓVIL (src == 1) ---
        if src == 1:
            self.last_rx_movil = time.time()
            vbat = float(d.get("vbat", 0.0))
            ibat = float(d.get("ibat", 0.0))
            pct = int(max(0.0, min(100.0, ((vbat - 12.8) / (16.8 - 12.8)) * 100.0)))

            self.lbl_bat_v.config(text=f"🔋 {vbat:.2f} V ({pct}%)")
            self.lbl_bat_i.config(text=f"⚡ {ibat:.3f} A")

            rpm_l = float(d.get("rpm_l", 0.0))
            rpm_r = float(d.get("rpm_r", 0.0))
            v_l = (rpm_l * 2.0 * 3.14159 * 0.030) / 60.0
            v_r = (rpm_r * 2.0 * 3.14159 * 0.030) / 60.0

            self.lbl_rpm_izq.config(text=f"Rueda Izq: {rpm_l:6.1f} RPM ({v_l:5.2f} m/s)")
            self.lbl_rpm_der.config(text=f"Rueda Der: {rpm_r:6.1f} RPM ({v_r:5.2f} m/s)")

            modos_txt = {
                0: "Estado: EN REPOSO (IDLE)",
                1: "Estado: EJECUTANDO MRU",
                2: "Estado: EJECUTANDO MRUV",
                3: "Estado: EJECUTANDO MCU",
                4: "Estado: CONTROL MANUAL",
                5: "⚠️ FRENO POR COLISIÓN PERIMETRAL"
            }
            modo = int(d.get("mode", 0))
            self.lbl_modo_movil.config(
                text=modos_txt.get(modo, "Estado: ACTIVO"),
                fg="#ef4444" if modo == 5 else ("#4ade80" if modo in (1, 2, 3) else "#fbbf24")
            )
            self.prog_bar["value"] = int(d.get("prog", 0))

            perim = int(d.get("perim", 0xFF))
            nombres_cortos = ["P0: Switch Izq", "P1: Switch Der", "P2: CNY70 Izq", "P3: CNY70 Der"]
            for i in range(4):
                activo = ((perim >> i) & 1) == 0
                self.lbls_perim[i].config(
                    text=f"{nombres_cortos[i]}\n{'🟢 DETECTADO' if activo else '⚪ LIBRE'}",
                    bg="#16a34a" if activo else "#3f3f46"
                )

        # --- TELEMETRÍA DE LA UNIDAD DEL LANZADOR (src == 2) ---
        elif src == 2:
            self.last_rx_lanzador = time.time()
            flags = int(d.get("flags", 0))
            act8   = bool(flags & (1 << 0))
            act10  = bool(flags & (1 << 1))
            cny1   = bool(flags & (1 << 2))
            cny2   = bool(flags & (1 << 3))
            armado = bool(flags & (1 << 4))

            self.lbl_estado_io8.config(
                text="IO8: PWM ACTIVO (800ms)" if act8 else "IO8: CORTE LOW",
                fg="#4ade80" if act8 else "#a1a1aa"
            )
            self.lbl_estado_io10.config(
                text="IO10: PWM ACTIVO (800ms)" if act10 else "IO10: CORTE LOW",
                fg="#4ade80" if act10 else "#a1a1aa"
            )

            txt_cny = f"Barreras Ópticas -> S1 (IO5): {'DETECTADO' if cny1 else 'LIBRE'} | S2 (IO6): {'DETECTADO' if cny2 else 'LIBRE'}"
            if armado:
                txt_cny += "  [⚡ MIDIENDO Δt...]"
            self.lbl_estado_cny.config(text=txt_cny)

            shot_id = int(d.get("shot_id", 0))
            if shot_id > 0 and shot_id != self.ultimo_shot_id:
                self.ultimo_shot_id = shot_id
                dt_us = int(d.get("dt_us", 0))
                v_ms  = float(d.get("v_ms", 0.0))
                v_kmh = v_ms * 3.6

                self.lbl_v0_ms.config(text=f"{v_ms:.3f} m/s")
                self.lbl_v0_kmh.config(text=f"Equivalente: {v_kmh:.2f} km/h | Δt: {dt_us} µs")

                ang_ret = int(d.get("ret", 45))
                comp_mm = max(0.0, (ang_ret - ANGULO_COMP_0MM) * PASO_MM_POR_GRADO)
                ang_tiro = max(0, int(d.get("can", 90)) - 90)
                hora = datetime.now().strftime("%H:%M:%S")

                self.tree_shots.insert("", 0, values=(
                    shot_id, hora, f"{comp_mm:.1f} mm ({ang_ret}°)",
                    f"{ang_tiro}°", dt_us, f"{v_ms:.3f}", f"{v_kmh:.2f}"
                ))

    def _loop_watchdog(self):
        ahora = time.time()
        movil_ok = (ahora - self.last_rx_movil) < 2.5
        lanz_ok  = (ahora - self.last_rx_lanzador) < 2.5

        self.lbl_link_movil.config(
            text="🟢 MÓVIL: ENLAZADO" if movil_ok else "🔴 MÓVIL: OFF",
            bg="#065f46" if movil_ok else "#3f3f46",
            fg="#ffffff" if movil_ok else "#fca5a5"
        )
        self.lbl_link_lanz.config(
            text="🟢 LANZADOR: ENLAZADO" if lanz_ok else "🔴 LANZADOR: OFF",
            bg="#065f46" if lanz_ok else "#3f3f46",
            fg="#ffffff" if lanz_ok else "#fca5a5"
        )
        self.root.after(500, self._loop_watchdog)


if __name__ == "__main__":
    root = tk.Tk()
    app = FiFuLabApp(root)
    root.mainloop()