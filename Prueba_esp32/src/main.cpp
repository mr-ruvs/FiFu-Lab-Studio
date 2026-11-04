// archivo: Prueba_esp32/src/main.cpp (Unidad Móvil)
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "INA226.h"
#include "espnow_protocol.h"

// --- DIRECCIÓN MAC DEL DONGLE ESP8266 ---
const uint8_t dongleMac[6] = {0xCC, 0x50, 0xE3, 0x7D, 0x1F, 0x1D};

// --- PINES BUSES I2C (CORREGIDOS SEGÚN CABLEADO REAL) ---
// Bus 0 (Wire): Encoder Rueda DERECHA
#define I2C0_SDA 2
#define I2C0_SCL 3
// Bus 1 (Wire1): Encoder Rueda IZQUIERDA + INA226 (0x44) + PCF8574 (0x20)
#define I2C1_SDA 12
#define I2C1_SCL 13

#define AS5600_ADDR  0x36
#define PCF8574_ADDR 0x20

// --- PINES DRIVERS POLOLU VNH5019 (20 kHz) ---
// Motor Izquierdo (Driver A)
#define AIN1 4
#define PWMA 8
#define AIN2 9
// Motor Derecho (Driver B)
#define BIN1 5
#define PWMB 7
#define BIN2 6

#define PWM_FREQ     20000
#define PWM_RES      8
#define CH_PWMA      0
#define CH_PWMB      1
#define PWM_DEADZONE 22   // Umbral de compensación de fricción estática

// --- CONSTANTES FÍSICAS Y SINTONIZACIÓN PI (MÉTODO LAMBDA) ---
const float RADIO_RUEDA_M = 0.030f; // D = 60 mm -> r = 0.030 m
const float MS_TO_RPM     = 60.0f / (2.0f * PI * RADIO_RUEDA_M); // 318.31 RPM por m/s

// Ganancias sintonizadas por rueda (compensan asimetría de 1.8% entre motores)
const float KP_L = 0.34f, KI_L = 3.20f, KFF_L = 0.52f;
const float KP_R = 0.34f, KI_R = 3.20f, KFF_R = 0.54f;

INA226 ina226(0x44, &Wire1);
bool ina_ok = false;

SemaphoreHandle_t xMutex;

// Variables compartidas de estado y control
volatile uint8_t  modoActual      = 0; // 0:IDLE, 1:MRU, 2:MRUV, 3:MCU, 4:MANUAL, 5:COLISION
volatile bool     frenoPerimetral = true;
volatile uint8_t  estadoPerim     = 0xFF;

volatile float    spRpmL = 0.0f, spRpmR = 0.0f;
volatile float    medRpmL = 0.0f, medRpmR = 0.0f; // Magnitud medida con signo según dirección activa
float             magRpmL = 0.0f, magRpmR = 0.0f; // Magnitud positiva filtrada para el lazo PI
volatile float    vBat = 14.8f, iBat = 0.0f;
volatile uint16_t progresoPct = 0;

// Parámetros del perfil cinemático activo
volatile float    profParam1 = 0.0f;
volatile float    profParam2 = 0.0f;
volatile float    profDuracionS = 0.0f;
volatile uint32_t profInicioMs = 0;

// Variables internas PI
float integL = 0.0f, integR = 0.0f;
uint16_t prevRawL = 0, prevRawR = 0;
bool firstReadL = true, firstReadR = true;

// --- LECTURA DE HARDWARE I2C ---
uint16_t leerAS5600(TwoWire &bus, bool &ok) {
    bus.beginTransmission(AS5600_ADDR);
    bus.write(0x0C);
    if (bus.endTransmission(false) != 0) {
        ok = false;
        return 0;
    }
    if (bus.requestFrom((uint8_t)AS5600_ADDR, (uint8_t)2) != 2) {
        ok = false;
        return 0;
    }
    uint16_t high = bus.read();
    uint16_t low  = bus.read();
    ok = true;
    return ((high << 8) | low) & 0x0FFF;
}

uint8_t leerPCF8574() {
    if (Wire1.requestFrom((uint8_t)PCF8574_ADDR, (uint8_t)1) == 1) {
        return Wire1.read();
    }
    return 0xFF;
}

