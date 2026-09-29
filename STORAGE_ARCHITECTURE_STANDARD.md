# Estándar de Arquitectura de Almacenamiento: Hipocrafy Edge Gateway

Este documento define la arquitectura de almacenamiento estándar y la configuración obligatoria para todos los nodos **Hipocrafy Edge AI** desplegados sobre hardware **NVIDIA Jetson (Orin Nano / Orin Super / Xavier NX)**.

---

## 1. Justificación de la Arquitectura: *Patrón Dual-Storage*

En entornos clínicos y hospitalarios, los equipos Edge ejecutan cargas pesadas de:
* **Imágenes Médicas DICOM (PACS Orthanc):** Escritura continua de estudios de alta resolución (tomografías, ecografías, resonancias).
* **Modelos de Lenguaje y Visión (Ollama / LLaMA 3 8B / Whisper / Faster-Whisper):** Ocupan entre 5 GB y 25 GB y requieren lectura a ultra-alta velocidad.
* **Memoria Swap para IA:** El procesamiento de tensores en modelos grandes requiere memoria virtual de baja latencia para prevenir cuelgues *Out Of Memory (OOM)*.

### ¿Por qué no correr el arranque frío 100% sobre el NVMe sin SD?
Las placas NVIDIA Jetson Orin tienen controladores y firmas de hardware asociadas a la memoria QSPI/microSD. Los arranques fríos directos desde NVMe sin flasheo previo de bajo nivel por SDK Manager suelen fallar o quedar en bucle de recuperación (*L4TLauncher Recovery Boot*). 

### La Solución Estándar: *Dual-Storage*
1. **MicroSD (256 GB) — Sistema Base y Boot Seguro:**
   * Contiene el kernel de Linux (`/boot`), drivers Tegra y el sistema operativo base (`/`).
   * **Ventaja:** El arranque es 100% confiable y protegido. Al no recibir escrituras constantes de Docker o modelos, la vida útil de la tarjeta es indefinida.
2. **SSD NVMe M.2 (1 TB) — Montado en `/data`:**
   * Aloja **todo lo pesado y crítico**: contenedores Docker, estudios DICOM, modelos de IA y el archivo swapfile.
   * **Ventaja:** Rendimiento de transferencia de hasta **2.000 MB/s**, reduciendo el tiempo de carga de modelos a la RAM/GPU de 30 segundos a menos de 2 segundos.

---

## 2. Mapa de Directorios en `/data`

| Ruta | Propósito | Configuración Asociada |
| :--- | :--- | :--- |
| **`/data/docker`** | Motor Docker (contenedores, volúmenes de Orthanc y Postgres) | `/etc/docker/daemon.json` (`"data-root": "/data/docker"`) |
| **`/data/ollama/models`** | Pesos de los LLMs (`llama3:8b`, `nomic-embed-text`, etc.) | Systemd override `OLLAMA_MODELS=/data/ollama/models` |
| **`/data/swapfile`** | Memoria virtual Swap de 16 GB en disco de alta velocidad | `/etc/fstab` con prioridad `pri=10` |
| **`/data/hipocrafy`** | Datos locales, colas Store & Forward y bases SQLite | Permisos asignados al usuario local |
| **`/data/projects`** | Espacio de trabajo para scripts y pruebas | Permisos asignados al usuario local |

---

## 3. Provisionamiento Automatizado

En cualquier Jetson nueva o que se le agregue un disco NVMe de 1 TB:

1. Conectar el disco NVMe M.2 a la placa.
2. Formatear la partición principal como `ext4` con etiqueta `NVME_DATA`:
   ```bash
   sudo mkfs.ext4 -F -L NVME_DATA /dev/nvme0n1p1
   ```
3. Ejecutar el script automatizado provisto en este repositorio:
   ```bash
   chmod +x setup_nvme.sh
   ./setup_nvme.sh
   ```

El script se encarga automáticamente de:
* Configurar el montaje persistente en `/etc/fstab`.
* Crear el swapfile de 16 GB y activarlo.
* Migrar los datos existentes de Docker y cambiar el `data-root`.
* Migrar los modelos de Ollama y configurar el servicio Systemd.
* Asignar permisos al usuario activo y agregarlo al grupo `docker`.

---

## 4. Checklist de Verificación Post-Instalación

Ejecutar los siguientes comandos en la terminal de la Jetson para validar el estado:

```bash
# 1. Verificar montaje y espacio (>850 GB libres en /data)
df -h / /data

# 2. Verificar que el Swap de 16GB esté activo en NVMe
swapon --show

# 3. Verificar que Docker use /data/docker
docker info | grep "Docker Root Dir"

# 4. Verificar que Ollama reconozca los modelos desde NVMe
ollama list
```

---

## 5. Protocolo de Rescate: Si la Jetson entra en *Recovery Boot*

Si por alguna razón la UEFI pierde el orden de arranque y muestra en pantalla:
`L4TLauncher: recovery boot`

**Procedimiento de resolución:**
1. Al encender la Jetson y ver el logo de NVIDIA, presionar **`ESC`** repetidamente para entrar a la BIOS UEFI.
2. Navegar a:
   👉 **Device Manager** -> **NVIDIA Resource Configuration** -> **Boot Configuration**
3. Cambiar **`L4T Boot Mode`** de `[Recovery Boot]` a **`[Direct Boot]`**.
4. Presionar **`F10`** para guardar y reiniciar.
