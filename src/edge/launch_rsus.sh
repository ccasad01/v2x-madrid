#!/bin/bash

# --- CONFIGURACIÓN ---
# "ID/ConnectionString/Lat/Lon"
NODES=(
)

# Array para guardar los PIDs de los procesos hijos
PIDS=()

# Función para detener todos los procesos al salir
cleanup() {
    echo -e "\n\nDeteniendo todos los agentes RSU..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    exit
}

# Captura la señal SIGINT (Ctrl+C)
trap cleanup SIGINT

echo "Iniciando despliegue de flota RSU..."

for node in "${NODES[@]}"; do
    # Separar los valores usando el punto y coma como delimitador
    IFS="/" read -r ID CONN LAT LON <<< "$node"
    
    echo "Lanzando nodo: $ID"
    
    # Ejecutar en segundo plano (&) y redirigir logs a archivos individuales si quieres
    PYTHONUNBUFFERED=1 python3 rsu_agent.py --id "$ID" --conn "$CONN" --lat "$LAT" --lon "$LON" > "log_$ID.txt" 2>&1 &
    
    # Guardar el PID del proceso recién lanzado
    PIDS+=($!)
done

echo "Flota desplegada. Presiona Ctrl+C para detener todos los nodos."
echo "Logs disponibles en log_RSU-ID.txt"

# Mantener el script vivo para esperar al Ctrl+C
wait