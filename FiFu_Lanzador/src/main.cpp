// archivo: FiFu_Lanzador/src/main.cpp
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Adafruit_NeoPixel.h>
#include "espnow_protocol.h"

// --- DIRECCIÓN MAC DEL DONGLE ESP8266 ---
const uint8_t dongleMac[6] = {0xCC, 0x50, 0xE3, 0x7D, 0x1F, 0x1D};

// --- DEFINICIÓN DE PINES HARDWARE LANZADOR ---
#define PIN_NEOPIXEL   2
#define PIN_TOUCH      3
#define PIN_BUZZER     4
#define PIN_CNY1       6   // Sensor óptico 1 (Inicio)
#define PIN_CNY2       7  // Sensor óptico 2 (Fin - separación 8 mm)
#define PIN_GATILLO    8   // IO8: Bajo demanda (800 ms) -> 90° Anclar, 105°-115° Liberar
#define PIN_RETRACTIL  9   // IO9: SIEMPRE ACTIVO -> 20° Tope, 45° (0mm) a 125° (11.2mm)
#define PIN_CANON      10  // IO10: Bajo demanda (800 ms) -> 90° (0° tiro) a 180° (90° tiro)

// --- CANALES LEDC HARDWARE (50 Hz, 14 bits = 16384 niveles en 20000 us) ---
#define SERVO_FREQ     50
#define SERVO_RES      14
#define CH_GATILLO     0
#define CH_RETRACTIL   1
#define CH_CANON       2

const unsigned long TIEMPO_PULSO_SERVO_MS = 800;    // 800 ms asegura recorrido completo bajo carga
const unsigned long TIMEOUT_CRONO_US      = 500000; // 500 ms máximo entre S1 y S2