// --- ACCIONAMIENTO SIMÉTRICO DE MOTORES SIN INVERSIÓN ACCIDENTAL ---
void aplicarMotorIzq(int pwmMag, int dir) {
    pwmMag = constrain(pwmMag, 0, 255);
    if (pwmMag == 0 || dir == 0) {
        // Freno electromagnético simétrico a GND en ambos terminales del VNH5019
        digitalWrite(AIN1, LOW);
        digitalWrite(AIN2, LOW);
        ledcWrite(CH_PWMA, 0);
    } else if (dir > 0) {
        digitalWrite(AIN1, HIGH);
        digitalWrite(AIN2, LOW);
        ledcWrite(CH_PWMA, pwmMag);
    } else {
        digitalWrite(AIN1, LOW);
        digitalWrite(AIN2, HIGH);
        ledcWrite(CH_PWMA, pwmMag);
    }
}

void aplicarMotorDer(int pwmMag, int dir) {
    pwmMag = constrain(pwmMag, 0, 255);
    if (pwmMag == 0 || dir == 0) {
        // Freno electromagnético simétrico a GND en ambos terminales del VNH5019
        digitalWrite(BIN1, LOW);
        digitalWrite(BIN2, LOW);
        ledcWrite(CH_PWMB, 0);
    } else if (dir > 0) {
        digitalWrite(BIN1, HIGH);
        digitalWrite(BIN2, LOW);
        ledcWrite(CH_PWMB, pwmMag);
    } else {
        digitalWrite(BIN1, LOW);
        digitalWrite(BIN2, HIGH);
        ledcWrite(CH_PWMB, pwmMag);
    }
}

void detenerMotoresInmediato() {
    aplicarMotorIzq(0, 0);
    aplicarMotorDer(0, 0);
    integL = 0.0f;
    integR = 0.0f;
    spRpmL = 0.0f;
    spRpmR = 0.0f;
}

// --- CALLBACK RECEPCIÓN ESP-NOW ---
void onDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
    if (len != sizeof(CommandPacketMovil)) return;
    CommandPacketMovil cmd;
    memcpy(&cmd, incomingData, sizeof(CommandPacketMovil));
    if (cmd.pkt_type != PKT_COMMAND || cmd.id_robot != ID_MOVIL) return;

    xSemaphoreTake(xMutex, portMAX_DELAY);
    frenoPerimetral = (cmd.stop_on_perim != 0);

    if (cmd.cmd_mode == 0) {
        modoActual = 0;
        progresoPct = 0;
        detenerMotoresInmediato();
    } else if (cmd.cmd_mode == 4) { // Control directo RPM
        modoActual = 4;
        spRpmL = cmd.param1;
        spRpmR = cmd.param2;
        progresoPct = 1000;
        integL = 0.0f;
        integR = 0.0f;
    } else if (cmd.cmd_mode >= 1 && cmd.cmd_mode <= 3) { // Perfiles MRU (1), MRUV (2), MCU (3)
        modoActual    = cmd.cmd_mode;
        profParam1    = cmd.param1;
        profParam2    = cmd.param2;
        profDuracionS = max(0.1f, cmd.duration_s);
        profInicioMs  = millis();
        progresoPct   = 0;
        integL        = 0.0f;
        integR        = 0.0f;
    }
    xSemaphoreGive(xMutex);
}

