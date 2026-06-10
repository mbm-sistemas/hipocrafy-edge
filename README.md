# Guía de Pruebas: Hipocrafy Edge AI

Sigue estos pasos para probar el ecosistema completo (Nube + Equipo Local).

## PASO 1: Preparar la Nube (Tu máquina de desarrollo)

Asegúrate de que el Backend de Laravel y el Frontend de Next.js estén corriendo.
- Backend: `php artisan serve` (por defecto en el puerto 8000)
- Frontend: `npm run dev` (por defecto en el puerto 3000)

1. Abre tu navegador e ingresa a `http://localhost:3000/admin/edge-gateways`.
2. Haz clic en **Registrar Equipo** y asígnale un nombre (Ej. "Servidor Demo PB").
3. Una vez creado, presiona **Ver Token** y cópialo.

## PASO 2: Configurar el Equipo Local (Gateway)

Abre una terminal en la carpeta del proyecto Edge:
`cd "C:\Mbm Salud\hipocrafy-edge"`

1. Crea el archivo de entorno copiando el ejemplo:
   `copy .env.example .env`
2. Abre el archivo `.env` y pega el token que copiaste en el paso anterior:
   `GATEWAY_API_TOKEN=tu_token_aqui`
   Asegúrate de que `HIPOCRAFY_CLOUD_URL=http://localhost:8000/api/edge-gateway`.

## PASO 3: Levantar el Servicio Local

El equipo local consta de dos partes: El servidor PACS (Orthanc en Docker) y el motor de IA (FastAPI, Ollama, Langchain).

**A. Preparación del Hardware Edge (Jetson Orin)**
Si estás configurando un Jetson desde cero, asegúrate de tener **JetPack 6.2** instalado. Luego ejecuta el script de setup automático:
```bash
chmod +x setup_jetson.sh
./setup_jetson.sh
```
*(Este script instalará Python, Ollama, descargará los modelos LLaMA 3 y Nomic, y configurará el entorno virtual).*

**B. Levantar Orthanc (PACS)**
En la consola, ejecuta:
`docker-compose up -d`
*(Esto descargará Orthanc y lo dejará escuchando en los puertos 8042 y 4242).*

**C. Levantar el Motor de IA (Python)**
1. Activa el entorno virtual:
   En Windows: `venv\Scripts\activate`
   En Linux/Jetson: `source venv/bin/activate`
2. Arranca el servidor FastAPI:
   `uvicorn main:app --host 0.0.0.0 --port 8080 --reload`

## PASO 4: Ejecutar la Prueba (Simular un Tomógrafo)

Ahora que todo está corriendo, vamos a simular que un equipo médico le envía una tomografía al servidor local.

1. Abre en tu navegador el panel de Orthanc: `http://localhost:8042` (Usuario: `orthanc`, Contraseña: `orthanc`).
2. Ve a la sección **Upload** y sube cualquier archivo `.dcm` (DICOM) de prueba que tengas.
3. **¡Observa la magia!** Mira la consola donde está corriendo Python (FastAPI).
   - Verás que a los 5 segundos de subir el archivo, Orthanc disparará el Webhook.
   - FastAPI descargará el estudio, correrá la IA y lo subirá a Laravel.

## PASO 5: Ver los Resultados en la Nube

1. Ingresa a `http://localhost:8080` (El panel local del técnico). Verás que contabiliza el estudio como "Subido y Sincronizado".
2. Entra a `http://localhost:3000/medico/diagnostico` (Panel Médico en Hipocrafy Cloud). ¡Ahí estará la tomografía esperando la firma del médico con las marcas estructuradas de la IA!
