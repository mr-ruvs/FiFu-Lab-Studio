# FiFuLab Studio — Software de Escritorio (PySide6 / Qt6)

Aplicación gráfica moderna de escritorio para la adquisición de datos, control cinemático, telemetría bidireccional y modelado físico experimental en tiempo real para la plataforma **FiFuLab**.

---

## 🚀 Requisitos del Sistema
* **Sistema Operativo:** Windows 10 / 11, Linux o macOS.
* **Entorno de Desarrollo:** Visual Studio Code.
* **Python:** Versión 3.10 o superior (recomendado Python 3.10 o 3.11).
* **Dependencias Principales:** `PySide6`, `numpy`, `pyqtgraph`, `pyserial`.

---

## 📦 Instalación y Ejecución

1. Abrir esta carpeta (`FiFuLab`) en **Visual Studio Code**.
2. Abrir una terminal integrada (`Ctrl + ~`) y crear un entorno virtual:
   ```powershell
   # En Windows PowerShell:
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
3. Instalar las dependencias del proyecto:
   ```bash
   pip install -r requirements.txt
   ```
4. Conectar el Dongle USB ESP8266 y ejecutar la aplicación:
   ```bash
   python main.py
   ```

---

## 🗂️ Arquitectura del Software

```text
FiFuLab/
├── main.py                     # Punto de entrada principal (QApplication, estilos y fuente base)
├── requirements.txt            # Dependencias oficiales de Python
├── ui/                         # Vistas de la aplicación
│   ├── main_window.py          # Ventana principal, Navbar, StatusBar y contenedor de tabs
│   ├── dashboard_tab.py        # Pestaña 1: Dashboard General y Secuenciador Multi-Perfil
│   ├── launcher_tab.py         # Pestaña 2: Módulo Lanzador Balístico y Simulación 2D
│   ├── mobile_tab.py           # Pestaña 3: Unidad Móvil (MRU, MRUV, MCU, Movimiento Libre)
│   └── tab_sensores.py         # Pestaña 4: Diagnóstico de Sensores PCF8574 y Encoders
├── models/                     # Capa de modelo y estado global
│   ├── variables.py            # AppState reactivo, buffers numéricos y cola de perfiles
│   └── translations.py         # Diccionario bilingüe Español / Inglés
├── libs/                       # Comunicación serie e infraestructura
│   ├── esp32_client.py         # Hilo QThread de comunicación USB Serial con el Dongle
│   └── pyqtgraph/              # Librería de graficación en tiempo real embebida
├── components/                 # Componentes gráficos especializados
│   ├── canvas_widget.py        # Lienzo para dibujo libre de curvas cinemáticas
│   ├── navbar.py               # Barra superior con selector de puerto COM y conexión
│   └── modals.py               # Ventanas modales para guardado de perfiles y triggers
└── styles/                     # Temas visuales QSS (Dark Mode y Light Mode)
```

---

## 🧩 Resumen de Módulos y Pestañas

### 1. Dashboard General (`dashboard_tab.py`)
* Indicadores visuales de estado de enlace para Dongle, Móvil y Lanzador con watchdogs independientes a 2.5 segundos.
* Telemetría de batería en tiempo real: Voltaje (12.8V - 16.8V LiPo), Corriente de consumo (A) y porcentaje restante.
* **Secuenciador Multi-Perfil:** Gráfica general $v(t)$ y $x(t)$ para secuencias de movimientos en cadena, con marcadores visuales temporales y cola de ejecución interactiva.

### 2. Módulo Lanzador (`launcher_tab.py`)
* Ajuste de compresión milimétrica del resorte (engranaje $m=1\text{ mm}, Z=16$, paso $0.1396\text{ mm/°}$).
* Mecanismo de gatillo mecánico (Anclar a 90° / Liberar a 108°).
* Cronógrafo balístico por barreras ópticas con filtro de compresión mínima ($\ge 1.0\text{ mm}$).
* Gráfica de trayectoria parabólica teórica vs experimental calculando alcance máximo $X_{max}$ y altura máxima $Y_{max}$.

### 3. Unidad Móvil (`mobile_tab.py`)
* **MRU:** Selección dinámica de variable a calcular ($v, d, t$), validación física en tiempo real y ajuste de regresión (Lineal / Cuadrática con cálculo de $R^2$).
* **MRUV:** Solucionador analítico que resuelve exactamente las 3 variables ingresadas de entre las 5 disponibles ($v_0, v_f, a, d, t$), graficando vistas individuales o simultáneas ($x-t, v-t, a-t$).
* **MCU:**
  * *Giro sobre su propio eje:* Rotación angular estacionaria sin traslación 2D.
  * *Orbitar:* Órbita circular 2D centrada en el origen $(0,0)$. El robot parte del radio en $(0, \pm R)$ según el sentido de giro, superponiendo la odometría medida con la órbita teórica.
* **Movimiento Libre (Dibujo a Mano):** Lienzo táctil interactivo que deriva o integra curvas de $x(t)$, $v(t)$ o $a(t)$ y las transmite a 20 Hz en Modo 4 (Control Directo RPM) al robot físico.

### 4. Sensores y Diagnóstico (`tab_sensores.py`)
* Tarjetas interactivas con el estado de los 5 bits del expansor PCF8574: CNY70 Frontal Izq/Der (suelo/aire), Microswitches de impacto y Sensor Touch.
* Lectura directa de encoders magnéticos AS5600 y control manual de tracción.
