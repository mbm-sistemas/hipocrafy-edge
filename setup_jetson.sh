#!/bin/bash
# ==============================================================================
# Setup Script for Jetson Orin (Nano/Super) - Hipocrafy Edge Gateway
# ==============================================================================
# This script automates the installation of dependencies, Ollama, and the AI models
# required to run the Edge Gateway in a Jetson environment with JetPack 6.2.
# ==============================================================================

set -e

echo "========================================"
echo " Starting Jetson Edge Setup...          "
echo "========================================"

# 1. Update system packages
echo ">>> Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl python3-pip python3-venv git htop jtop build-essential

# 2. Setup Python Virtual Environment
echo ">>> Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created."
else
    echo "Virtual environment already exists."
fi

echo ">>> Activating virtual environment and installing requirements..."
source venv/bin/activate
pip install --upgrade pip

# Note: In Jetson, PyTorch with CUDA support usually requires installing a specific .whl
# from NVIDIA. The following pip install will attempt to fetch compatible versions.
# If faster-whisper fails to detect CUDA, you may need to install the NVIDIA-specific PyTorch:
# pip3 install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# 3. Install Ollama
echo ">>> Installing Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.com/install.sh | sh
    echo "Ollama installed successfully."
else
    echo "Ollama is already installed."
fi

# 4. Start Ollama Service in the background temporarily to pull models
echo ">>> Ensuring Ollama service is running..."
sudo systemctl enable ollama
sudo systemctl start ollama
sleep 5 # Wait for the service to start

# 5. Pull AI Models
echo ">>> Pulling LLM Model (llama3:8b)..."
ollama pull llama3:8b

echo ">>> Pulling Embedding Model (nomic-embed-text)..."
ollama pull nomic-embed-text

# 6. Setup ChromaDB Storage
echo ">>> Setting up local storage directories..."
mkdir -p data/chromadb
mkdir -p data/temp_audio

echo "========================================"
echo " Setup Completed Successfully!          "
echo "========================================"
echo ""
echo "To start the Hipocrafy Edge Gateway, run:"
echo "  source venv/bin/activate"
echo "  uvicorn main:app --host 0.0.0.0 --port 8080"
echo "========================================"
