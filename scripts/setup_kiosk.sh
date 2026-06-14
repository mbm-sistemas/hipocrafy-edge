#!/bin/bash
# Configura el Jetson para arrancar en modo kiosk mostrando la interfaz del edge.
# Ejecutar UNA SOLA VEZ como root: sudo bash setup_kiosk.sh

set -e

KIOSK_USER="pmoraga"
EDGE_URL="http://localhost:8080"

# 1. Instalar dependencias mínimas de display
apt-get install -y --no-install-recommends \
    chromium-browser \
    xorg \
    openbox \
    x11-xserver-utils \
    unclutter \
    2>/dev/null || true

# 2. Autoloign en TTY1 sin contraseña
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin ${KIOSK_USER} --noclear %I \$TERM
EOF

# 3. Instalar wmctrl para forzar fullscreen
apt-get install -y --no-install-recommends wmctrl 2>/dev/null || true

# 4. .xinitrc: inicia Openbox explícitamente antes de Chromium
cat > /home/${KIOSK_USER}/.xinitrc << EOF
#!/bin/bash
xrandr --output DP-0 --off --output DP-1 --primary --mode 1920x1080

# Iniciar window manager primero
openbox &

unclutter -idle 3 &

# Esperar hasta que el servicio responda
until curl -sf ${EDGE_URL} >/dev/null 2>&1; do sleep 2; done

# Lanzar Chromium en kiosk
chromium-browser \\
  --kiosk \\
  --app=${EDGE_URL} \\
  --lang=es-419 \\
  --accept-lang=es-419,es \\
  --disable-features=Translate \\
  --force-device-scale-factor=1.25 \\
  --noerrdialogs \\
  --disable-infobars \\
  --disable-session-crashed-bubble \\
  --disable-restore-session-state \\
  --no-first-run \\
  --check-for-update-interval=31536000 &

# Forzar fullscreen una vez que cargue
sleep 8
wmctrl -r "Hipocrafy Edge" -b add,fullscreen

wait
EOF
chmod +x /home/${KIOSK_USER}/.xinitrc
chown ${KIOSK_USER}:${KIOSK_USER} /home/${KIOSK_USER}/.xinitrc

# 5. Arrancar X al hacer login en TTY1 (usa .xinitrc automáticamente)
BASHRC="/home/${KIOSK_USER}/.bash_profile"
if ! grep -q "startx" "${BASHRC}" 2>/dev/null; then
cat >> "${BASHRC}" << 'EOF'

# Kiosk: arrancar X en TTY1 (lee ~/.xinitrc)
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec startx
fi
EOF
fi

# 5. Arrancar en multi-user (sin GNOME pesado), los servicios hipocrafy cargan igual
systemctl set-default multi-user.target

echo ""
echo "Kiosk configurado. Al reiniciar el Jetson:"
echo "  - Arranca sin desktop GNOME (ahorra ~800MB RAM)"
echo "  - Auto-login como ${KIOSK_USER} en TTY1"
echo "  - Abre Chromium apuntando a ${EDGE_URL}"
echo ""
echo "Ejecuta: sudo reboot"