Adafruit_NeoPixel pixel(1, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

// Cola segura FreeRTOS para pasar comandos de la interrupción Wi-Fi al loop()
QueueHandle_t colaComandos;

// --- ESTADO DE SERVOS Y ENCLAVAMIENTO MUTUO (IO8 vs IO10) ---
uint8_t angActual8  = 90;  // Gatillo anclado por defecto
uint8_t angActual9  = 45;  // Retráctil en 0 mm por defecto
uint8_t angActual10 = 90;  // Cañón horizontal (0° tiro) por defecto

bool act8 = false, act10 = false;
unsigned long tInicio8 = 0, tInicio10 = 0;

bool pend8 = false, pend10 = false;
uint8_t targetPend8 = 90, targetPend10 = 90;

// Secuencia automática de disparo (Liberar -> Esperar -> Re-anclar a 90°)
bool autoReanclarPendiente = false;
unsigned long tInicioAutoReanclar = 0;

// Buzzer no bloqueante
bool buzzerActivo = false;
unsigned long tInicioBuzzer = 0;

// --- VARIABLES DE INTERRUPCIÓN CRONÓGRAFO CNY70 (Separación = 8 mm) ---
volatile unsigned long t1_us = 0;
volatile unsigned long dt_capturado_us = 0;
volatile bool esperandoS2 = false;
volatile bool nuevoDisparo = false;

uint16_t contadorDisparos = 0;
uint32_t ultimoDtUs = 0;
float    ultimaVelMs = 0.0f;
unsigned long ultimoEnvioTelemetria = 0;

// --- CONVERSIÓN DE GRADOS A DUTY CYCLE LEDC (14 bits @ 50 Hz) ---
uint32_t anguloADuty(uint8_t ang) {
    ang = constrain(ang, 0, 180);
    // Mapeo lineal de 0°..180° a 500..2400 microsegundos
    uint32_t us = map(ang, 0, 180, 500, 2400);
    // 20000 us = 16384 ticks (2^14)
    return (us * 16384UL) / 20000UL;
}

// --- INTERRUPCIONES EN MEMORIA RÁPIDA (IRAM) ---
void IRAM_ATTR isrSensor1() {
    if (!esperandoS2) {
        t1_us = micros();
        esperandoS2 = true;
    }
}

void IRAM_ATTR isrSensor2() {
    if (esperandoS2) {
        unsigned long ahora_us = micros();
        unsigned long delta = ahora_us - t1_us;
        if (delta > 100 && delta < TIMEOUT_CRONO_US) {
            dt_capturado_us = delta;
            nuevoDisparo = true;
            esperandoS2 = false;
        }
    }
}

// --- CONTROL DE SERVOMOTORES CON CORTE PURO A LOW (0V) ---
void cortarCanal8() {
    ledcWrite(CH_GATILLO, 0); // Duty 0 = Pin en nivel LOW fijo (0.0V) sin destruir el timer
    act8 = false;
}

void cortarCanal10() {
    ledcWrite(CH_CANON, 0);   // Duty 0 = Pin en nivel LOW fijo (0.0V) sin destruir el timer
    act10 = false;
}

void activarCanal8(uint8_t ang) {
    ang = constrain(ang, 0, 180);
    angActual8 = ang;
    cortarCanal10(); // Garantiza exclusión inmediata frente a IO10
    ledcWrite(CH_GATILLO, anguloADuty(ang));
    act8 = true;
    tInicio8 = millis();
}

void activarCanal10(uint8_t ang) {
    ang = constrain(ang, 90, 180);
    angActual10 = ang;
    cortarCanal8();  // Garantiza exclusión inmediata frente a IO8
    ledcWrite(CH_CANON, anguloADuty(ang));
    act10 = true;
    tInicio10 = millis();
}

void solicitarMovimientoServo(uint8_t pin, uint8_t ang) {
    if (pin == PIN_RETRACTIL) {
        angActual9 = constrain(ang, 5, 125);
        ledcWrite(CH_RETRACTIL, anguloADuty(angActual9));
    } else if (pin == PIN_GATILLO) {
        if (act10) {
            pend8 = true;
            targetPend8 = ang;
        } else {
            pend8 = false;
            activarCanal8(ang);
        }
    } else if (pin == PIN_CANON) {
        if (act8) {
            pend10 = true;
            targetPend10 = ang;
        } else {
            pend10 = false;
            activarCanal10(ang);
        }
    }
}

void sonarBuzzer() {
    digitalWrite(PIN_BUZZER, HIGH);
    buzzerActivo = true;
    tInicioBuzzer = millis();
}

// --- CALLBACK RECEPCIÓN ESP-NOW (NÚCLEO 0 -> ENCOLA AL NÚCLEO 1) ---
void onDataRecv(const uint8_t *mac, const uint8_t *incomingData, int len) {
    if (len != sizeof(CommandPacketLanzador)) return;
    CommandPacketLanzador cmd;
    memcpy(&cmd, incomingData, sizeof(CommandPacketLanzador));
    if (cmd.pkt_type != PKT_COMMAND || cmd.id_robot != ID_LANZADOR) return;

    xQueueSendFromISR(colaComandos, &cmd, NULL);
}

void setup() {
    Serial.begin(115200);
    colaComandos = xQueueCreate(10, sizeof(CommandPacketLanzador));

    pinMode(PIN_TOUCH, INPUT);
    pinMode(PIN_BUZZER, OUTPUT);
    digitalWrite(PIN_BUZZER, LOW);

    pinMode(PIN_CNY1, INPUT_PULLUP);
    pinMode(PIN_CNY2, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_CNY1), isrSensor1, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PIN_CNY2), isrSensor2, CHANGE);

    // NeoPixel local en verde indicando sistema listo
    pixel.begin();
    pixel.setBrightness(40);
    pixel.setPixelColor(0, pixel.Color(0, 255, 100));
    pixel.show();

    // Configurar los 3 canales LEDC independientes a 50 Hz y 14 bits
    ledcSetup(CH_GATILLO,   SERVO_FREQ, SERVO_RES);
    ledcAttachPin(PIN_GATILLO, CH_GATILLO);
    cortarCanal8(); // Inicia en LOW (0V)

    ledcSetup(CH_CANON,     SERVO_FREQ, SERVO_RES);
    ledcAttachPin(PIN_CANON, CH_CANON);
    cortarCanal10(); // Inicia en LOW (0V)

    ledcSetup(CH_RETRACTIL, SERVO_FREQ, SERVO_RES);
    ledcAttachPin(PIN_RETRACTIL, CH_RETRACTIL);
    ledcWrite(CH_RETRACTIL, anguloADuty(angActual9)); // IO9 siempre activo en 45° (0 mm)

    // Inicializar Wi-Fi y ESP-NOW en Canal 1
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
}

