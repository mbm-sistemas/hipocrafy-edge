#!/bin/bash
echo "=== DRM CONNECTORS ==="
ls /sys/class/drm/
echo ""
echo "=== CONNECTOR STATUS ==="
for f in /sys/class/drm/card*-*/; do
    name=$(basename "$f")
    status=$(cat "$f/status" 2>/dev/null)
    enabled=$(cat "$f/enabled" 2>/dev/null)
    echo "$name: status=$status enabled=$enabled"
done
echo ""
echo "=== DMESG DISPLAY ==="
echo "Martiluc1317" | sudo -S dmesg 2>/dev/null | grep -iE "hdmi|displayport| dp|drm|hotplug|sor|tegra" | tail -20
echo ""
echo "=== XRANDR ==="
export DISPLAY=:0
export XAUTHORITY=/run/user/1000/.mXauthority
xrandr 2>&1
echo ""
export DISPLAY=:1
xrandr 2>&1
echo ""
echo "=== WHO ==="
who
echo ""
echo "=== CABLE TYPE ==="
echo "Check: Is it DP-to-HDMI ACTIVE adapter? Passive may not work."
