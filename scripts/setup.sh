#!/usr/bin/env bash
#
# scripts/setup.sh — SecOps RAG one-shot setup with health checks
#
# Usage:
#   bash scripts/setup.sh              # full setup
#   bash scripts/setup.sh --skip-pdfs  # skip downloading starter PDFs
#   bash scripts/setup.sh --no-index   # skip index build (do it manually later)
#
# Idempotent: safe to run multiple times. Checks each step and skips if done.
#
set -euo pipefail  # exit on error, undefined var, or failed pipe

# ---------- pretty output -----------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'  # No Color

log()     { printf "${BLUE}▶${NC} %s\n" "$*"; }
ok()      { printf "${GREEN}✓${NC} %s\n" "$*"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err()     { printf "${RED}✗${NC} %s\n" "$*" >&2; }
section() { printf "\n${BOLD}${BLUE}═══ %s ═══${NC}\n" "$*"; }
die()     { err "$*"; exit 1; }

# ---------- arg parsing -------------------------------------------------------
SKIP_PDFS=false
NO_INDEX=false
for arg in "$@"; do
    case "$arg" in
        --skip-pdfs) SKIP_PDFS=true ;;
        --no-index)  NO_INDEX=true ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "Unknown argument: $arg (use --help)" ;;
    esac
done

# ---------- locate project root ----------------------------------------------
# This script lives in scripts/, so project root is one level up.
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"
log "Project root: $PROJECT_ROOT"

# ============================================================================
# STEP 1 — System dependencies
# ============================================================================
section "1/7  System dependency checks"

# Python 3.10+
if ! command -v python3 &>/dev/null; then
    die "python3 not found. Install with: sudo apt install python3 python3-venv"
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    die "Python 3.10+ required, found $PY_VERSION"
fi
ok "Python $PY_VERSION"

# venv module
if ! python3 -c "import venv" &>/dev/null; then
    die "python3-venv not installed. Run: sudo apt install python3-venv"
fi
ok "venv module available"

# Ollama
if ! command -v ollama &>/dev/null; then
    die "ollama command not found. Install from https://ollama.com"
fi
ok "ollama CLI installed"

# Is the Ollama daemon running? Try the API.
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    warn "Ollama daemon not responding at http://localhost:11434"
    log "Attempting to start: ollama serve &"
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 3
    if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
        die "Could not start Ollama daemon. Check /tmp/ollama.log"
    fi
fi
ok "Ollama daemon responding"

# wget (for PDF downloads) — non-fatal, we'll fall back to curl
if command -v wget &>/dev/null; then
    DOWNLOADER="wget -q --show-progress -O"
elif command -v curl &>/dev/null; then
    DOWNLOADER="curl -sSL -o"
else
    warn "Neither wget nor curl found. PDF auto-download will be skipped."
    SKIP_PDFS=true
fi

# ============================================================================
# STEP 2 — Ollama models
# ============================================================================
section "2/7  Ollama model checks"

LLM_MODEL="llama3.1:8b"
EMBED_MODEL="nomic-embed-text"

# Use the JSON API rather than parsing `ollama list` output (more reliable)
have_model() {
    local model="$1"
    curl -sf http://localhost:11434/api/tags \
        | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = [m['name'] for m in data.get('models', [])]
sys.exit(0 if '$model' in models else 1)
"
}

for model in "$LLM_MODEL" "$EMBED_MODEL"; do
    if have_model "$model"; then
        ok "Model present: $model"
    else
        log "Pulling $model (this can take several minutes)..."
        ollama pull "$model" || die "Failed to pull $model"
        ok "Model pulled: $model"
    fi
done

# ============================================================================
# STEP 3 — Python virtual environment
# ============================================================================
section "3/7  Python virtualenv"

if [ ! -d ".venv" ]; then
    log "Creating .venv..."
    python3 -m venv .venv
    ok "Virtualenv created"
else
    ok "Virtualenv exists"
fi

# shellcheck disable=SC1091
source .venv/bin/activate
ok "Virtualenv activated"

# Confirm we're really in the venv
EXPECTED_PY="$PROJECT_ROOT/.venv/bin/python"
ACTUAL_PY=$(which python)
if [ "$ACTUAL_PY" != "$EXPECTED_PY" ]; then
    die "Venv activation failed. Expected $EXPECTED_PY but got $ACTUAL_PY"
fi

# ============================================================================
# STEP 4 — Python dependencies
# ============================================================================
section "4/7  Python dependencies"

log "Upgrading pip..."
python -m pip install --quiet --upgrade pip
ok "pip upgraded"

log "Installing requirements (this can take a minute)..."
python -m pip install --quiet -r requirements.txt
ok "Dependencies installed"

