// archivo: FiFu_Dongle/src/main.cpp
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <espnow.h>
#include <ArduinoJson.h>
#include "espnow_protocol.h"

// Direcciones MAC físicas de ambos módulos ESP32-S3
uint8_t movilMac[6]    = {0x3C, 0x0F, 0x02, 0xE4, 0x24, 0x9C};
uint8_t lanzadorMac[6] = {0x3C, 0x0F, 0x02, 0xE4, 0x24, 0xBC};

String serialBuffer = "";

// --- CALLBACK DE RECEPCIÓN ESP-NOW (DESDE MÓVIL O LANZADOR) ---
void onDataRecv(uint8_t *mac, uint8_t *incomingData, uint8_t len) {
    if (len < 2) return;
    uint8_t pkt_type = incomingData[0];
    uint8_t id_robot = incomingData[1];

    if (pkt_type != PKT_TELEMETRY) return;

    // Caso 1: Telemetría de la Unidad Móvil (ID = 1)
    if (id_robot == ID_MOVIL && len == sizeof(TelemetryPacketMovil)) {
        TelemetryPacketMovil pkt;
        memcpy(&pkt, incomingData, sizeof(TelemetryPacketMovil));

        Serial.printf(
            "{\"src\":1,\"mode\":%u,\"perim\":%u,\"vbat\":%.2f,\"ibat\":%.3f,"
            "\"rpm_l\":%.1f,\"rpm_r\":%.1f,\"sp_l\":%.1f,\"sp_r\":%.1f,\"prog\":%u}\n",
            pkt.mode_state, pkt.perimetral, pkt.v_bat_v, pkt.i_bat_a,
            pkt.rpm_l, pkt.rpm_r, pkt.sp_rpm_l, pkt.sp_rpm_r, pkt.progress_pct
        );
    }
    // Caso 2: Telemetría de la Unidad del Lanzador (ID = 2)
    else if (id_robot == ID_LANZADOR && len == sizeof(TelemetryPacketLanzador)) {
        TelemetryPacketLanzador pkt;
        memcpy(&pkt, incomingData, sizeof(TelemetryPacketLanzador));

        Serial.printf(
            "{\"src\":2,\"gat\":%u,\"ret\":%u,\"can\":%u,\"flags\":%u,"
            "\"shot_id\":%u,\"dt_us\":%u,\"v_ms\":%.3f}\n",
            pkt.ang_gatillo, pkt.ang_retractil, pkt.ang_canon, pkt.flags,
            pkt.shot_id, pkt.dt_us, pkt.v_salida_ms
        );
    }
}

// --- PROCESAR COMANDOS JSON DESDE LA INTERFAZ PYTHON ---
void procesarComandoSerial(const String &linea) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, linea);
    if (err) return;

    int target = doc["target"] | 0;

    // Enviar comando a la Unidad Móvil (target = 1)
    if (target == ID_MOVIL) {
        CommandPacketMovil cmd = {};
        cmd.pkt_type      = PKT_COMMAND;
        cmd.id_robot      = ID_MOVIL;
        cmd.cmd_mode      = doc["mode"] | 0;
        cmd.stop_on_perim = doc["perim_stop"] | 1;
        cmd.param1        = doc["p1"] | 0.0f;
        cmd.param2        = doc["p2"] | 0.0f;
        cmd.duration_s    = doc["dur"] | 0.0f;

        esp_now_send(movilMac, (uint8_t *)&cmd, sizeof(CommandPacketMovil));
    }
    // Enviar comando a la Unidad del Lanzador (target = 2)
    else if (target == ID_LANZADOR) {
        CommandPacketLanzador cmd = {};
        cmd.pkt_type   = PKT_COMMAND;
        cmd.id_robot   = ID_LANZADOR;
        cmd.cmd_action = doc["action"] | 1;
        cmd.servo_pin  = doc["pin"] | 9;
        cmd.servo_ang  = doc["ang"] | 45;

        esp_now_send(lanzadorMac, (uint8_t *)&cmd, sizeof(CommandPacketLanzador));
    }
}

void setup() {
    Serial.begin(115200);
    delay(100);

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    wifi_set_channel(CANAL_WIFI);

    if (esp_now_init() == 0) {
        esp_now_set_self_role(ESP_NOW_ROLE_COMBO);
        esp_now_register_recv_cb(onDataRecv);

        esp_now_add_peer(movilMac,    ESP_NOW_ROLE_COMBO, CANAL_WIFI, NULL, 0);
        esp_now_add_peer(lanzadorMac, ESP_NOW_ROLE_COMBO, CANAL_WIFI, NULL, 0);
    }
}

void loop() {
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (serialBuffer.length() > 0) {
                procesarComandoSerial(serialBuffer);
                serialBuffer = "";
            }
        } else {
            serialBuffer += c;
            if (serialBuffer.length() > 256) serialBuffer = "";
        }
    }
}