import sys
import os
import pytest

# 1. Le decimos a Python dónde encontrar tu Azure Function para poder importarla.
# (Ajusta la ruta '../src/cloud/twin-core-processor' si tu function_app.py está en otro sitio)
ruta_funcion = os.path.abspath(os.path.join(os.path.dirname(__file__), '../src/cloud/twin-core-processor'))
sys.path.insert(0, ruta_funcion)

from function_app import get_nested_value, analyze_discrepancies, get_next_state

# --- TEST 1: Navegación de JSON ---
def test_get_nested_value():
    data = {
        "hardware": {"temp": 45.5},
        "cyber_backend": {"performance": {"app_latency_ms": 3.2}}
    }
    
    # Caso ideal: Encuentra el valor de primer nivel
    assert get_nested_value(data, "hardware.temp") == 45.5
    
    # Caso ideal: Encuentra el valor anidado
    assert get_nested_value(data, "cyber_backend.performance.app_latency_ms") == 3.2
    
    # Caso de error: Clave que no existe
    assert get_nested_value(data, "hardware.bateria") is None

# --- TEST 2: El Analizador de Discrepancias ---
def test_analyze_discrepancies():
    expected = {
        "hardware": {
            "temp": {"warn": 80, "crit": 95}
        }
    }
    
    # Caso 1: Todo bajo control (OK)
    obs_ok = {"hardware": {"temp": 50}}
    event, reasons = analyze_discrepancies(obs_ok, expected)
    assert event == "OK"
    assert len(reasons) == 0
    
    # Caso 2: Supera el umbral de Warning
    obs_warn = {"hardware": {"temp": 85}}
    event, reasons = analyze_discrepancies(obs_warn, expected)
    assert event == "WARN"
    assert "WARNING: temp alcanzó 85" in reasons[0]
    
    # Caso 3: Supera el umbral Crítico
    obs_crit = {"hardware": {"temp": 96}}
    event, reasons = analyze_discrepancies(obs_crit, expected)
    assert event == "CRITICAL"
    assert "CRITICAL: temp alcanzó 96" in reasons[0]

# --- TEST 3: FSM ---
def test_get_next_state():
    # Transiciones normales
    assert get_next_state("INIT", "OK") == "HEALTHY"
    assert get_next_state("HEALTHY", "WARN") == "DEGRADED"
    assert get_next_state("DEGRADED", "CRITICAL") == "CRITICAL"
    
    # El Watchdog marca el timeout
    assert get_next_state("HEALTHY", "TIME") == "OFFLINE"
    
    # Comportamiento clave: Un estado CRÍTICO no puede bajar a DEGRADED si llega un evento WARN
    assert get_next_state("CRITICAL", "WARN") == "CRITICAL"