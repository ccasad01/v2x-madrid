import azure.functions as app
import logging
import json
from datetime import datetime, timezone

fb_app = app.FunctionApp()

def get_nested_value(data, key_path):
    """
    Navega por un diccionario usando una ruta de claves (ej: 'performance.app_latency_ms')
    """
    keys = key_path.split('.')
    rv = data
    for key in keys:
        if isinstance(rv, dict):
            rv = rv.get(key)
        else:
            return None
    return rv
# --- ANALIZADOR DE DISCREPANCIAS ---
def analyze_discrepancies(observed, expected):
    event = "OK"
    reasons = []

    for category, rules in expected.items():
        # category_data ahora será el bloque principal (hardware, cyber_backend...)
        category_data = observed.get(category, {})
        
        for metric_path, thresholds in rules.items():
            # Buscamos el valor real, incluso si está anidado (ej: 'performance.app_latency_ms')
            val = get_nested_value(category_data, metric_path)
            
            if val is not None and isinstance(val, (int, float)):
                crit_limit = thresholds.get('crit', 999999)
                warn_limit = thresholds.get('warn', 999999)

                if val >= crit_limit:
                    event = "CRITICAL"
                    reasons.append(f"CRITICAL: {metric_path} alcanzó {val} (Límite: {crit_limit})")
                elif val >= warn_limit and event != "CRITICAL":
                    event = "WARN"
                    reasons.append(f"WARNING: {metric_path} alcanzó {val} (Límite: {warn_limit})")
    
    return event, reasons

# --- MOTOR DE LA MÁQUINA DE ESTADOS ---
def get_next_state(current_state, event):
    """
    Implementa la matriz de transición de estados.
    """
    transitions = {
        "CRITICAL": "CRITICAL", # El fallo crítico es persistente hasta que llegue un OK
        "WARN": "DEGRADED" if current_state != "CRITICAL" else "CRITICAL",
        "OK": "HEALTHY",
        "TIME": "OFFLINE"
    }
    return transitions.get(event, current_state)

# --- ORQUESTADOR (Azure Function) ---
@fb_app.event_hub_message_trigger(arg_name="azeventhub", 
                               event_hub_name="hub-v2x-madrid", 
                               connection="IoTHubConnectionString") 
@fb_app.cosmos_db_output(arg_name="telemetryHistory", 
                        database_name="v2x-database", 
                        container_name="rsu-telemetry-history", 
                        connection="CosmosDbConnectionString")
@fb_app.cosmos_db_output(arg_name="twinModelUpdate", 
                        database_name="v2x-database", 
                        container_name="rsu-twin-models", 
                        connection="CosmosDbConnectionString")
@fb_app.cosmos_db_input(arg_name="currentModel", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT * FROM c WHERE c.nodeId = {nodeId}",
                       connection="CosmosDbConnectionString")
def iothub_processor(azeventhub: app.EventHubEvent, 
                     telemetryHistory: app.Out[app.Document],
                     twinModelUpdate: app.Out[app.Document],
                     currentModel: app.DocumentList):
    
    # 1. Extracción de datos
    body = azeventhub.get_body().decode('utf-8')
    observed = json.loads(body)
    node_id = observed.get('nodeId')

    if not currentModel:
        logging.error(f"RSU {node_id} no registrada.")
        return

    # 2. Carga de contexto del Gemelo
    twin_doc = currentModel[0]
    previous_state = twin_doc.get('currentState', 'INIT')
    expected_behavior = twin_doc.get('expected_behavior', {})

    # 3. Ejecución de la lógica modular
    event, reasons = analyze_discrepancies(observed, expected_behavior)
    new_state = get_next_state(previous_state, event)

    # 4. Persistencia (Doble escritura)
    # Histórico de telemetría procesada
    telemetry_entry = {
        # Cosmos DB necesita un 'id' único (string). Usamos el nodeId + timestamp.
        "id": f"{node_id}-{datetime.now(timezone.utc).timestamp()}", 
        "nodeId": node_id, # IMPORTANTE: Debe coincidir con la Partition Key del contenedor
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": observed,
        "derived_state": new_state,
        "reasons": reasons
    }
    telemetryHistory.set(app.Document.from_dict(telemetry_entry))

    # Actualización del Modelo Vivo (Gemelo)
    twin_doc.update({
        "currentState": new_state,
        "reasons": reasons,
        "lastUpdate": datetime.now(timezone.utc).isoformat(),
        "last_observation": observed
    })
    
    twinModelUpdate.set(app.Document.from_dict(twin_doc))
    
    logging.info(f"Node: {node_id} | State: {previous_state} -> {new_state} | Event: {event}")