void loop() {
    unsigned long ahora = millis();

    // 0. Despachar comandos recibidos por ESP-NOW de forma segura en Core 1
    CommandPacketLanzador cmd;
    while (xQueueReceive(colaComandos, &cmd, 0) == pdTRUE) {
        if (cmd.cmd_action == 1) { // Mover un servo individual
            solicitarMovimientoServo(cmd.servo_pin, cmd.servo_ang);
        } else if (cmd.cmd_action == 2) { // Sonar Buzzer
            sonarBuzzer();
        } else if (cmd.cmd_action == 3) { // Reiniciar cronógrafo
            esperandoS2 = false;
            ultimoDtUs = 0;
            ultimaVelMs = 0.0f;
        } else if (cmd.cmd_action == 4) { // Disparo rápido + Re-anclaje automático a 90°
            esperandoS2 = false;
            activarCanal8(cmd.servo_ang);
            autoReanclarPendiente = true;
            tInicioAutoReanclar = millis();
        }
    }

    // 1. Secuencia automática de re-anclaje (vuelve a 90° tras 950 ms del disparo)
    if (autoReanclarPendiente && (ahora - tInicioAutoReanclar >= 950)) {
        autoReanclarPendiente = false;
        activarCanal8(90);
    }

    // 2. Gestión de ventana de 800 ms y enclavamiento mutuo entre IO8 e IO10
    if (act8 && (ahora - tInicio8 >= TIEMPO_PULSO_SERVO_MS)) {
        cortarCanal8();
        if (pend10) {
            pend10 = false;
            activarCanal10(targetPend10);
        }
    }
    if (act10 && (ahora - tInicio10 >= TIEMPO_PULSO_SERVO_MS)) {
        cortarCanal10();
        if (pend8) {
            pend8 = false;
            activarCanal8(targetPend8);
        }
    }

    // 3. Apagado no bloqueante del Buzzer (120 ms)
    if (buzzerActivo && (ahora - tInicioBuzzer >= 120)) {
        digitalWrite(PIN_BUZZER, LOW);
        buzzerActivo = false;
    }

    // 4. Timeout preventivo si S1 se activó pero la pelota no cruzó S2
    if (esperandoS2 && (micros() - t1_us > TIMEOUT_CRONO_US)) {
        esperandoS2 = false;
    }

    // 5. Procesar nuevo disparo capturado por las barreras CNY70 (8 mm = 0.008 m)
    if (nuevoDisparo) {
        noInterrupts();
        uint32_t dt = dt_capturado_us;
        nuevoDisparo = false;
        interrupts();

        ultimoDtUs = dt;
        ultimaVelMs = 8000.0f / (float)dt; // v0 = 0.008 m / (dt * 1e-6 s)
        contadorDisparos++;
        sonarBuzzer();
    }

    // 6. Envío periódico de telemetría por ESP-NOW (10 Hz / cada 100 ms)
    if (ahora - ultimoEnvioTelemetria >= 100) {
        ultimoEnvioTelemetria = ahora;

        uint8_t flags = 0;
        if (act8)                           flags |= (1 << 0);
        if (act10)                          flags |= (1 << 1);
        if (digitalRead(PIN_CNY1) == LOW)   flags |= (1 << 2);
        if (digitalRead(PIN_CNY2) == LOW)   flags |= (1 << 3);
        if (esperandoS2)                    flags |= (1 << 4);
        if (digitalRead(PIN_TOUCH) == HIGH) flags |= (1 << 5);

        TelemetryPacketLanzador pkt;
        pkt.pkt_type      = PKT_TELEMETRY;
        pkt.id_robot      = ID_LANZADOR;
        pkt.ang_gatillo   = angActual8;
        pkt.ang_retractil = angActual9;
        pkt.ang_canon     = angActual10;
        pkt.flags         = flags;
        pkt.shot_id       = contadorDisparos;
        pkt.dt_us         = ultimoDtUs;
        pkt.v_salida_ms   = ultimaVelMs;

        esp_now_send(dongleMac, (uint8_t *)&pkt, sizeof(TelemetryPacketLanzador));
    }
}