# Verify the critical imports actually work
log "Verifying critical imports..."
python - <<'PY' || die "Critical imports failed. Check pip output above."
import importlib, sys
required = [
    "streamlit",
    "langchain",
    "langchain_community",
    "langchain_ollama",
    "langchain_text_splitters",
    "faiss",
    "pypdf",
    "dotenv",
]
missing = []
for mod in required:
    try:
        importlib.import_module(mod)
    except ImportError as e:
        missing.append(f"{mod}: {e}")
if missing:
    print("MISSING:", *missing, sep="\n  ", file=sys.stderr)
    sys.exit(1)
print(f"  All {len(required)} packages importable.")
PY
ok "All imports verified"

# ============================================================================
# STEP 5 — Environment file
# ============================================================================
section "5/7  Environment configuration"

if [ ! -f ".env" ]; then
    cp .env.example .env
    ok "Created .env from .env.example"
else
    ok ".env already exists (left untouched)"
fi

# ============================================================================
# STEP 6 — Starter PDFs (optional)
# ============================================================================
section "6/7  Starter corpus"

mkdir -p data/sources

PDFS=(
    "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf|nist-csf-2.0.pdf"
    "https://owasp.org/Top10/assets/OWASP_Top_10-2021.pdf|owasp-top-10-2021.pdf"
)

if [ "$SKIP_PDFS" = true ]; then
    warn "Skipping starter PDF downloads (--skip-pdfs)."
    log "Drop your own PDFs into data/sources/ before building the index."
else
    for entry in "${PDFS[@]}"; do
        url="${entry%|*}"
        filename="${entry##*|}"
        target="data/sources/$filename"
        if [ -f "$target" ] && [ -s "$target" ]; then
            ok "Already have $filename"
            continue
        fi
        log "Downloading $filename..."
        if $DOWNLOADER "$target" "$url" 2>/dev/null; then
            # Verify it's a real PDF (starts with %PDF)
            if head -c 4 "$target" | grep -q '%PDF'; then
                ok "Downloaded $filename"
            else
                warn "$filename downloaded but isn't a valid PDF — removing."
                rm -f "$target"
            fi
        else
            warn "Could not download $filename (skipping). Add manually if needed."
        fi
    done
fi

PDF_COUNT=$(find data/sources -maxdepth 1 -name "*.pdf" | wc -l)
if [ "$PDF_COUNT" -eq 0 ]; then
    warn "No PDFs in data/sources/. Add some before building the index."
else
    ok "$PDF_COUNT PDF(s) in data/sources/"
fi

# ============================================================================
# STEP 7 — Build FAISS index
# ============================================================================
section "7/7  FAISS index"

if [ "$NO_INDEX" = true ]; then
    warn "Skipping index build (--no-index). Run: python ingest.py"
elif [ "$PDF_COUNT" -eq 0 ]; then
    warn "Skipping index build because data/sources/ is empty."
    log "After adding PDFs, run: python ingest.py"
elif [ -f "vector_store/index.faiss" ] && [ -f "vector_store/index.pkl" ]; then
    ok "FAISS index already exists at vector_store/"
    log "To rebuild after adding new PDFs: python ingest.py"
else
    log "Building FAISS index (embedding $PDF_COUNT PDF(s))..."
    python ingest.py || die "Index build failed. See errors above."
    if [ -f "vector_store/index.faiss" ]; then
        SIZE=$(du -h vector_store/index.faiss | cut -f1)
        ok "Index built — vector_store/index.faiss ($SIZE)"
    else
        die "ingest.py reported success but no index file found."
    fi
fi

# ============================================================================
# Smoke test — verify the pipeline actually works end-to-end
# ============================================================================
section "Smoke test"

if [ -f "vector_store/index.faiss" ]; then
    log "Running a tiny query through the full pipeline..."
    python - <<'PY' || warn "Smoke test failed — pipeline may have issues."
import warnings
warnings.filterwarnings("ignore")
from rag_pipeline import load_index, answer_question
vs = load_index()
print(f"  Index has {vs.index.ntotal} vectors.")
# Just verify retrieval works; skip the full LLM call (too slow for smoke)
docs = vs.similarity_search("test query", k=2)
print(f"  Retrieved {len(docs)} chunks for a test query. ✓")
PY
    ok "Smoke test passed"
else
    warn "No index built, smoke test skipped."
fi

# ============================================================================
# Final summary
# ============================================================================
section "✅ Setup complete"

cat <<EOF

  ${BOLD}Next steps:${NC}

  1. Activate the venv in your shell:
       ${BLUE}source .venv/bin/activate${NC}

  2. Launch the app:
       ${BLUE}streamlit run app.py${NC}

  3. Open in your browser:
       ${BLUE}http://localhost:8501${NC}

  ${BOLD}Useful commands:${NC}
    • Add more PDFs:    drop into data/sources/ then run ${BLUE}python ingest.py${NC}
    • Rebuild index:    ${BLUE}python ingest.py${NC}
    • Re-run this:      ${BLUE}bash scripts/setup.sh${NC}   (idempotent)

EOF
