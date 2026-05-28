#!/usr/bin/env bash
# Androbugger native Linux installer (Debian/Ubuntu).
#
# Installs all components directly on the host as systemd services:
#   - backend (FastAPI) on 127.0.0.1:8000, serving the built frontend
#   - redis-server on 127.0.0.1:6379 (for the arq job queue)
#   - ollama on 127.0.0.1:11434 (local LLM)
#   - ADB via android-sdk-platform-tools (USB access via plugdev + udev rules)
#
# Layout:
#   /opt/androbugger          - application code (this checkout, copied)
#   /etc/androbugger          - androbugger.env (EnvironmentFile for systemd)
#   /var/lib/androbugger      - app data (SQLite, chroma, tantivy, bugreports)
#
# Usage:  sudo ./scripts/install.sh

set -euo pipefail

INSTALL_DIR="/opt/androbugger"
CONFIG_DIR="/etc/androbugger"
DATA_DIR="/var/lib/androbugger"
SERVICE_USER="androbugger"
ENV_FILE="${CONFIG_DIR}/androbugger.env"
UNIT_FILE="/etc/systemd/system/androbugger-backend.service"

log()  { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 0. Preflight
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run as root (use sudo)."

if ! command -v apt-get >/dev/null 2>&1; then
    die "This installer targets Debian/Ubuntu (apt-get not found)."
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
log "Repository root: ${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
log "Installing system packages via apt..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip \
    android-sdk-platform-tools android-sdk-platform-tools-common \
    nodejs npm \
    redis-server \
    build-essential libffi-dev \
    openssl ca-certificates curl

# Node 22+ is required for the frontend build. apt on older releases may ship
# Node 18; if so, install via NodeSource.
NODE_MAJOR=$(node -v 2>/dev/null | sed -E 's/v([0-9]+)\..*/\1/' || echo 0)
if [[ "${NODE_MAJOR}" -lt 20 ]]; then
    warn "Detected Node ${NODE_MAJOR}; installing Node 22 from NodeSource."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
fi

# ---------------------------------------------------------------------------
# 2. uv (Python package manager)
# ---------------------------------------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
    log "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh
fi

# ---------------------------------------------------------------------------
# 3. Ollama
# ---------------------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
    log "Installing Ollama via official installer..."
    curl -fsSL https://ollama.com/install.sh | sh
fi
systemctl enable --now ollama

log "Waiting for ollama to accept connections..."
for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi
    sleep 1
done

pull_model() {
    local model="$1"
    if ollama list 2>/dev/null | awk 'NR>1 {print $1}' | grep -qx "${model}"; then
        log "Ollama model already present: ${model}"
    else
        log "Pulling Ollama model: ${model} (this may take a while)..."
        ollama pull "${model}"
    fi
}
pull_model "qwen3:14b"
pull_model "qwen3:8b"
pull_model "nomic-embed-text"

# ---------------------------------------------------------------------------
# 4. Service user, directories
# ---------------------------------------------------------------------------
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
    log "Creating system user '${SERVICE_USER}'..."
    useradd --system --create-home --home-dir "/var/lib/${SERVICE_USER}-home" \
            --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
usermod -aG plugdev "${SERVICE_USER}"

install -d -o "${SERVICE_USER}" -g "${SERVICE_USER}" -m 0755 "${INSTALL_DIR}" "${DATA_DIR}"
install -d -o root            -g root            -m 0755 "${CONFIG_DIR}"

# ---------------------------------------------------------------------------
# 5. Sync source into /opt/androbugger
# ---------------------------------------------------------------------------
log "Syncing source to ${INSTALL_DIR}..."
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
        --exclude='.git' --exclude='node_modules' --exclude='.venv' \
        --exclude='__pycache__' --exclude='dist' \
        "${REPO_ROOT}/" "${INSTALL_DIR}/"
else
    # rsync absent: fall back to cp (no --delete behavior)
    cp -a "${REPO_ROOT}/." "${INSTALL_DIR}/"
fi
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# ---------------------------------------------------------------------------
# 6. Build backend venv and frontend bundle
# ---------------------------------------------------------------------------
log "Building backend venv with uv..."
sudo -u "${SERVICE_USER}" -H bash -lc "cd '${INSTALL_DIR}/backend' && uv sync --frozen --no-dev"

log "Building frontend bundle with npm..."
sudo -u "${SERVICE_USER}" -H bash -lc "cd '${INSTALL_DIR}/frontend' && npm ci && npm run build"

# ---------------------------------------------------------------------------
# 7. /etc/androbugger/androbugger.env
# ---------------------------------------------------------------------------
if [[ ! -f "${ENV_FILE}" ]]; then
    log "Generating ${ENV_FILE}..."
    SECRET_KEY="$(openssl rand -hex 32)"
    cat > "${ENV_FILE}" <<EOF
# Generated by scripts/install.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
SECRET_KEY=${SECRET_KEY}
ANDROBUGGER_SECRET_KEY=${SECRET_KEY}
ANDROBUGGER_OLLAMA_BASE_URL=http://127.0.0.1:11434
ANDROBUGGER_REDIS_URL=redis://127.0.0.1:6379
ANDROBUGGER_DATA_DIR=${DATA_DIR}
ANDROBUGGER_DB_PATH=${DATA_DIR}/androbugger.db
ANDROBUGGER_FRONTEND_DIST=${INSTALL_DIR}/frontend/dist
ANDROBUGGER_PLUGIN_DIR=${INSTALL_DIR}/backend/plugins
EOF
    chmod 0640 "${ENV_FILE}"
    chown root:"${SERVICE_USER}" "${ENV_FILE}"
else
    log "Existing ${ENV_FILE} found, leaving it untouched."
fi

# ---------------------------------------------------------------------------
# 8. systemd unit
# ---------------------------------------------------------------------------
log "Installing systemd unit ${UNIT_FILE}..."
install -m 0644 "${INSTALL_DIR}/systemd/androbugger-backend.service" "${UNIT_FILE}"

systemctl daemon-reload
systemctl enable --now redis-server
systemctl enable --now ollama
systemctl enable --now androbugger-backend

# ---------------------------------------------------------------------------
# 9. Done
# ---------------------------------------------------------------------------
log "Installation complete."
cat <<EOF

  Androbugger is now installed.

    Backend:   http://$(hostname -I 2>/dev/null | awk '{print $1}'):8000
    Config:    ${ENV_FILE}
    Data:      ${DATA_DIR}
    Logs:      journalctl -u androbugger-backend -f

  First login: admin / admin  (you will be forced to change the password).

  Plug in an Android device with USB debugging enabled and accept the
  "Allow USB debugging" prompt on the phone. The device should appear in
  the Devices page within a few seconds.
EOF
