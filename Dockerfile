# GPU (default): docker build .
# CPU/NAS:       docker build --build-arg BASE=ubuntu:22.04 .
ARG BASE=nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# ── Stage 1: Build the React frontend ────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build
# Output is in /build/frontend/dist


# ── Stage 2: Production image ─────────────────────────────────────────────────
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# System deps: Python, OpenCV runtime libs, libGL (needed by OpenCV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Make python3.11 the default python
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.11 /usr/bin/python

WORKDIR /app

# Install Python dependencies
# Pre-install CUDA-enabled PyTorch when building the GPU image so that
# ultralytics (which depends on torch) doesn't pull the CPU build from PyPI.
ARG CUDA_TORCH=false
RUN if [ "$CUDA_TORCH" = "true" ]; then \
      pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu121; \
    fi

COPY server/requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy server source
COPY server/ ./

# Copy built frontend into server/static so FastAPI can serve it
COPY --from=frontend-build /build/frontend/dist ./static

# Data directory — will be mounted as a volume so data persists
RUN mkdir -p /villapro-data/projects /villapro-data/models /villapro-data/config \
             /villapro-data/recordings /villapro-data/debug /villapro-data/datasets

# Default environment — override in docker-compose or with -e flags
ENV VISIONQ_DATA=/villapro-data
ENV VISIONQ_SECRET=change-me-in-production

EXPOSE 8000

CMD ["python3", "main.py", "--host", "0.0.0.0", "--port", "8000"]
