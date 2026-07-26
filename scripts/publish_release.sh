#!/usr/bin/env bash
# Empaqueta el estado actual de hipocrafy-edge y lo registra como una release
# nueva en el backend (sin publicar todavía). Un admin la publica desde
# /admin/edge-releases cuando quiera que los equipos conectados la instalen.
#
# Uso:
#   HIPOCRAFY_CLOUD_URL=https://qas.hipocrafy... EDGE_RELEASE_TOKEN=xxx ./scripts/publish_release.sh
#
# Requiere estar parado en la raíz del repo hipocrafy-edge.

set -euo pipefail

if [ -z "${HIPOCRAFY_CLOUD_URL:-}" ] || [ -z "${EDGE_RELEASE_TOKEN:-}" ]; then
  echo "Faltan HIPOCRAFY_CLOUD_URL y/o EDGE_RELEASE_TOKEN en el entorno." >&2
  exit 1
fi

VERSION=$(git rev-parse --short HEAD)
NOTES=$(git log -1 --pretty=%s)
TARBALL="/tmp/hipocrafy-edge-${VERSION}.tar.gz"

echo "Empaquetando version ${VERSION}..."

# Mismos excludes que deploy-edge.yml, más VERSION que se sobreescribe con el
# git sha real (el del repo local queda en "dev", no sirve para comparar).
echo "${VERSION}" > VERSION

tar --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='venv' \
    --exclude='estudios_recibidos' \
    --exclude='estudios_procesados' \
    --exclude='edge_data.db' \
    --exclude='*.log' \
    --exclude='models' \
    -czf "${TARBALL}" .

git checkout -- VERSION 2>/dev/null || true

BASE_URL="${HIPOCRAFY_CLOUD_URL%/api}"

echo "Subiendo release ${VERSION} a ${BASE_URL}..."
curl -sf -X POST "${BASE_URL}/api/internal/edge-releases" \
  -H "Authorization: Bearer ${EDGE_RELEASE_TOKEN}" \
  -F "version=${VERSION}" \
  -F "notes=${NOTES}" \
  -F "package=@${TARBALL}"

echo
echo "Listo. Publicala desde /admin/edge-releases cuando quieras que los equipos la instalen."

rm -f "${TARBALL}"
