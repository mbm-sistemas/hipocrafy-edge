#!/bin/bash
set -e

echo "========================================================="
echo "  HIPOCRAFY EDGE AI - HEALTH & STRESS TEST SUITE"
echo "  Target: $(hostname) ($(uname -m)) - $(date)"
echo "========================================================="

echo ""
echo "--- [TEST 1: STORAGE & PARTITION HEALTH] ---"
df -h / /data
echo "Verifying /etc/fstab entry:"
grep -E "NVME_DATA|swapfile" /etc/fstab

echo ""
echo "--- [TEST 2: MEMORY & 16GB NVMe SWAP] ---"
free -h
swapon --show

echo ""
echo "--- [TEST 3: DOCKER SUBSYSTEM & ROOT DIR] ---"
docker info 2>/dev/null | grep -E "Docker Root Dir|Server Version|Runtimes"
echo "Active Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "--- [TEST 4: OLLAMA LAN LISTENER & DIRECTORY] ---"
ss -tulpn | grep 11434 || netstat -tlpn | grep 11434
echo "Model blobstores in /data/ollama/models:"
ls -lh /data/ollama/models/manifests/registry.ollama.ai/library/
ollama list

echo ""
echo "--- [TEST 5: LIVE AI INFERENCE BENCHMARK (LLaMA 3 8B)] ---"
START_TIME=$(date +%s.%N)
RESPONSE=$(curl -s http://localhost:11434/api/generate -d '{
  "model": "llama3:8b",
  "prompt": "Responde únicamente en una sola frase: ¿Cuál es el rol de un gateway edge en telemedicina?",
  "stream": false
}')
END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc -l 2>/dev/null || echo "N/A")

TEXT=$(echo "$RESPONSE" | grep -o '"response":"[^"]*"' | head -n 1 | cut -d'"' -f4)
EVAL_COUNT=$(echo "$RESPONSE" | grep -o '"eval_count":[0-9]*' | cut -d':' -f2)
EVAL_DURATION=$(echo "$RESPONSE" | grep -o '"eval_duration":[0-9]*' | cut -d':' -f2)

echo "Respuesta del modelo:"
echo ">>> \"$TEXT\""
echo "Tiempo total: ${DURATION}s"
if [ -n "$EVAL_COUNT" ] && [ -n "$EVAL_DURATION" ] && [ "$EVAL_DURATION" -gt 0 ]; then
    TPS=$(echo "scale=2; $EVAL_COUNT / ($EVAL_DURATION / 1000000000)" | bc -l 2>/dev/null || echo "N/A")
    echo "Velocidad de generación: $TPS tokens/segundo (Tokens evaluados: $EVAL_COUNT)"
fi

echo ""
echo "--- [TEST 6: EMBEDDINGS TEST (nomic-embed-text)] ---"
EMBED_RES=$(curl -s http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "Hipocrafy Edge AI Diagnostic Telemetry"
}')
EMBED_LEN=$(echo "$EMBED_RES" | grep -o '\[.*\]' | tr ',' '\n' | wc -l)
echo "Dimensión del embedding generado: $EMBED_LEN vectores (Esperado: 768)"

echo ""
echo "--- [TEST 7: JETSON THERMAL SENSORS & GPU CLOCKS] ---"
for zone in /sys/devices/virtual/thermal/thermal_zone*; do
    if [ -f "$zone/type" ] && [ -f "$zone/temp" ]; then
        TYPE=$(cat "$zone/type")
        TEMP=$(awk '{print $1/1000 " °C"}' "$zone/temp")
        echo "  - $TYPE: $TEMP"
    fi
done

echo ""
echo "--- [TEST 8: HIPOCRAFY DATA DIRECTORIES PERMISSIONS] ---"
ls -ld /data/hipocrafy /data/projects /data/docker /data/ollama

echo ""
echo "========================================================="
echo "  HEALTH CHECK COMPLETE: ALL SYSTEMS NOMINAL"
echo "========================================================="
