#!/bin/bash
# DVAIA - Damn Vulnerable AI Application
# Docker Compose wrapper: Flask app + Qdrant, with optional Ollama.
#
# All LLM calls route through LiteLLM, so any provider works once its API key
# is in .env. The Ollama service is only needed for local model inference.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

LOCAL_FLAG=false
NO_OLLAMA_FLAG=false
SKIP_PROMPT=false

for arg in "$@"; do
  case "$arg" in
    --local|--ollama)
      LOCAL_FLAG=true
      ;;
    --no-ollama|--cloud)
      NO_OLLAMA_FLAG=true
      ;;
    --skip-prompt|--yes|-y)
      SKIP_PROMPT=true
      ;;
    -h|--help)
      echo "Usage: $0 [OPTIONS] [docker compose args...]"
      echo ""
      echo "Interactive setup runs when no mode flag is set and stdin is a TTY."
      echo "Use ./run_docker.sh instead of 'docker compose up' directly."
      echo ""
      echo "Options:"
      echo "  (default)       Prompt for local Ollama vs cloud-only"
      echo "  --local         Local Ollama stack (~9–10 GB model downloads)"
      echo "  --no-ollama     Skip Ollama service — cloud providers via API keys"
      echo "  --skip-prompt   Default to local Ollama; no prompt"
      echo "  -y, --yes       Same as --skip-prompt"
      echo ""
      echo "Cloud providers require API keys in .env. See .env.example."
      echo "Set DVAIA_SKIP_MODE_PROMPT=1 to always skip the interactive prompt."
      exit 0
      ;;
  esac
done

is_truthy() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_env_file() {
  if [ -f .env ]; then
    return 0
  fi
  echo ""
  echo "No .env file found."
  if [ -f .env.example ]; then
    read -r -p "Copy .env.example to .env now? [Y/n]: " copy_env
    copy_env="${copy_env:-Y}"
    if [[ "$copy_env" =~ ^[Yy]$ ]]; then
      cp .env.example .env
      echo "Created .env — edit it to add API keys for cloud providers."
      return 0
    fi
  fi
  echo "Warning: continuing without .env (docker-compose defaults only)."
  return 0
}

print_local_info() {
  cat <<'EOF'

  LOCAL (Ollama) — full stack with on-device LLMs

  What you need:
    • Copy .env.example to .env (no API keys required for Ollama)
    • Docker with Compose v2
    • Disk: ~9–10 GB for Ollama models on first start
    • RAM: 8–16 GB recommended for CPU inference

  Models pulled automatically on first start:
    • llama3.2          (~2 GB)   — chat / main panels
    • nomic-embed-text  (~275 MB) — RAG embeddings
    • qwen3:0.6b        (~400 MB) — Agentic / chain-of-thought
    • qwen2.5vl:7b      (~6 GB)   — Document Injection vision

  First startup can take several minutes while models download.
  After startup, pick a model in Settings (defaults to ollama/llama3.2).
EOF
}

print_cloud_info() {
  cat <<'EOF'

  CLOUD — no Ollama container, no local LLM downloads

  Set whichever provider keys you want in .env:
    • OPENAI_API_KEY      — https://platform.openai.com/api-keys
    • GEMINI_API_KEY      — https://aistudio.google.com/apikey
    • ANTHROPIC_API_KEY   — https://console.anthropic.com/settings/keys
    • GROQ_API_KEY, OPENROUTER_API_KEY, ... (any LiteLLM provider)

  Then point DEFAULT_MODEL at a 'provider/model' id, e.g.
    DEFAULT_MODEL=openai/gpt-4o-mini
    EMBEDDING_MODEL=openai/text-embedding-3-small

  After startup, pick the provider/model in Settings.
  Whisper/OCR still run locally in the app container.
EOF
}

prompt_for_mode() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║           DVAIA — choose how to run LLMs in Docker           ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  1) Local (Ollama)     — download and run models in Docker"
  echo "  2) Cloud only         — skip Ollama; use API keys for any provider"
  echo ""
  echo "  h) Show requirements for an option before choosing"
  echo "  q) Quit"
  echo ""

  while true; do
    read -r -p "Enter choice [1/2] (default: 1): " choice
    choice="${choice:-1}"
    case "$choice" in
      1)
        print_local_info
        read -r -p "Start with local Ollama? [Y/n]: " confirm
        confirm="${confirm:-Y}"
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
          LOCAL_FLAG=true
          return 0
        fi
        ;;
      2)
        print_cloud_info
        read -r -p "Start cloud-only (no Ollama)? [Y/n]: " confirm
        confirm="${confirm:-Y}"
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
          NO_OLLAMA_FLAG=true
          return 0
        fi
        ;;
      h|H)
        echo ""
        echo "Which option do you want details for?"
        echo "  1 = Local Ollama   2 = Cloud only"
        read -r -p "Choice: " help_choice
        case "$help_choice" in
          1) print_local_info ;;
          2) print_cloud_info ;;
          *) echo "Unknown option." ;;
        esac
        echo ""
        ;;
      q|Q)
        echo "Aborted."
        exit 0
        ;;
      *)
        echo "Invalid choice. Enter 1, 2, h, or q."
        ;;
    esac
  done
}

# Load .env when present (may be created interactively below)
load_env() {
  if [ -f .env ]; then
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
  fi
}

MODE_EXPLICIT=false
if [ "$LOCAL_FLAG" = true ] || [ "$NO_OLLAMA_FLAG" = true ]; then
  MODE_EXPLICIT=true
fi

if [ "$SKIP_PROMPT" = false ] && [ "$MODE_EXPLICIT" = false ] && is_truthy "${DVAIA_SKIP_MODE_PROMPT:-false}"; then
  SKIP_PROMPT=true
fi

# Interactive mode selection (TTY only, no flags)
if [ "$SKIP_PROMPT" = false ] && [ "$MODE_EXPLICIT" = false ]; then
  if [ -t 0 ]; then
    ensure_env_file
    load_env
    prompt_for_mode
    MODE_EXPLICIT=true
  fi
fi

load_env

echo "Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

COMPOSE_ARGS=(up --build)

if [ "$NO_OLLAMA_FLAG" = true ]; then
  export OLLAMA_HOST=""
  echo ""
  echo "Cloud-only mode: starting Qdrant + DVAIA (skipping Ollama — no local LLM downloads)"
  echo "  Set DEFAULT_MODEL and provider API keys in .env. See ./run_docker.sh --help."
  echo "  Whisper/OCR still run locally in the app container for audio/image tests."
  echo ""
else
  # Default to local Ollama stack.
  export OLLAMA_HOST="http://ollama:11434"
  COMPOSE_ARGS=(--profile ollama "${COMPOSE_ARGS[@]}")
  echo ""
  echo "Local mode: building and running DVAIA with Ollama + Qdrant..."
  echo "First startup downloads llama3.2, nomic-embed-text, qwen3:0.6b, qwen2.5vl:7b (may take several minutes)"
  echo "Requirements: ~9–10 GB disk, 8–16 GB RAM recommended. See: ./run_docker.sh --help"
  echo ""
fi

docker compose "${COMPOSE_ARGS[@]}"
