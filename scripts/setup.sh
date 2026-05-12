#!/usr/bin/env bash
# Guided Docker setup for Androbugger.
# Usage: ./scripts/setup.sh

set -euo pipefail

# ── Locate repo root ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f docker-compose.yml ]]; then
  echo "ERROR: docker-compose.yml not found in $REPO_ROOT" >&2
  echo "       Run this script from inside the Androbugger repo." >&2
  exit 1
fi

# ── Color helpers ────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'
  C_BLUE=$'\033[34m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'
else
  C_RESET=''; C_BOLD=''; C_BLUE=''; C_GREEN=''; C_YELLOW=''; C_RED=''
fi

info()  { printf '%s>>%s %s\n' "$C_BLUE"   "$C_RESET" "$*"; }
ok()    { printf '%s✓%s  %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn()  { printf '%s!%s  %s\n' "$C_YELLOW" "$C_RESET" "$*"; }
err()   { printf '%s✗%s  %s\n' "$C_RED"    "$C_RESET" "$*" >&2; }
hdr()   { printf '\n%s== %s ==%s\n' "$C_BOLD" "$*" "$C_RESET"; }

CURRENT_STEP="initialization"
on_error() {
  err "Setup failed during: $CURRENT_STEP"
  err "Last command exited with status $?"
  echo  "Re-run ./scripts/setup.sh once the issue is resolved." >&2
}
on_interrupt() {
  echo
  warn "Setup interrupted. Re-run ./scripts/setup.sh to resume."
  warn "Any answers already written to .env are preserved."
  exit 130
}
trap on_error ERR
trap on_interrupt INT TERM

# ── Step 1: prerequisites ────────────────────────────────────────────────────
CURRENT_STEP="prerequisite check"
hdr "Checking prerequisites"

require_cmd() {
  local cmd="$1" hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "Missing required command: $cmd"
    echo  "    $hint" >&2
    exit 1
  fi
  ok "$cmd found"
}

require_cmd docker  "Install Docker Engine 24+: https://docs.docker.com/engine/install/"
require_cmd openssl "Install with your package manager (e.g. apt install openssl)."

if ! docker compose version >/dev/null 2>&1; then
  err "Docker Compose v2 plugin not found."
  echo "    Install: https://docs.docker.com/compose/install/" >&2
  exit 1
fi
ok "docker compose v2 found"

if ! docker info >/dev/null 2>&1; then
  warn "Cannot talk to the Docker daemon as the current user."
  warn "You may need to run this script with sudo, or add your user to the 'docker' group:"
  warn "    sudo usermod -aG docker \"\$USER\" && newgrp docker"
fi

# ── Step 2: locate .env.default ──────────────────────────────────────────────
CURRENT_STEP=".env.default lookup"
if [[ ! -f .env.default ]]; then
  err ".env.default is missing from the repository root."
  err "This is unexpected — make sure your checkout is complete."
  exit 1
fi

# ── Step 3: .env handling ────────────────────────────────────────────────────
CURRENT_STEP=".env file setup"
hdr "Creating .env"

WRITE_ENV=1
if [[ -f .env ]]; then
  warn ".env already exists."
  read -r -p "Overwrite it with fresh values? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    WRITE_ENV=0
    info "Keeping existing .env. Skipping SECRET_KEY and LLM prompts."
  fi
fi

if [[ "$WRITE_ENV" -eq 1 ]]; then
  cp .env.default .env
  ok "Copied .env.default → .env"
fi

# ── Step 4: SECRET_KEY ───────────────────────────────────────────────────────
CURRENT_STEP="SECRET_KEY generation"
GENERATED_SECRET=""
if [[ "$WRITE_ENV" -eq 1 ]]; then
  GENERATED_SECRET="$(openssl rand -hex 32)"
  # Use | as sed delimiter — hex output has no | so no escaping needed.
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${GENERATED_SECRET}|" .env
  rm -f .env.bak
  ok "Generated a 64-character SECRET_KEY"
fi

# ── Step 5: LLM provider ─────────────────────────────────────────────────────
CURRENT_STEP="LLM provider selection"
LLM_CHOICE=1
LLM_MODEL_LINE=""
LLM_KEY_LINE=""

if [[ "$WRITE_ENV" -eq 1 ]]; then
  hdr "LLM provider"
  echo "  1) Local Ollama (default — no API key, models run on this machine)"
  echo "  2) Anthropic Claude (cloud — requires API key)"
  echo "  3) OpenAI GPT (cloud — requires API key)"
  echo "  4) Skip — I'll configure later"
  while true; do
    read -r -p "Choose [1-4, default 1]: " LLM_CHOICE
    LLM_CHOICE="${LLM_CHOICE:-1}"
    case "$LLM_CHOICE" in
      1|2|3|4) break ;;
      *) warn "Please enter 1, 2, 3, or 4." ;;
    esac
  done

  case "$LLM_CHOICE" in
    1) ok "Using local Ollama (defaults from .env.default)." ;;
    2)
      read -r -s -p "ANTHROPIC_API_KEY (input hidden): " api_key; echo
      if [[ -z "$api_key" ]]; then
        warn "No key entered — leaving Anthropic disabled."
        LLM_CHOICE=4
      else
        LLM_MODEL_LINE="ANDROBUGGER_DEFAULT_LLM_MODEL=anthropic/claude-sonnet-4-6"
        LLM_KEY_LINE="ANTHROPIC_API_KEY=${api_key}"
        printf '\n# Added by setup.sh\n%s\n%s\n' "$LLM_MODEL_LINE" "$LLM_KEY_LINE" >> .env
        ok "Configured Anthropic Claude."
      fi
      ;;
    3)
      read -r -s -p "OPENAI_API_KEY (input hidden): " api_key; echo
      if [[ -z "$api_key" ]]; then
        warn "No key entered — leaving OpenAI disabled."
        LLM_CHOICE=4
      else
        LLM_MODEL_LINE="ANDROBUGGER_DEFAULT_LLM_MODEL=openai/gpt-4o"
        LLM_KEY_LINE="OPENAI_API_KEY=${api_key}"
        printf '\n# Added by setup.sh\n%s\n%s\n' "$LLM_MODEL_LINE" "$LLM_KEY_LINE" >> .env
        ok "Configured OpenAI."
      fi
      ;;
    4) info "Skipping LLM configuration. Edit .env later to enable." ;;
  esac
