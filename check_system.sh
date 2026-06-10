#!/bin/bash
echo "=== SERVICES ==="
echo "Martiluc1317" | sudo -S systemctl is-active hipocrafy-api hipocrafy-dicom ollama docker 2>/dev/null

echo ""
echo "=== HEALTH CHECK ==="
curl -s http://localhost:8080/health 2>/dev/null
echo ""

echo ""
echo "=== OLLAMA MODELS ==="
ollama list

echo ""
echo "=== ORTHANC ==="
curl -s http://localhost:8042/system 2>/dev/null | head -5

echo ""
echo "=== DOCKER ==="
sg docker -c 'docker ps --format "{{.Names}}: {{.Status}}"'

echo ""
echo "=== API ROUTES ==="
curl -s http://localhost:8080/openapi.json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for path, methods in data.get('paths', {}).items():
        for method in methods:
            print(f'  {method.upper():6s} {path}')
except:
    print('Could not parse API schema')
"
