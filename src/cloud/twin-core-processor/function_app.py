import azure.functions as app
import logging
import json
import copy
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

# --- ORQUESTADOR ---
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

# --- ENDPOINT PARA GRAFANA - current status ---
@fb_app.route(route="get_rsu_status", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_input(arg_name="documents", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT * FROM c WHERE c.type = 'RoadSideUnit'", # Traemos todas las RSUs excluyendo system_metadata
                       connection="CosmosDbConnectionString")
def get_rsu_status(req: app.HttpRequest, documents: app.DocumentList) -> app.HttpResponse:
    logging.info("API: Grafana solicitando estado de los Gemelos.")

    if not documents:
        return app.HttpResponse("No hay Gemelos registrados.", status_code=404)

    # Convertimos la lista de Cosmos a una lista de diccionarios Python
    twin_list = [doc.to_dict() for doc in documents]

    # Aquí es donde inyectamos/aseguramos el JSON-LD para Grafana
    # Envolvemos todo en un contexto semántico NGSI-LD
    response_payload = {
        "@context": "https://uri.etsi.org/ngsi-ld/v1/context.jsonld",
        "type": "QueryResponse",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "entities": twin_list
    }
    
    return app.HttpResponse(
        body=json.dumps(response_payload, indent=2),
        mimetype="application/json",
        status_code=200
    )

# --- ENDPOINT PARA GRAFANA - HISTORY (last 50 items)---

@fb_app.route(route="get_history", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_input(arg_name="history", 
                       database_name="v2x-database", 
                       container_name="rsu-telemetry-history", 
                       sql_query="SELECT TOP 200 * FROM c ORDER BY c._ts DESC",
                       connection="CosmosDbConnectionString")
def get_history(req: app.HttpRequest, history: app.DocumentList) -> app.HttpResponse:
    # Esta función devuelve los últimos 50 mensajes enviados por todos los nodos
    history_list = [doc.to_dict() for doc in history]
    return app.HttpResponse(json.dumps(history_list), mimetype="application/json")

# --- ENDPOINT PARA GRAFANA - Activa/desactiva modo simulación ---

@fb_app.route(route="toggle_simulation", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_output(arg_name="twinUpdate", 
                        database_name="v2x-database", 
                        container_name="rsu-twin-models", 
                        connection="CosmosDbConnectionString")
@fb_app.cosmos_db_input(arg_name="currentModel", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT * FROM c WHERE c.nodeId = {nodeId}",
                       connection="CosmosDbConnectionString")
def toggle_simulation(req: app.HttpRequest, currentModel: app.DocumentList, twinUpdate: app.Out[app.Document]) -> app.HttpResponse:
    try:
        req_body = req.get_json()
        node_id = req_body.get('nodeId')

        if not currentModel:
            return app.HttpResponse("RSU no encontrada", status_code=404)

        twin = currentModel[0]
        sim_state = twin.get('simulation_state', {})
        
        # LÓGICA TOGGLE: Invertimos el estado actual
        current_active = sim_state.get('active', False)
        new_active = not current_active
        
        sim_state['active'] = new_active
        
        if new_active:
            # 1. Copiamos los valores de la última observación real al estado de simulación
            last_obs = twin.get('last_observation', {})
            
            # Mantenemos las categorías clave: hardware, network, cyber_backend
            for category in ['hardware', 'network', 'cyber_backend']:
                if category in last_obs:
                    sim_state[category] = copy.deepcopy(last_obs[category])
            
            # 2. Evaluamos el estado basado en estos datos "heredados" de la realidad
            event, reasons = analyze_discrepancies(sim_state, twin.get('expected_behavior', {}))
            
            # 3. El estado inicial simulado será una continuación del estado real actual
            sim_state['sim_status'] = get_next_state(twin.get('currentState', 'INIT'), event)
            sim_state['reasons_sim'] = reasons
            message = "Sandbox Activado: Sincronizado con estado real"
        else:
            # Al DESACTIVAR: Limpiamos estados para que no se quede en rojo
            sim_state['sim_status'] = "OFF"
            sim_state['reasons_sim'] = []
            message = "Sandbox Desactivado y Limpio"

        sim_state['lastSimUpdate'] = datetime.now(timezone.utc).isoformat()
        twin['simulation_state'] = sim_state
        
        twinUpdate.set(app.Document.from_dict(twin))
        
        return app.HttpResponse(
            body=json.dumps({"status": "OK", "active": new_active, "message": message}),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        return app.HttpResponse(f"Error: {str(e)}", status_code=500)

# --- ENDPOINT PARA GRAFANA - Simula maquina de estados en funcion de los cambios introducidos en la telemtria (last 50 items)---

@fb_app.route(route="simulate_step", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_output(arg_name="twinUpdate", 
                        database_name="v2x-database", 
                        container_name="rsu-twin-models", 
                        connection="CosmosDbConnectionString")
@fb_app.cosmos_db_input(arg_name="currentModel", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT * FROM c WHERE c.nodeId = {nodeId}",
                       connection="CosmosDbConnectionString")
def simulate_step(req: app.HttpRequest, currentModel: app.DocumentList, twinUpdate: app.Out[app.Document]) -> app.HttpResponse:
    try:
        req_body = req.get_json()
        cat = req_body.get('category') # 'hardware', 'network', 'cyber_backend'
        field = req_body.get('field')    # 'temp', 'cpuPct', 'performance.app_latency_ms'
        val_sim = float(req_body.get('value'))

        if not currentModel:
            return app.HttpResponse("RSU no encontrada", status_code=404)

        twin = currentModel[0]
        
        # 1. Accedemos directamente a la sección de simulación que ya existe
        sim_state = twin.get('simulation_state', {})

        # Devuelve error si no está en modo simulación
        if not sim_state.get('active', False):
            return app.HttpResponse(
                body=json.dumps({"error": "Sandbox deshabilitado. Pulse 'INICIAR SIMULACIÓN'."}),
                mimetype="application/json",
                status_code=403
            )
        
        # 2. Inyección del valor en la estructura jerárquica
        if cat in sim_state:
            target_cat = sim_state[cat]
            
            # Gestión de sub-objetos (como performance dentro de cyber_backend)
            if "." in field:
                parts = field.split('.')
                # Esto sirve para performance.app_latency_ms -> target_cat['performance']['app_latency_ms']
                if parts[0] in target_cat:
                    target_cat[parts[0]][parts[1]] = val_sim
            else:
                target_cat[field] = val_sim
        else:
            return app.HttpResponse(f"La categoría {cat} no existe en simulation_state", status_code=400)

        # 3. ANALIZAR: Usamos el bloque simulation_state entero para validar contra los límites
        # Importante: analyze_discrepancies debe recibir sim_state (que ahora tiene la misma forma que una observación real)
        event, reasons = analyze_discrepancies(sim_state, twin.get('expected_behavior', {}))
        
        # 4. ACTUALIZAR ESTADO Y REASONS
        sim_state['sim_status'] = get_next_state(twin.get('currentState', 'INIT'), event)
        sim_state['reasons_sim'] = reasons
        sim_state['lastSimUpdate'] = datetime.now(timezone.utc).isoformat()

        # 5. GUARDAR
        twinUpdate.set(app.Document.from_dict(twin))

        return app.HttpResponse(json.dumps({"status": "OK", "new_state": sim_state['sim_status']}), mimetype="application/json")

    except Exception as e:
        return app.HttpResponse(f"Error: {str(e)}", status_code=500)

# --- ENDPOINT PARA GRAFANA - Actualización de rangos para gemelo ---

@fb_app.route(route="update_twin_config", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_output(arg_name="twinUpdate", database_name="v2x-database", container_name="rsu-twin-models", connection="CosmosDbConnectionString")
@fb_app.cosmos_db_input(arg_name="currentModel", database_name="v2x-database", container_name="rsu-twin-models", sql_query="SELECT * FROM c WHERE c.nodeId = {nodeId}", connection="CosmosDbConnectionString")
def update_twin_config(req: app.HttpRequest, currentModel: app.DocumentList, twinUpdate: app.Out[app.Document]) -> app.HttpResponse:
    try:
        body = req.get_json()
        cat = body.get('categoria')  # 'hardware', 'network', etc.
        campo = body.get('campo')    # 'cpuPct', 'v2xLatencyMs', etc.
        warn = float(body.get('warn'))
        crit = float(body.get('crit'))

        if not currentModel:
            return app.HttpResponse("Nodo no encontrado", status_code=404)

        twin = currentModel[0]

        # Bloqueamos la edición de umbrales si la simulación no está activa
        if not twin.get('simulation_state', {}).get('active', False):
            return app.HttpResponse(
                body=json.dumps({"error": "Modo Configuración bloqueado. Active el Sandbox primero."}),
                mimetype="application/json",
                status_code=403
            )
        
        # navegacion json
        if cat in twin['expected_behavior'] and campo in twin['expected_behavior'][cat]:
            twin['expected_behavior'][cat][campo]['warn'] = warn
            twin['expected_behavior'][cat][campo]['crit'] = crit
            
            # Actuliza Cosmos DB
            twinUpdate.set(app.Document.from_dict(twin))
            return app.HttpResponse(f"Configuración de {campo} actualizada a {warn}/{crit}", status_code=200)
        else:
            return app.HttpResponse(f"Error: No existe el campo {cat}.{campo}", status_code=400)
            
    except Exception as e:
        return app.HttpResponse(f"Error procesando update: {str(e)}", status_code=500)
    
# --- ENDPOINT PARA GRAFANA - Historial de Mantenimiento ---
@fb_app.route(route="get_system_events", auth_level=app.AuthLevel.ANONYMOUS)
@fb_app.cosmos_db_input(arg_name="metadata", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT c.events FROM c WHERE c.id = 'system_metadata'",
                       connection="CosmosDbConnectionString")
def get_system_events(req: app.HttpRequest, metadata: app.DocumentList) -> app.HttpResponse:
    if not metadata:
        return app.HttpResponse("[]", mimetype="application/json")
    
    event_list = metadata[0].get("events", [])
    
    return app.HttpResponse(
        body=json.dumps(event_list),
        mimetype="application/json",
        status_code=200
    )

# --- WATCHDOG: DETECTOR DE RSUS OFFLINE ---
@fb_app.timer_trigger(schedule="0 */5 * * * *", arg_name="watchdogTimer", run_on_startup=False)
@fb_app.cosmos_db_input(arg_name="allRSUs", 
                       database_name="v2x-database", 
                       container_name="rsu-twin-models", 
                       sql_query="SELECT * FROM c WHERE c.type = 'RoadSideUnit' AND c.currentState != 'OFFLINE'",
                       connection="CosmosDbConnectionString")
@fb_app.cosmos_db_output(arg_name="updateOutput", 
                        database_name="v2x-database", 
                        container_name="rsu-twin-models", 
                        connection="CosmosDbConnectionString")
def watchdog_processor(watchdogTimer: app.TimerRequest, 
                      allRSUs: app.DocumentList,
                      updateOutput: app.Out[app.Document]):
    
    now = datetime.now(timezone.utc)
    timeout_seconds = 300  # 5 minutos de silencio = OFFLINE
    count_offline = 0

    logging.info(f"WATCHDOG: Analizando {len(allRSUs)} nodos potencialmente activos...")

    for rsu_doc in allRSUs:
        last_update_str = rsu_doc.get('lastUpdate')
        if not last_update_str:
            continue
        
        # Convertimos el string ISO a objeto datetime
        last_update = datetime.fromisoformat(last_update_str.replace('Z', '+00:00'))
        
        # Calculamos el tiempo de silencio
        silence_duration = (now - last_update).total_seconds()

        if silence_duration > timeout_seconds:
            node_id = rsu_doc.get('nodeId')
            
            previous_state = rsu_doc.get('currentState', 'INIT')
            new_state = get_next_state(previous_state, "TIME")
            
            logging.warning(f"WATCHDOG: Nodo {node_id} lleva {silence_duration}s en silencio. Marcando {new_state}.")
            
            rsu_doc['currentState'] = new_state
            rsu_doc['reasons'] = [f"Timeout: No se recibe telemetría desde hace {int(silence_duration)}s"]
            # ----------------------------------------------------
            
            updateOutput.set(app.Document.from_dict(rsu_doc))
            count_offline += 1

    logging.info(f"WATCHDOG: Ciclo completado. {count_offline} nodos pasaron a OFFLINE.")