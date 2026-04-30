# Brain V2X Madrid - Digital Twin for Roadside Units (RSU)

Este repositorio contiene el código fuente y la infraestructura como código (IaC) de un sistema de Gemelos Digitales (Digital Twins) para unidades de carretera (RSUs) en entornos V2X (Vehicle-to-Everything). 

El proyecto permite monitorizar, simular y gestionar el ciclo de vida de una flota de nodos Edge desplegados en la ciudad de Madrid, utilizando una arquitectura 100% Serverless en Azure y observabilidad avanzada en Grafana.

## Arquitectura del Sistema

El sistema está dividido en tres grandes capas:

1. **Capa Edge (Adquisición de Datos):** Agentes Python simulados ejecutándose en nodos Linux (Fedora). Capturan telemetría real y simulada del hardware (CPU, temperatura, carga media), métricas de red (Latencia, Packet Loss), performance (mensajes procesados, latencia, pila), y las envían de forma segura vía MQTT.
2. **Capa Cloud (Procesamiento y Estado):** Orquestada mediante Azure Serverless. 
    * **Azure IoT Hub:** Puerta de enlace segura para la ingesta de telemetría.
    * **Azure Functions:** Motor lógico que procesa eventos, evalúa discrepancias, gestiona la máquina de estados del Gemelo Digital (HEALTHY, WARN, CRITICAL, OFFLINE) del dispositivo, la máquina de estados general (OPERATIONAL, MAINTENANCE) y la simulación
    * **Azure Cosmos DB:** Base de datos NoSQL que almacena el modelo vivo de las RSUs, el histórico de telemetría y los metadatos de despliegue.
3. **Capa de Observabilidad:** Paneles de Grafana conectados mediante el plugin Infinity que consumen la API de la Azure Function, modelando los datos bajo un contexto semántico (NGSI-LD).

## Características Principales

* **Detección de Anomalías en Tiempo Real:** Evaluación de telemetría del backend contra umbrales dinámicos (`expected_behavior`).
* **Watchdog de Conectividad:** Proceso en segundo plano (Cron) que detecta nodos caídos y los marca como `OFFLINE` tras 5 minutos de inactividad.
* **Entorno Sandbox (Simulación):** Capacidad de inyectar fallos virtuales en los nodos sin afectar a la telemetría real ni a la configuración global de producción.
* **CI/CD con Trazabilidad:** Pipeline automatizado en GitHub Actions que actualiza el código en Azure e inyecta eventos de despliegue en la base de datos para correlacionarlos visualmente en las gráficas de Grafana (Anotaciones).

## Estructura del Repositorio

La siguiente estructura refleja el código base del proyecto (los archivos autogenerados, entornos virtuales, logs locales y empaquetados están excluidos por `.gitignore`):

```text
├── .github/workflows/       # Pipelines de CI/CD (GitHub Actions)
├── docs/                    # Documentacion del TFM (memoria, especificaciones)
├── grafana/                 # Dashboards de Grafana exportados (.json)
├── graph/                   # Diagramas de arquitectura y maquinas de estado (.drawio)
├── scripts/                 # Scripts de utilidad para CI/CD (deploy_notifier.py)
├── src/
│   ├── cloud/               # Codigo Backend (Azure)
│   │   └── twin-core-processor/ # Motor logico (Azure Functions)
│   │       ├── function_app.py  # Script principal de la API y procesamiento
│   │       ├── host.json
│   │       ├── local.settings.json
│   │       └── requirements.txt
│   ├── edge/                # Codigo de los dispositivos fisicos Edge
│   │   ├── launch_rsus.sh   # Script Bash para desplegar la flota simulada
│   │   └── rsu_agent.py     # Agente Python de captura de telemetria
│   └── shared/              # Recursos y modulos compartidos
├── tests/                   # Suite de pruebas unitarias
│   └── test_basic.py        # Tests del brain.
└── README.md
```

## Despliegue y Uso Local

### 1. Requisitos Previos
* Python 3.11+
* Cuenta de Microsoft Azure activa (IoT Hub, Functions App, Cosmos DB).
* Entorno Linux (para la ejecución de los agentes Edge).

### 2. Ejecución de la Flota (Edge)
Para lanzar la simulación de los nodos RSU locales, navega a la carpeta `src/edge/` e inicia el script lanzador. 

**Importante:** Por motivos de seguridad, las credenciales reales (`SharedAccessKey`) no se incluyen en este repositorio. Debes generar las tuyas en Azure IoT Hub creando un dispositivo IoTy pegarlas en el archivo `launch_rsus.sh` con el siguiente formato: 

```bash 
ID|ConnectionString|Lat|Lon
```
Por ejemplo:
```text
NODES=(
    "RSU-Madrid-01|ConnectionString|40.416700|-3.703700"
    "RSU-Madrid-02|ConnectionString2|40.418000|-3.690000"
    #"RSU-Madrid-03|ConnectionString3|40.418879|-3.696281"
    #"RSU-Madrid-04|ConnectionString4|40.417050|-3.694324"
)
```
Lanzamiento:
```bash
cd src/edge/
chmod +x launch_rsus.sh
./launch_rsus.sh
```

### 3. Ejecución de Tests Unitarios
El núcleo lógico del Gemelo Digital está cubierto por pruebas automatizadas que validan la navegación de JSON, el análisis de discrepancias y las transiciones de la máquina de estados.

```bash
pip install pytest
pytest tests/test_basic.py -v
```

## Integración y Despliegue Continuo (CI/CD)

Cualquier push a la rama `main` dispara automáticamente el pipeline definido en `.github/workflows/main_brain-v2x-madrid.yml`. El flujo realiza lo siguiente:
1. Clona el repositorio y ejecuta la suite de `pytest`.
2. Empaqueta el código de la Azure Function.
3. Notifica a Cosmos DB el inicio del mantenimiento (`deploy_notifier.py`).
4. Despliega la nueva versión en Azure de forma segura mediante OIDC.
5. Notifica a Cosmos DB el fin del despliegue etiquetando la versión con el Hash del commit, lo que dibuja una línea de control en Grafana.

## Dashboard y Visualización

El panel operativo ha sido diseñado en Grafana. Para replicarlo en un entorno nuevo:
1. Instala el plugin Infinity en tu instancia de Grafana.
2. Ve a Dashboards > Import.
3. Sube el archivo `dashboards/V2X Madrid.json` incluido en este repositorio para incluír el dashboard principal del gemelo digital
4. Sube el archivo `dashboards/simulated dashboard.json` incluido en este repositorio para incluír el dashboard de simulación del gemelo digital
