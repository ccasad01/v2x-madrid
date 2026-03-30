import azure.functions as app
import logging
import json
from datetime import datetime, timezone

# Definimos la aplicación de funciones
fb_app = app.FunctionApp()

# Configuramos el trigger de IoT Hub (Event Hub compatible)
@fb_app.event_hub_message_trigger(arg_name="azeventhub", 
                               event_hub_name="hub-v2x-madrid", # Nombre de tu hub
                               connection="IoTHubConnectionString") 
@fb_app.cosmos_db_output(arg_name="outputDocument", 
                        database_name="v2x-database", 
                        container_name="rsu-telemetry-history", 
                        connection="CosmosDbConnectionString")
def iothub_processor(azeventhub: app.EventHubEvent, outputDocument: app.Out[app.Document]):
    # 1. Recibir el "Estado Observado" (Telemetría de Fedora)
    body = azeventhub.get_body().decode('utf-8')
    data = json.loads(body)
    
    logging.info(f"--- TWIN CORE: Procesando {data['nodeId']} ---")

    # 2. Modelo de Comportamiento Esperado (Criterio Cyber)
    # Estos límites disparan el cambio de estado en el Gemelo
    EXPECTED = {
        "cpuPct_max": 80.0,
        "latency_max": 20.0
    }

    # 3. Análisis de Discrepancias
    health = "OK"
    reasons = []

    if data.get('cpuPct', 0) > EXPECTED['cpuPct_max']:
        health = "FAIL"
        reasons.append("CPU_CRITICAL_DISCREPANCY")
    
    if data.get('v2xLatencyMs', 0) > EXPECTED['latency_max']:
        if health != "FAIL": health = "DEGRADED"
        reasons.append("LATENCY_ABOVE_THRESHOLD")

    # 4. Generación del Estado del Gemelo (Base para el JSON-LD)
    twin_state = {
        "id": f"{data['nodeId']}-{datetime.now(timezone.utc).timestamp()}", # ID único para Cosmos
        "nodeId": data['nodeId'],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": health,
        "reasons": reasons,
        "observed_metrics": data
    }
    # Enviamos el JSON a la base de datos
    outputDocument.set(app.Document.from_dict(twin_state))

    logging.info(f"--- GEMELO ACTUALIZADO Y ALMACENADO EN LA BBDD: {json.dumps(twin_state, indent=2)} ---")