#!/bin/bash
sleep 5
echo "=== PLUGINS ==="
curl -s http://localhost:8042/plugins
echo ""
echo "=== EXPLORER2 ==="
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8042/ui/app/)
echo "HTTP $CODE"
echo "=== STONE VIEWER ==="
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8042/stone-webviewer/index.html)
echo "HTTP $CODE"
echo "=== DICOMWEB ==="
CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8042/dicom-web/studies)
echo "HTTP $CODE"
echo "=== DOCKER LOGS ==="
sg docker -c 'docker logs hipocrafy-edge-orthanc-1 2>&1' | grep -iE 'plugin|stone|dicom-web|explorer|error|enabled' | tail -20
