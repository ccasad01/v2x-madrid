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
        with open("/sys/class/thermal/thermal_zone1/temp", "r") as f:
            temp_raw = f.read().strip()
        return round(float(temp_raw) / 1000.0, 1)
    except:
        # Fallback: Si no hay sensor accesible, simulamos una temperatura
        return round(random.uniform(42.0, 48.0), 1)

def get_network_metrics():
    """Métrica de red real: ráfaga de 5 pings para obtener latencia y pérdida real"""
    try:
        # -c 5: 5 paquetes, -i 0.2: intervalo rápido, -W 1: timeout 1s
        res = subprocess.check_output(["ping", "-c", "5", "-i", "0.2", "-W", "1", "8.8.8.8"], 
                                      stderr=subprocess.STDOUT, 
                                      universal_newlines=True)
        
        # 1. Extraer Latencia (Media)
        labels = ["time=", "tiempo="]
        latency = 999.0
        for label in labels:
            if label in res:
                latency_str = res.split(label)[1].split()[0].replace(',', '.')
                latency = float(latency_str)
                break
        
        # 2. Extraer Packet Loss Real
        # Buscamos la línea que contiene '% packet loss'
        loss_line = [l for l in res.split('\n') if 'packet loss' in l][0]
        # Extraemos el número justo antes del '%'
        loss_pct = float(loss_line.split('%')[0].split()[-1])
        
        return latency, loss_pct
    except Exception:
        return 999.0, 100.0

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
            "queue_fill_pct": 75
        }
    }

def send_telemetry(client):
    print(f"//////*******Iniciando agente RSU: {args.id}*******//////")
    try:
        while True:
            # Captura de datos reales del sistema Fedora
            real_latency, real_loss = get_network_metrics()
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
                    "packetLoss": real_loss
                }
            }

            message = json.dumps(telemetry_data)
            print(f"//////*******Enviando telemetría: {message}*******//////")

            client.send_message(message)
            print(f"//////*******Evento Ciber-Físico enviado: {args.id} - Status: OK*******//////")
            
            time.sleep(7)  # 7s +1.5s aprox ping
            
    except KeyboardInterrupt:
        print(f"\n//////*******Agente {args.id} detenido.*******//////")
    finally:
        client.shutdown()

if __name__ == "__main__":
    rsu_client = create_client()
    send_telemetry(rsu_client)