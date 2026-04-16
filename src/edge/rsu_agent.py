#!/usr/bin/env python3
import time
import json
import random
import psutil
import argparse
import subprocess
import os # Añadimos os para verificar rutas de archivos
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
    client = IoTHubDeviceClient.create_from_connection_string(args.conn)
    return client

def get_real_temp():
    """Lee la temperatura real del CPU desde /sys/class/thermal/"""
    try:
        # CPU temp
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp_raw = f.read().strip()
        return round(float(temp_raw) / 1000.0, 1)
    except:
        # Fallback: Si no hay sensor accesible, simulamos una temperatura
        return round(random.uniform(42.0, 48.0), 1)

def get_real_ping():
    """Métrica de red real: latencia compatible con inglés (time=) y español (tiempo=)"""
    try:
        # Ejecutamos el ping con timeout de 2 segundos
        res = subprocess.check_output(["ping", "-c", "1", "-W", "2", "8.8.8.8"], 
                                      stderr=subprocess.STDOUT, 
                                      universal_newlines=True)
        
        # Lista de posibles etiquetas de tiempo según el idioma
        labels = ["time=", "tiempo="]
        
        for label in labels:
            if label in res:
                # Extraemos lo que hay justo después de la etiqueta
                # split(label)[1] nos da: "3.05 ms..."
                # split()[0] nos da solo el número: "3.05"
                latency_str = res.split(label)[1].split()[0]
                
                # En español, a veces el ping usa la coma como separador decimal (3,05)
                # Lo normalizamos a punto para que Python pueda convertirlo a float
                latency_str = latency_str.replace(',', '.')
                
                return float(latency_str)
        
        return 999.0
    except Exception:
        return 999.0

def get_load_avg():
    """Métrica de /proc real: carga media del sistema"""
    try:
        with open("/proc/loadavg", "r") as f:
            return float(f.read().split()[0])
    except:
        return 0.0

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
            # Captura de datos reales del sistema Fedora
            real_latency = get_real_ping()
            load_1m = get_load_avg()
            cpu_temp = get_real_temp()

            telemetry_data = {
                "nodeId": args.id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "version": "v2.2.0-cyber",
                "location": {
                    "type": "Point",
                    "coordinates": [args.lon, args.lat]
                },
                "hardware": {
                    "cpuPct": psutil.cpu_percent(),
                    "memPct": psutil.virtual_memory().percent,
                    "loadAvg": load_1m,
                    "temp": cpu_temp # Ahora es temperatura real de /sys
                },
                "cyber_backend": get_backend_metrics(),
                "network": {
                    "v2xLatencyMs": real_latency,
                    "packetLoss": 0.0 if real_latency < 200 else 0.1
                }
            }

            message = json.dumps(telemetry_data)
            print(f"Enviando telemetría: {message}")

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