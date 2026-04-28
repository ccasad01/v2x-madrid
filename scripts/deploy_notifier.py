import os
import sys
import argparse
from datetime import datetime, timezone
from azure.cosmos import CosmosClient

def update_cosmos_state(status: str, version: str = None):
    connection_string = os.getenv("COSMOS_CONNECTION_STRING")
    if not connection_string:
        print("ERROR: Variable de entorno COSMOS_CONNECTION_STRING no definida.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CosmosClient.from_connection_string(connection_string)
        container = client.get_database_client("v2x-database").get_container_client("rsu-twin-models")

        # Recuperar estado actual
        metadata = container.read_item(item="system_metadata", partition_key="system_metadata")
        
        # Actualizar campos de la raíz
        metadata["status"] = status
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata["last_deploy"] = timestamp
        
        if version:
            metadata["backend_version"] = version

        # Registrar el evento en el array para Grafana
        texto_evento = f"Despliegue versión {version} completado" if status == "OPERATIONAL" else "Iniciando mantenimiento del sistema"
        
        nuevo_evento = {
            "timestamp": timestamp,
            "status": status,
            "text": texto_evento
        }
        
        eventos = metadata.get("events", [])
        eventos.append(nuevo_evento)
        metadata["events"] = eventos[-20:] # Retener únicamente los últimos 20 eventos

        # Persistir cambios
        container.replace_item(item=metadata["id"], body=metadata)
        print(f"INFO: Metadatos del sistema actualizados -> {status}")

    except Exception as e:
        print(f"ERROR: Fallo al actualizar Cosmos DB: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", required=True, choices=["OPERATIONAL", "MAINTENANCE"])
    parser.add_argument("--version", required=False)
    args = parser.parse_args()
    
    update_cosmos_state(args.status, args.version)