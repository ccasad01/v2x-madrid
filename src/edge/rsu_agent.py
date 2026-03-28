#!/usr/bin/env python3
import time
import json
import random
from datetime import datetime, timezone
from azure.iot.device import IoTHubDeviceClient

# PEGA AQUÍ TU CADENA DE CONEXIÓN
CONNECTION_STRING = ""

def create_client():
    client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)
    return client

def send_telemetry(client):
    print("Iniciando Agente RSU Madrid V2X...")
    try:
        while True:
            # Simulamos datos crudos del nodo (Estado Observado)
            telemetry_data = {
                "nodeId": "RSU-Madrid-01",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reportIntervalSec": 5,
                "cpuPct": 95.5,
                "memPct": round(random.uniform(40.0, 60.0), 2),
                "v2xLatencyMs": round(random.uniform(5.0, 25.0), 2),
                "errors": {
                    "watchdogResets": 0
                },
                "version": "v2.1.0-rtlinux"
            }

            # Convertimos a JSON string
            message = json.dumps(telemetry_data)
            print(f"Enviando telemetría: {message}")
            
            # Envío a Azure IoT Hub
            client.send_message(message)
            print("Mensaje enviado con éxito.")
            
            time.sleep(5) # Intervalo de reporte
            
    except KeyboardInterrupt:
        print("Agente detenido por el usuario.")
    finally:
        client.shutdown()

if __name__ == "__main__":
    rsu_client = create_client()
    send_telemetry(rsu_client)
