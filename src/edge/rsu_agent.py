#!/usr/bin/env python3
import time
import json
import random
import psutil #pip install psutil si no esta instalado
from datetime import datetime, timezone
from azure.iot.device import IoTHubDeviceClient

CONNECTION_STRING = ""
def create_client():
    client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
    return client

def get_backend_metrics():
    """Simula la salud de los procesos V2X internos"""
    return {
        "services": [
            {"name": "v2x-stack", "status": "RUNNING", "threads": 12},
            {"name": "security-hsm", "status": "RUNNING", "integrity_check": "OK"}
        ],
        "performance": {
            "msg_processed_per_sec": random.randint(85, 115),
            "app_latency_ms": round(random.uniform(2.0, 10.0), 2),
            "queue_fill_pct": 99.8
        }
    }

def send_telemetry(client):
    print("🚀 Iniciando agente RSU Madrid")
    try:
        while True:
            # Datos observados del nodo reales+simulados
            telemetry_data = {
                "nodeId": "RSU-Madrid-01",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "v2.2.0-cyber",
                "hardware": {
                    "cpuPct": psutil.cpu_percent(),
                    "memPct": psutil.virtual_memory().percent,
                    "temp": round(random.uniform(45.0, 55.0), 1)
                },
                "cyber_backend": get_backend_metrics(),
                "network": {
                    "v2xLatencyMs": round(random.uniform(5.0, 20.0), 2),
                    "packetLoss": round(random.uniform(0.0, 0.1), 3)
                }
            }

            # Convertimos a JSON string
            message = json.dumps(telemetry_data)
            print(f"Enviando telemetría: {message}")

            # Envío a Azure IoT Hub
            client.send_message(message)
            print(f"📡 Evento Ciber-Físico enviado: {telemetry_data['nodeId']} - Status: OK")
            
            time.sleep(10) 
            
    except KeyboardInterrupt:
        print("\n🛑 Agente detenido.")
    finally:
        client.shutdown()

if __name__ == "__main__":
    rsu_client = create_client()
    send_telemetry(rsu_client)