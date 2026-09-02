# ============================================================
#  SCRIPT DE SINCRONIZACIÓN - Hipocrafy Edge (Windows → Jetson)
# ============================================================
# Ejecutar este script en tu terminal de Windows para subir los 
# cambios locales al Jetson Orin Nano y reiniciarlo.

param(
    [string]$HostName = "192.168.11.5",
    [string]$User = "pmoraga",
    [string]$SudoPass = "Martiluc13-17"
)

$RemoteDir = "/home/pmoraga/hipocrafy-edge"

Write-Host "[*] Iniciando sincronizacion con Hipocrafy Edge ($HostName)..." -ForegroundColor Cyan

# 1. Subir archivos modificados
Write-Host "[*] Subiendo archivos..." -ForegroundColor Yellow
scp -o StrictHostKeyChecking=no -o ServerAliveInterval=5 -o ServerAliveCountMax=12 -r main.py app_updater.py hipocrafy-app-updater.timer templates prompts data services core api enrollment vision_service.py gateway_production.py simulate_capture.py update_edge.sh setup_jetson.sh hipocrafy-edge.service requirements.txt "${User}@${HostName}:${RemoteDir}/"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Archivos subidos correctamente." -ForegroundColor Green
} else {
    Write-Host "[ERROR] Error al subir archivos con SCP. Asegurate de ingresar la contrasena correcta del Jetson." -ForegroundColor Red
    Exit 1
}

# 2. Ejecutar script de actualización en el Jetson
Write-Host "[*] Ejecutando script de actualizacion en el Jetson..." -ForegroundColor Yellow
ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=5 -o ServerAliveCountMax=12 -t "${User}@${HostName}" "sed -i 's/\r$//' ${RemoteDir}/update_edge.sh; chmod +x ${RemoteDir}/update_edge.sh; export SUDO_PASS='${SudoPass}'; ${RemoteDir}/update_edge.sh"

if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Sincronizacion y actualizacion finalizada con exito." -ForegroundColor Green
} else {
    Write-Host "[ERROR] Error al ejecutar el script de actualizacion en el Jetson." -ForegroundColor Red
}
