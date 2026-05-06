FROM python:3.11-slim

# Install system deps: ADB, build tools for native Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev

# Copy source
COPY src/ src/
COPY plugins/ plugins/

# Pull default Ollama models on first run via entrypoint (handled by startup)
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "androbugger.main:app", "--host", "0.0.0.0", "--port", "8000"]
