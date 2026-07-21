#!/bin/bash
# ============================================================
#  SCRIPT DE ACTUALIZACIÓN - Hipocrafy Edge Gateway
# ============================================================
# Este script se ejecuta en el Jetson Orin Nano para aplicar
# los cambios y reiniciar los servicios de IA local.

set -e

EDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$EDGE_DIR"

run_sudo() {
    if [ -n "$SUDO_PASS" ]; then
        echo "$SUDO_PASS" | sudo -S "$@"
    else
        sudo "$@"
    fi
}

echo "=== 1. Deteniendo servicios temporariamente ==="
run_sudo systemctl stop hipocrafy-edge || true

echo "=== 2. Actualizando dependencias de Python ==="
if [ -d "venv" ]; then
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt || echo "No requirements.txt or no changes"
else
    echo "Advertencia: No se encontró el entorno virtual venv."
fi

echo "=== 3. Creando directorios requeridos ==="
mkdir -p data
mkdir -p logs

echo "=== 4. Recargando y reiniciando servicios systemd ==="
run_sudo systemctl daemon-reload

echo "Iniciando API de FastAPI..."
run_sudo systemctl start hipocrafy-edge
sleep 2

echo "Iniciando Receptor DICOM (Orthanc)..."
run_sudo docker compose up -d || run_sudo docker-compose up -d || true

echo "=== 5. Estado de los servicios ==="
run_sudo systemctl status hipocrafy-edge --no-pager

echo "========================================="
echo " ¡Hipocrafy Edge actualizado correctamente!"
echo "========================================="