// --- TAREA CORE 1: LAZO DE CONTROL CINEMÁTICO (20 Hz / 50 ms) ---
void TaskControlPID(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(50);
    const float dt = 0.050f; // 50 ms

    for (;;) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        // 1. Lectura de Encoders en sus buses físicos reales:
        //    - Bus 0 (Wire)  -> Rueda DERECHA (rawR)
        //    - Bus 1 (Wire1) -> Rueda IZQUIERDA (rawL) + PCF8574
        bool okL = false, okR = false;
        uint16_t rawR = leerAS5600(Wire, okR);

        xSemaphoreTake(xMutex, portMAX_DELAY);
        uint16_t rawL = leerAS5600(Wire1, okL);
        uint8_t perim = leerPCF8574();
        estadoPerim = perim;

        // Estimación de magnitud de RPM Rueda IZQUIERDA (Wire1)
        if (okL) {
            if (firstReadL) { prevRawL = rawL; firstReadL = false; }
            int32_t diffL = (int32_t)rawL - (int32_t)prevRawL;
            if (diffL > 2048)  diffL -= 4096;
            if (diffL < -2048) diffL += 4096;
            prevRawL = rawL;
            float instMagL = (fabs((float)diffL) / 4096.0f) * (60.0f / dt);
            if (modoActual == 0 && abs(diffL) <= 2) magRpmL = 0.0f;
            else magRpmL = 0.65f * magRpmL + 0.35f * instMagL;
            medRpmL = (spRpmL < -0.5f) ? -magRpmL : magRpmL;
        }

        // Estimación de magnitud de RPM Rueda DERECHA (Wire)
        if (okR) {
            if (firstReadR) { prevRawR = rawR; firstReadR = false; }
            int32_t diffR = (int32_t)rawR - (int32_t)prevRawR;
            if (diffR > 2048)  diffR -= 4096;
            if (diffR < -2048) diffR += 4096;
            prevRawR = rawR;
            float instMagR = (fabs((float)diffR) / 4096.0f) * (60.0f / dt);
            if (modoActual == 0 && abs(diffR) <= 2) magRpmR = 0.0f;
            else magRpmR = 0.65f * magRpmR + 0.35f * instMagR;
            medRpmR = (spRpmR < -0.5f) ? -magRpmR : magRpmR;
        }

        // 2. Verificar colisión en Placa Perimetral Frontal (bits en 0 = activado en Pull-Up)
        if (frenoPerimetral && modoActual != 0 && (perim & 0x0F) != 0x0F) {
            modoActual = 5; // Freno por colisión perimetral
            detenerMotoresInmediato();
        }

        // 3. Generador de Perfiles Cinemáticos con rampa suave de arranque (250 ms)
        if (modoActual >= 1 && modoActual <= 3) {
            float t_transcurrido = (millis() - profInicioMs) / 1000.0f;
            if (t_transcurrido >= profDuracionS) {
                modoActual  = 0;
                progresoPct = 1000;
                detenerMotoresInmediato();
            } else {
                progresoPct = (uint16_t)constrain((t_transcurrido / profDuracionS) * 1000.0f, 0.0f, 1000.0f);
                // Rampa de suavizado inicial de 250 ms para romper la inercia de forma simétrica
                float softStart = constrain(t_transcurrido / 0.25f, 0.20f, 1.0f);

                if (modoActual == 1) { // MRU: v constante (param1 en m/s)
                    float rpmTarget = profParam1 * MS_TO_RPM * softStart;
                    spRpmL = rpmTarget;
                    spRpmR = rpmTarget;
                } else if (modoActual == 2) { // MRUV: rampa lineal de v0 (param1) a vf (param2)
                    float a = (profParam2 - profParam1) / profDuracionS;
                    float v_inst = profParam1 + a * t_transcurrido;
                    float rpmTarget = v_inst * MS_TO_RPM;
                    spRpmL = rpmTarget;
                    spRpmR = rpmTarget;
                } else if (modoActual == 3) { // MCU y Giro sobre su propio eje: vL (param1) y vR (param2)
                    spRpmL = profParam1 * MS_TO_RPM * softStart;
                    spRpmR = profParam2 * MS_TO_RPM * softStart;
                }
            }
        }

        // 4. Controladores PI en Magnitud Positiva (evita inversión de giro al frenar)
        float factorBat = (vBat > 10.0f) ? (14.8f / vBat) : 1.0f;
        float targetMagL = fabs(spRpmL);
        float targetMagR = fabs(spRpmR);

        if (modoActual == 0 || modoActual == 5 || (targetMagL < 1.5f && targetMagR < 1.5f)) {
            detenerMotoresInmediato();
        } else {
            // Rueda Izquierda (Driver A)
            if (targetMagL < 1.5f) {
                integL = 0.0f;
                aplicarMotorIzq(0, 0);
            } else {
                int dirL = (spRpmL >= 0.0f) ? 1 : -1;
                float errL = targetMagL - magRpmL;
                integL = constrain(integL + errL * dt, -45.0f, 45.0f);
                float uL = (PWM_DEADZONE + KFF_L * targetMagL + KP_L * errL + KI_L * integL) * factorBat;
                aplicarMotorIzq((int)constrain(uL, 0.0f, 255.0f), dirL);
            }

            // Rueda Derecha (Driver B)
            if (targetMagR < 1.5f) {
                integR = 0.0f;
                aplicarMotorDer(0, 0);
            } else {
                int dirR = (spRpmR >= 0.0f) ? 1 : -1;
                float errR = targetMagR - magRpmR;
                integR = constrain(integR + errR * dt, -45.0f, 45.0f);
                float uR = (PWM_DEADZONE + KFF_R * targetMagR + KP_R * errR + KI_R * integR) * factorBat;
                aplicarMotorDer((int)constrain(uR, 0.0f, 255.0f), dirR);
            }
        }
        xSemaphoreGive(xMutex);
    }
}

