#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  Hipocrafy Edge - Kiosk Mode Script
# ═══════════════════════════════════════════════════════════
# Este script levanta el navegador local en pantalla completa
# para mostrar la cola de estudios y configuraciones en la pantalla del Jetson.

export DISPLAY=:0
export XAUTHORITY=/run/user/1000/.mXauthority

echo "[*] Esperando que el Gateway de Hipocrafy esté en línea..."
until curl -s http://localhost:8080/health | grep -q "online"; do
    sleep 1.5
done

echo "[*] Iniciando navegador local en modo Kiosco..."
if command -v chromium-browser &> /dev/null; then
    chromium-browser --kiosk --noerrdialogs --disable-infobars --check-for-update-interval=31536000 http://localhost:8080
elif command -v google-chrome &> /dev/null; then
    google-chrome --kiosk --noerrdialogs --disable-infobars --check-for-update-interval=31536000 http://localhost:8080
elif command -v firefox &> /dev/null; then
    firefox --kiosk http://localhost:8080
elif command -v epiphany-browser &> /dev/null; then
    epiphany-browser --kiosk http://localhost:8080
else
    # Si no hay interfaz gráfica activa o navegador compatible, abre en lynx/w3m si está disponible
    echo "[-] No se encontró un navegador de escritorio compatible (Chromium, Chrome o Firefox)."
fi
