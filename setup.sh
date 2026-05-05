#!/usr/bin/env bash
# VisionQ — one-time setup script
# Run as a regular user with sudo privileges (not as root).
# Usage: bash setup.sh

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✔]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
step()  { echo -e "${CYAN}[→]${NC} $*"; }
error() { echo -e "${RED}[✘] ERROR:${NC} $*" >&2; exit 1; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║        VisionQ Setup Installer       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── 1. Platform check ────────────────────────────────────────────────────────
[[ "$(uname)" == "Linux" ]] || error "This installer only supports Linux (Ubuntu)."
if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    warn "OS is not Ubuntu — proceeding anyway, but this is untested."
fi

# ── 2. Docker ─────────────────────────────────────────────────────────────────
step "Checking Docker..."
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    info "Docker is already installed ($(docker --version))"
else
    step "Docker not found — installing via get.docker.com..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    warn "Added '$USER' to the docker group."
    warn "You must log out and back in (or run 'newgrp docker') before Docker works without sudo."
    info "Docker installed."
fi

# ── 3. Docker Compose plugin ──────────────────────────────────────────────────
step "Checking Docker Compose..."
if docker compose version &>/dev/null 2>&1; then
    info "Docker Compose is available ($(docker compose version --short))"
else
    step "Docker Compose plugin not found — installing..."
    sudo apt-get update -qq
    sudo apt-get install -y docker-compose-plugin
    info "Docker Compose installed."
fi

# ── 4. NVIDIA driver + container toolkit (optional but needed for GPU) ────────
step "Checking NVIDIA GPU support..."
if ! command -v nvidia-smi &>/dev/null; then
    warn "nvidia-smi not found — skipping GPU setup."
    warn "VisionQ will run in CPU-only mode. Install NVIDIA drivers first if you need GPU inference."
else
    info "NVIDIA driver detected: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)"

    if ! dpkg -s nvidia-container-toolkit &>/dev/null 2>&1; then
        step "NVIDIA Container Toolkit not found — installing..."
        distribution=$(. /etc/os-release; echo "${ID}${VERSION_ID}")
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
            | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" \
            | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
            | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        sudo apt-get update -qq
        sudo apt-get install -y nvidia-container-toolkit
        sudo systemctl restart docker
        info "NVIDIA Container Toolkit installed."
    else
        info "NVIDIA Container Toolkit is already installed."
    fi
fi

# ── 5. .env file ──────────────────────────────────────────────────────────────
step "Checking .env configuration..."
if [[ -f .env ]]; then
    info ".env already exists — skipping generation."
else
    if [[ ! -f .env.example ]]; then
        error ".env.example not found. Make sure you are running this script from the VisionQ directory."
    fi

    # Generate a strong secret
    if command -v openssl &>/dev/null; then
        SECRET=$(openssl rand -hex 32)
    else
        SECRET=$(tr -dc 'a-f0-9' < /dev/urandom | fold -w 64 | head -n 1)
    fi

    cp .env.example .env
    sed -i "s|^VISIONQ_SECRET=.*|VISIONQ_SECRET=${SECRET}|" .env
    info ".env created with a generated secret."
fi

# Validate that VISIONQ_SECRET is actually set
# shellcheck disable=SC1091
source .env 2>/dev/null || true
if [[ -z "${VISIONQ_SECRET:-}" ]]; then
    error "VISIONQ_SECRET is empty in .env. Please set it to a strong random value (openssl rand -hex 32)."
fi

# ── 6. Create data directory ───────────────────────────────────────────────────
DATA_DIR="${VISIONQ_DATA_DIR:-./villapro-data}"
if [[ ! -d "$DATA_DIR" ]]; then
    mkdir -p "$DATA_DIR"
    info "Created data directory: $DATA_DIR"
else
    info "Data directory already exists: $DATA_DIR"
fi

# ── 7. Pull image and start ───────────────────────────────────────────────────
step "Pulling VisionQ image..."
docker compose pull

step "Starting VisionQ..."
docker compose up -d

PORT="${VISIONQ_PORT:-8000}"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   VisionQ is up and running!             ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║   Open: http://$(hostname -I | awk '{print $1}'):${PORT}          ║${NC}"
echo -e "${GREEN}║   Docs: http://$(hostname -I | awk '{print $1}'):${PORT}/docs     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "To stop:    docker compose down"
echo "To update:  docker compose pull && docker compose up -d"
echo "To logs:    docker compose logs -f"
echo ""