// --- TAREA CORE 0: TELEMETRÍA ESP-NOW E INA226 (10 Hz / 100 ms) ---
void TaskComunicaciones(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(100);

    for (;;) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);

        xSemaphoreTake(xMutex, portMAX_DELAY);
        if (ina_ok) {
            vBat = ina226.getBusVoltage();
            iBat = ina226.getCurrent();
        }

        TelemetryPacketMovil pkt;
        pkt.pkt_type     = PKT_TELEMETRY;
        pkt.id_robot     = ID_MOVIL;
        pkt.mode_state   = modoActual;
        pkt.perimetral   = estadoPerim;
        pkt.v_bat_v      = vBat;
        pkt.i_bat_a      = iBat;
        pkt.rpm_l        = medRpmL;
        pkt.rpm_r        = medRpmR;
        pkt.sp_rpm_l     = spRpmL;
        pkt.sp_rpm_r     = spRpmR;
        pkt.progress_pct = progresoPct;
        xSemaphoreGive(xMutex);

        esp_now_send(dongleMac, (uint8_t *)&pkt, sizeof(TelemetryPacketMovil));
    }
}

void setup() {
    Serial.begin(115200);
    xMutex = xSemaphoreCreateMutex();

    // Configurar pines de motores VNH5019
    pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
    pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
    ledcSetup(CH_PWMA, PWM_FREQ, PWM_RES);
    ledcAttachPin(PWMA, CH_PWMA);
    ledcSetup(CH_PWMB, PWM_FREQ, PWM_RES);
    ledcAttachPin(PWMB, CH_PWMB);
    detenerMotoresInmediato();

    // Inicializar ambos buses I2C a 100 kHz con timeout de 25 ms
    Wire.begin(I2C0_SDA, I2C0_SCL, 100000);   // Bus 0: Encoder Rueda Derecha
    Wire.setTimeOut(25);
    Wire1.begin(I2C1_SDA, I2C1_SCL, 100000);  // Bus 1: Encoder Rueda Izquierda + INA226 + PCF8574
    Wire1.setTimeOut(25);

    // Inicializar INA226 en Wire1
    if (ina226.begin()) {
        ina226.setMaxCurrentShunt(10.0, 0.010);
        ina_ok = true;
    }

    // Configurar Wi-Fi y ESP-NOW en Canal 1
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(CANAL_WIFI, WIFI_SECOND_CHAN_NONE);
    esp_wifi_set_promiscuous(false);

    if (esp_now_init() == ESP_OK) {
        esp_now_register_recv_cb(onDataRecv);
        esp_now_peer_info_t peerInfo = {};
        memcpy(peerInfo.peer_addr, dongleMac, 6);
        peerInfo.channel = CANAL_WIFI;
        peerInfo.encrypt = false;
        esp_now_add_peer(&peerInfo);
    }

    xTaskCreatePinnedToCore(TaskControlPID,     "ControlPID", 4096, NULL, 5, NULL, 1);
    xTaskCreatePinnedToCore(TaskComunicaciones, "CommsESP",   4096, NULL, 2, NULL, 0);
}

void loop() {
    vTaskDelay(pdMS_TO_TICKS(1000));
}