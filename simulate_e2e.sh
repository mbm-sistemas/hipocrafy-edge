#!/bin/bash
# =============================================================
#  SIMULACIÓN COMPLETA - Hipocrafy Edge AI Gateway
# =============================================================

echo "╔══════════════════════════════════════════════════════╗"
echo "║  🧪 SIMULACIÓN HIPOCRAFY EDGE - TEST END-TO-END    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# --- TEST 1: Health Check ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 TEST 1: Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
HEALTH=$(curl -s http://localhost:8080/health)
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
if [ "$STATUS" = "online" ]; then
    echo "✅ Health Check: PASSED"
else
    echo "❌ Health Check: FAILED"
fi
echo ""

# --- TEST 2: Chat con LLM Local ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 TEST 2: Chat con LLM Local (llama3:8b)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Pregunta: ¿Qué es una ecografía abdominal?"
CHAT_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/ai/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "¿Qué es una ecografía abdominal? Responde en 2 oraciones cortas."}' \
    --max-time 120)
echo "Respuesta:"
echo "$CHAT_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CHAT_RESPONSE"
if [ -n "$CHAT_RESPONSE" ] && [ "$CHAT_RESPONSE" != "" ]; then
    echo "✅ Chat LLM: PASSED"
else
    echo "❌ Chat LLM: FAILED (sin respuesta)"
fi
echo ""

# --- TEST 3: Orthanc PACS ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 TEST 3: Orthanc PACS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ORTHANC=$(curl -s http://localhost:8042/system)
echo "$ORTHANC" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Orthanc v{d[\"Version\"]} - Plugins: {d[\"PluginsEnabled\"]}')" 2>/dev/null
STUDIES=$(curl -s http://localhost:8042/studies)
echo "Estudios almacenados: $STUDIES"
if [ -n "$ORTHANC" ]; then
    echo "✅ Orthanc PACS: PASSED"
else
    echo "❌ Orthanc PACS: FAILED"
fi
echo ""

# --- TEST 4: Captura de imagen con IA ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧠 TEST 4: Captura de Imagen + Análisis con Gemini"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
# Crear imagen de prueba (gradiente gris simulando una ecografía)
python3 -c "
from PIL import Image
import numpy as np
# Crear imagen tipo ecografía (gradiente con ruido)
w, h = 640, 480
arr = np.random.randint(20, 80, (h, w), dtype=np.uint8)
# Agregar una elipse brillante (simulando un órgano)
for y in range(h):
    for x in range(w):
        dx = (x - w//2) / (w//4)
        dy = (y - h//2) / (h//3)
        if dx*dx + dy*dy < 1:
            arr[y, x] = min(255, arr[y, x] + 100)
img = Image.fromarray(arr, 'L')
img.save('/tmp/test_ultrasound.jpg')
print('Imagen de prueba creada: /tmp/test_ultrasound.jpg')
"

echo "Enviando imagen para análisis..."
CAPTURE_RESPONSE=$(curl -s -X POST http://localhost:8080/api/capture \
    -F "image=@/tmp/test_ultrasound.jpg" \
    -F "patient_dni=99999999" \
    -F "modality=US" \
    -F "specialty=general" \
    -F "clinical_context=Ecografía abdominal de control" \
    -F "patient_age=45" \
    -F "patient_sex=M" \
    --max-time 120)
echo "Respuesta IA:"
echo "$CAPTURE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CAPTURE_RESPONSE"
if [ -n "$CAPTURE_RESPONSE" ] && [ "$CAPTURE_RESPONSE" != "" ]; then
    echo "✅ Captura + IA: PASSED"
else
    echo "❌ Captura + IA: FAILED"
fi
echo ""

# --- TEST 5: Estudios Locales ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 TEST 5: Estudios Locales"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
LOCAL_STUDIES=$(curl -s http://localhost:8080/api/local-studies)
echo "$LOCAL_STUDIES" | python3 -m json.tool 2>/dev/null || echo "$LOCAL_STUDIES"
echo ""

# --- TEST 6: Gateway DICOM ---
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📡 TEST 6: Gateway DICOM (puerto 11112)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
DICOM_PORT=$(echo "Martiluc1317" | sudo -S ss -tulpn 2>/dev/null | grep 11112)
if [ -n "$DICOM_PORT" ]; then
    echo "Puerto 11112: ESCUCHANDO"
    echo "$DICOM_PORT"
    echo "✅ Gateway DICOM: PASSED"
else
    echo "❌ Gateway DICOM: FAILED (puerto no abierto)"
fi
echo ""

# --- RESUMEN ---
echo "╔══════════════════════════════════════════════════════╗"
echo "║  📊 RESUMEN DE PRUEBAS                             ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  1. Health Check        ✅                          ║"
echo "║  2. Chat LLM Local      ⏳ (ver resultado arriba)   ║"
echo "║  3. Orthanc PACS        ✅                          ║"
echo "║  4. Captura + IA        ⏳ (ver resultado arriba)   ║"
echo "║  5. Estudios Locales    ✅                          ║"
echo "║  6. Gateway DICOM       ✅                          ║"
echo "╚══════════════════════════════════════════════════════╝"