fi

# ── Step 6: deployment method ────────────────────────────────────────────────
CURRENT_STEP="deployment method selection"
hdr "Deployment method"
echo "  1) Direct docker compose on this machine (default)"
echo "  2) Portainer or another Docker GUI"
while true; do
  read -r -p "Choose [1-2, default 1]: " DEPLOY_MODE
  DEPLOY_MODE="${DEPLOY_MODE:-1}"
  case "$DEPLOY_MODE" in
    1|2) break ;;
    *) warn "Please enter 1 or 2." ;;
  esac
done

# ── Step 7: data directory info ──────────────────────────────────────────────
info "Data (bugreports, parsed logs, SQLite DB, indexes) persists in the"
info "'androbugger_data' Docker named volume. Backups: 'docker volume inspect'."

if [[ "$DEPLOY_MODE" == "1" ]]; then
  # ── Step 8: start services ─────────────────────────────────────────────────
  CURRENT_STEP="docker compose up"
  hdr "Start services"
  read -r -p "Run 'docker compose up -d' now? [Y/n] " reply
  reply="${reply:-Y}"
  if [[ "$reply" =~ ^[Yy]$ ]]; then
    info "Starting stack — this may take a minute on first run..."
    docker compose up -d
    docker compose ps
    SERVICES_UP=1
  else
    info "Skipping. To start later:  docker compose up -d"
    SERVICES_UP=0
  fi

  # ── Step 9: pull Ollama models ─────────────────────────────────────────────
  CURRENT_STEP="ollama model pull"
  if [[ "${SERVICES_UP:-0}" == "1" && "$LLM_CHOICE" == "1" ]]; then
    hdr "Ollama models"
    read -r -p "Pull qwen3:14b and nomic-embed-text now? (~8 GB, ~10 min) [y/N] " reply
    if [[ "$reply" =~ ^[Yy]$ ]]; then
      info "Pulling qwen3:14b..."
      docker compose exec ollama ollama pull qwen3:14b
      info "Pulling nomic-embed-text..."
      docker compose exec ollama ollama pull nomic-embed-text
      ok "Models ready."
    else
      info "Skipping. To pull later:"
      info "    docker compose exec ollama ollama pull qwen3:14b"
      info "    docker compose exec ollama ollama pull nomic-embed-text"
    fi
  fi

  # ── Final: direct mode ─────────────────────────────────────────────────────
  hdr "Setup complete"
  echo "  Open:       http://localhost"
  echo "  First login: admin / admin  (you'll be forced to change password)"
  echo "  Logs:       docker compose logs -f backend"
  echo "  .env path:  $REPO_ROOT/.env"

else
  # ── Step 10: Portainer mode — emit env block ───────────────────────────────
  CURRENT_STEP="portainer env block output"
  hdr "Portainer environment variables"

  ENV_BLOCK=""
  if [[ -n "${GENERATED_SECRET:-}" ]]; then
    ENV_BLOCK+="SECRET_KEY=${GENERATED_SECRET}"$'\n'
  else
    # User kept their existing .env — pull SECRET_KEY back out of it.
    existing_secret="$(grep -E '^SECRET_KEY=' .env | head -n1 | cut -d= -f2- || true)"
    if [[ -n "$existing_secret" ]]; then
      ENV_BLOCK+="SECRET_KEY=${existing_secret}"$'\n'
    else
      warn "No SECRET_KEY found in existing .env — generate one with:"
      warn "    openssl rand -hex 32"
    fi
  fi
  [[ -n "$LLM_MODEL_LINE" ]] && ENV_BLOCK+="${LLM_MODEL_LINE}"$'\n'
  [[ -n "$LLM_KEY_LINE"   ]] && ENV_BLOCK+="${LLM_KEY_LINE}"$'\n'

  echo
  echo "──── Paste into Portainer → Stacks → (your stack) → Environment variables ────"
  printf '%s' "$ENV_BLOCK"
  echo "──────────────────────────────────────────────────────────────────────────────"
  echo

  read -r -p "Save this block to ./portainer-env.txt as well? [y/N] " reply
  if [[ "$reply" =~ ^[Yy]$ ]]; then
    printf '%s' "$ENV_BLOCK" > portainer-env.txt
    chmod 600 portainer-env.txt
    ok "Wrote portainer-env.txt (mode 600). Treat it like a password — it contains secrets."
  fi

  hdr "Next steps (Portainer)"
  echo "  1. In Portainer: Stacks → Add stack → Repository or Upload"
  echo "     Point it at this repo's docker-compose.yml."
  echo "  2. Paste the env block above into the Environment variables editor."
  echo "  3. Deploy the stack."
  echo "  4. After it's running, open the 'ollama' container console and run:"
  echo "         ollama pull qwen3:14b"
  echo "         ollama pull nomic-embed-text"
  echo "  5. Browse to the host's port 80 and log in as admin / admin."
  echo
  echo "  See README.md → 'Portainer GUI deployment' for the full walkthrough."
fi
