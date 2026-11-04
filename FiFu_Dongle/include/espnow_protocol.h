// archivo: include/espnow_protocol.h
#ifndef ESPNOW_PROTOCOL_H
#define ESPNOW_PROTOCOL_H

#include <stdint.h>

#define CANAL_WIFI       1
#define PKT_TELEMETRY    0x10
#define PKT_COMMAND      0x20

#define ID_MOVIL         1
#define ID_LANZADOR      2

// --- TELEMETRÍA UNIDAD MÓVIL (30 bytes exactos) ---
struct __attribute__((packed)) TelemetryPacketMovil {
    uint8_t  pkt_type;       // PKT_TELEMETRY (0x10)
    uint8_t  id_robot;       // ID_MOVIL (1)
    uint8_t  mode_state;     // 0:IDLE, 1:MRU, 2:MRUV, 3:MCU, 4:MANUAL, 5:COLISION_PERIM
    uint8_t  perimetral;     // Byte crudo del expansor PCF8574 (0x20)
    float    v_bat_v;        // Voltaje de batería (V) - INA226
    float    i_bat_a;        // Corriente (A) con resolución de mA - INA226
    float    rpm_l;          // RPM medida rueda izquierda (AS5600)
    float    rpm_r;          // RPM medida rueda derecha (AS5600)
    float    sp_rpm_l;       // Consigna actual RPM izquierda
    float    sp_rpm_r;       // Consigna actual RPM derecha
    uint16_t progress_pct;   // Progreso del perfil (0 a 1000 -> 0.0% a 100.0%)
};

// --- TELEMETRÍA UNIDAD LANZADOR (16 bytes exactos) ---
struct __attribute__((packed)) TelemetryPacketLanzador {
    uint8_t  pkt_type;       // PKT_TELEMETRY (0x10)
    uint8_t  id_robot;       // ID_LANZADOR (2)
    uint8_t  ang_gatillo;    // Pin 8: 90° (Anclado) / 105° (Liberado)
    uint8_t  ang_retractil;  // Pin 9: 20° (Tope), 45° (0mm) a 125° (11.2mm)
    uint8_t  ang_canon;      // Pin 10: 90° (0° tiro) a 180° (90° tiro)
    uint8_t  flags;          // Bit0:act8, Bit1:act10, Bit2:cny1, Bit3:cny2, Bit4:armado, Bit5:touch
    uint16_t shot_id;        // Contador incremental de disparos válidos
    uint32_t dt_us;          // Tiempo de vuelo entre CNY70 S1 (IO5) y S2 (IO6) en µs
    float    v_salida_ms;    // Velocidad de salida v0 = 8000.0 / dt_us (m/s)
};

// --- COMANDOS HACIA UNIDAD MÓVIL (16 bytes exactos) ---
struct __attribute__((packed)) CommandPacketMovil {
    uint8_t  pkt_type;       // PKT_COMMAND (0x20)
    uint8_t  id_robot;       // ID_MOVIL (1)
    uint8_t  cmd_mode;       // 0:STOP, 1:MRU, 2:MRUV, 3:MCU, 4:DIRECT_RPM
    uint8_t  stop_on_perim;  // 1:Frenar si placa perimetral detecta obstáculo, 0:Ignorar
    float    param1;         // MRU: v(m/s) | MRUV: v0(m/s) | MCU: v_izq(m/s) | DIRECT: rpm_izq
    float    param2;         // MRU: 0      | MRUV: vf(m/s) | MCU: v_der(m/s) | DIRECT: rpm_der
    float    duration_s;     // Tiempo de ejecución del perfil (s)
};

// --- COMANDOS HACIA UNIDAD LANZADOR (5 bytes exactos) ---
struct __attribute__((packed)) CommandPacketLanzador {
    uint8_t  pkt_type;       // PKT_COMMAND (0x20)
    uint8_t  id_robot;       // ID_LANZADOR (2)
    uint8_t  cmd_action;     // 1:MOVER_SERVO, 2:BUZZER, 3:RESET_CRONO
    uint8_t  servo_pin;      // 8 (Gatillo), 9 (Retráctil), 10 (Cañón)
    uint8_t  servo_ang;      // Ángulo objetivo (grados)
};

#endif