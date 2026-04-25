#!/usr/bin/env bash
# ─── ClipForge — Start Script ──────────────────────────────────────────────────
# Inicia backend e frontend em paralelo.
# Uso: ./start.sh

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

log()  { echo -e "${GREEN}[ClipForge]${NC} $1"; }
warn() { echo -e "${YELLOW}[aviso]${NC} $1"; }
die()  { echo -e "${RED}[erro]${NC} $1"; exit 1; }

# ── Verificações ────────────────────────────────────────────────────────────────
command -v python3 >/dev/null || die "Python 3 não encontrado."
command -v node    >/dev/null || die "Node.js não encontrado."
command -v ffmpeg  >/dev/null || die "FFmpeg não encontrado. Instale com: brew install ffmpeg"
command -v npm     >/dev/null || die "npm não encontrado."

if [ ! -f "$ROOT/.env" ]; then
  warn ".env não encontrado — copiando .env.example..."
  cp "$ROOT/.env.example" "$ROOT/.env"
  warn "Edite o arquivo .env antes de continuar!"
fi

# ── Backend ─────────────────────────────────────────────────────────────────────
BACKEND="$ROOT/backend"
VENV="$BACKEND/venv"

if [ ! -d "$VENV" ]; then
  log "Criando ambiente virtual Python..."
  python3 -m venv "$VENV"
fi

log "Instalando dependências do backend..."
"$VENV/bin/pip" install -q -r "$BACKEND/requirements.txt"

log "Iniciando backend (porta 8000)..."
cd "$BACKEND"
"$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# ── Frontend ────────────────────────────────────────────────────────────────────
FRONTEND="$ROOT/frontend"

if [ ! -d "$FRONTEND/node_modules" ]; then
  log "Instalando dependências do frontend..."
  cd "$FRONTEND" && npm install -q
fi

log "Iniciando frontend (porta 5173)..."
cd "$FRONTEND"
npm run dev &
FRONTEND_PID=$!

# ── Cleanup ─────────────────────────────────────────────────────────────────────
trap "log 'Encerrando...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM

log "✅ ClipForge rodando!"
echo ""
echo -e "  Frontend: ${GREEN}http://localhost:5173${NC}"
echo -e "  API docs: ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo "  Pressione Ctrl+C para encerrar."
echo ""

wait
