#!/usr/bin/env bash
#
# scripts/healthcheck.sh — Verify SecOps RAG environment is functional.
#
# Run anytime you want to diagnose "is something broken?". Exits 0 if all green,
# non-zero with a clear error if anything is wrong.
#
set -uo pipefail  # NOTE: no -e here; we want to collect ALL failures, not stop at first

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check_pass() { printf "  ${GREEN}✓${NC} %s\n" "$*"; PASS=$((PASS+1)); }
check_fail() { printf "  ${RED}✗${NC} %s\n" "$*"; FAIL=$((FAIL+1)); }
check_warn() { printf "  ${YELLOW}⚠${NC} %s\n" "$*"; WARN=$((WARN+1)); }
section() { printf "\n${BOLD}${BLUE}━━ %s${NC}\n" "$*"; }

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( dirname "$SCRIPT_DIR" )"
cd "$PROJECT_ROOT"

printf "${BOLD}SecOps RAG — Health Check${NC}\n"
printf "Project: %s\n" "$PROJECT_ROOT"

# --- System ---
section "System"
command -v python3 &>/dev/null && check_pass "python3 present" || check_fail "python3 not found"
command -v ollama &>/dev/null  && check_pass "ollama CLI present" || check_fail "ollama CLI not found"

# --- Ollama daemon ---
section "Ollama daemon"
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    check_pass "Daemon responding at localhost:11434"

    # Check required models
    for model in "llama3.1:8b" "nomic-embed-text"; do
        if curl -sf http://localhost:11434/api/tags \
            | python3 -c "import sys,json; sys.exit(0 if '$model' in [m['name'] for m in json.load(sys.stdin).get('models',[])] else 1)"; then
            check_pass "Model available: $model"
        else
            check_fail "Model missing: $model  (fix: ollama pull $model)"
        fi
    done
else
    check_fail "Daemon not responding  (fix: ollama serve)"
fi

# --- Virtualenv ---
section "Python environment"
if [ -d ".venv" ]; then
    check_pass ".venv exists"
    if [ -f ".venv/bin/python" ]; then
        check_pass ".venv/bin/python present"
    else
        check_fail ".venv broken (no bin/python)  (fix: rm -rf .venv && bash scripts/setup.sh)"
    fi
else
    check_fail ".venv missing  (fix: bash scripts/setup.sh)"
fi

# --- Python deps (run inside venv) ---
section "Python dependencies"
if [ -f ".venv/bin/python" ]; then
    .venv/bin/python - <<'PY' 2>/dev/null
import importlib, sys
required = ["streamlit","langchain","langchain_community","langchain_ollama",
            "langchain_text_splitters","faiss","pypdf","dotenv"]
missing = [m for m in required if not importlib.util.find_spec(m)]
if missing:
    print("MISSING:", ",".join(missing))
    sys.exit(1)
sys.exit(0)
PY
    if [ $? -eq 0 ]; then
        check_pass "All required packages importable"
    else
        check_fail "Some packages missing  (fix: .venv/bin/pip install -r requirements.txt)"
    fi
fi

# --- Project files ---
section "Project files"
for f in app.py rag_pipeline.py config.py ingest.py requirements.txt .env.example; do
    [ -f "$f" ] && check_pass "$f" || check_fail "$f missing"
done

# --- Data corpus ---
section "Corpus"
if [ -d "data/sources" ]; then
    PDF_COUNT=$(find data/sources -maxdepth 1 -name "*.pdf" | wc -l)
    if [ "$PDF_COUNT" -gt 0 ]; then
        check_pass "$PDF_COUNT PDF(s) in data/sources/"
        find data/sources -maxdepth 1 -name "*.pdf" | while read -r f; do
            SIZE=$(du -h "$f" | cut -f1)
            printf "      • %s (%s)\n" "$(basename "$f")" "$SIZE"
        done
    else
        check_warn "data/sources/ is empty  (drop PDFs in, then run: python ingest.py)"
    fi
else
    check_fail "data/sources/ missing  (fix: mkdir -p data/sources)"
fi

# --- FAISS index ---
section "Vector index"
if [ -f "vector_store/index.faiss" ] && [ -f "vector_store/index.pkl" ]; then
    SIZE=$(du -h vector_store/index.faiss | cut -f1)
    check_pass "FAISS index present ($SIZE)"

    # Bonus: check vector count
    if [ -f ".venv/bin/python" ]; then
        COUNT=$(.venv/bin/python -c "
import warnings; warnings.filterwarnings('ignore')
from rag_pipeline import load_index
print(load_index().index.ntotal)
" 2>/dev/null) || COUNT="?"
        printf "      Vectors: %s\n" "$COUNT"
    fi
else
    check_warn "No FAISS index yet  (fix: python ingest.py)"
fi

# --- Port check ---
section "Streamlit port"
if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":8501 "; then
        check_warn "Port 8501 is in use (Streamlit may already be running)"
    else
        check_pass "Port 8501 is free"
    fi
elif command -v netstat &>/dev/null; then
    netstat -tln 2>/dev/null | grep -q ":8501 " \
        && check_warn "Port 8501 in use" \
        || check_pass "Port 8501 free"
fi

# --- Summary ---
section "Summary"
printf "  ${GREEN}Passed: %d${NC}   ${YELLOW}Warnings: %d${NC}   ${RED}Failed: %d${NC}\n\n" "$PASS" "$WARN" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    printf "${RED}${BOLD}✗ Some checks failed.${NC} See fixes above.\n"
    exit 1
elif [ "$WARN" -gt 0 ]; then
    printf "${YELLOW}${BOLD}⚠ Healthy but with warnings.${NC}\n"
    exit 0
else
    printf "${GREEN}${BOLD}✓ All systems go.${NC}\n"
    exit 0
fi
