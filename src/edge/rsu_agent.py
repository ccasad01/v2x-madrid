#!/usr/bin/env python3
import time
import json
import random
import psutil
import argparse # Añadimos esto para manejar argumentos por terminal
from datetime import datetime, timezone
from azure.iot.device import IoTHubDeviceClient

# --- GESTIÓN DE ARGUMENTOS ---
parser = argparse.ArgumentParser(description='Agente RSU Madrid Multi-Nodo')
parser.add_argument('--id', default="RSU-Madrid-01", help='ID del nodo (nodeId)')
parser.add_argument('--conn', required=True, help='Connection String de Azure IoT Hub')
parser.add_argument('--lat', type=float, default=40.4167, help='Latitud del nodo')
parser.add_argument('--lon', type=float, default=-3.7037, help='Longitud del nodo')
args = parser.parse_args()

def create_client():
    # Usamos la cadena de conexión pasada por parámetro
    client = IoTHubDeviceClient.create_from_connection_string(args.conn)
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
            "queue_fill_pct": 20
        }
    }

def send_telemetry(client):
    print(f"🚀 Iniciando agente RSU: {args.id}")
    try:
        while True:
            # Datos observados del nodo reales+simulados
            telemetry_data = {
                "nodeId": args.id, # Usamos el ID pasado por parámetro
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
            print(f"📡 Evento Ciber-Físico enviado: {args.id} - Status: OK")
            
            time.sleep(10) 
            
    except KeyboardInterrupt:
        print(f"\n🛑 Agente {args.id} detenido.")
    finally:
        client.shutdown()

if __name__ == "__main__":
    rsu_client = create_client()
    send_telemetry(rsu_client)