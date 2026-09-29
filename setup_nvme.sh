#!/bin/bash
set -e

echo "=========================================="
echo " Starting NVMe 1TB Storage Configuration  "
echo "=========================================="

# 1. Mount /data in fstab
echo ">>> 1. Configuring /etc/fstab for /data..."
sudo mkdir -p /data
if ! grep -q "NVME_DATA" /etc/fstab; then
    echo "LABEL=NVME_DATA /data ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab
fi
sudo mount -a

# 2. Directory structure
echo ">>> 2. Creating directory structure on /data..."
CURRENT_USER="${SUDO_USER:-$USER}"
sudo mkdir -p /data/docker /data/ollama /data/hipocrafy /data/projects
sudo chown -R "$CURRENT_USER:$CURRENT_USER" /data/hipocrafy /data/projects /data/ollama
sudo usermod -aG docker "$CURRENT_USER" 2>/dev/null || true

# 3. 16GB High-Speed Swapfile on NVMe
echo ">>> 3. Setting up 16GB NVMe swapfile..."
if [ ! -f /data/swapfile ]; then
    sudo fallocate -l 16G /data/swapfile
    sudo chmod 600 /data/swapfile
    sudo mkswap /data/swapfile
fi

if ! grep -q "/data/swapfile" /etc/fstab; then
    echo "/data/swapfile none swap sw,pri=10 0 0" | sudo tee -a /etc/fstab
fi
sudo swapon -a || true

# 4. Migrate Docker to NVMe
echo ">>> 4. Migrating Docker data-root to NVMe..."
sudo systemctl stop docker.socket || true
sudo systemctl stop docker || true

if [ -d /var/lib/docker ] && [ ! -d /data/docker/image ]; then
    echo "Copying existing Docker containers and images to /data/docker..."
    sudo rsync -aP /var/lib/docker/ /data/docker/
fi

sudo mkdir -p /etc/docker
cat << 'EOF_DOCKER' | sudo tee /etc/docker/daemon.json
{
  "data-root": "/data/docker"
}
EOF_DOCKER

sudo systemctl start docker

# 5. Migrate Ollama models to NVMe
echo ">>> 5. Migrating Ollama models to NVMe..."
sudo systemctl stop ollama || true

if [ -d /usr/share/ollama/.ollama ]; then
    if [ ! -d /data/ollama/models ]; then
        echo "Copying Ollama models to /data/ollama..."
        sudo rsync -aP /usr/share/ollama/.ollama/ /data/ollama/
    fi
    sudo rm -rf /usr/share/ollama/.ollama
    sudo ln -sfn /data/ollama /usr/share/ollama/.ollama
fi

sudo mkdir -p /etc/systemd/system/ollama.service.d
cat << 'EOF_OLLAMA' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_MODELS=/data/ollama/models"
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_ORIGINS=*"
EOF_OLLAMA

sudo systemctl daemon-reload
sudo systemctl start ollama

echo "=========================================="
echo " NVMe Storage Configuration Complete!     "
echo "=========================================="
df -h /data
swapon --show
docker info 2>/dev/null | grep "Docker Root Dir" || true
ollama list || true
