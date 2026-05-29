"""Centralized configuration for the SecOps RAG application.

All knobs (models, paths, retrieval params) live here so the rest of the
codebase stays clean and so that environment variables can override defaults
without touching code.

"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Provider selection: "ollama" (default, local), "groq", or "openai".
# Embeddings stay local on Ollama regardless of LLM provider, so the document
# corpus is never sent to a cloud provider during ingestion.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower().strip()

# Ollama settings (default LLM path, always used for embeddings)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Cloud LLM credentials (only used when LLM_PROVIDER is set accordingly).
# These MUST be loaded from environment, never hardcoded or accepted via UI.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# FIX #6: llama-3.1-70b-versatile deprecated on Groq early 2025; updated default.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Retrieval tuning
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "4"))

# FIX #1: os.getenv() default must be a plain string, not a Path object.
PROJECT_ROOT = Path(__file__).parent
VECTOR_STORE_PATH = Path(os.getenv("VECTOR_STORE_PATH", str(PROJECT_ROOT / "vector_store")))
SOURCES_PATH = Path(os.getenv("SOURCES_PATH", str(PROJECT_ROOT / "data" / "sources")))

# Generation tuning
TEMPERATURE = 0.1  # Low temp for factual, grounded security answers

# FIX #7: Split into system prompt + user turn template so rag_pipeline can
# send them as proper SystemMessage / HumanMessage objects rather than one
# big string stuffed into the user turn.
SYSTEM_PROMPT_BASE = (
    "You are SecOps Copilot, an AI assistant for security analysts "
    "and GRC professionals. You answer questions strictly from the provided context "
    "documents (security policies, compliance frameworks, runbooks, advisories).\n\n"
    "RULES (these are absolute):\n"
    "1. Answer ONLY using information from the provided context below.\n"
    "2. If the context does not contain the answer, respond exactly: "
    '"I don\'t have enough information in the provided documents to answer that. '
    "Consider consulting [relevant source type, e.g., your incident response team "
    'or the original framework documentation]."\n'
    "3. Cite the source document and page number for every factual claim using the "
    "format: (Source: <filename>, page <n>).\n"
    "4. Never fabricate CVE numbers, control IDs, compliance clauses, or technical "
    "details. If unsure, refuse per rule 2.\n"
    "5. For incident-related questions, always recommend human analyst review "
    "before taking automated action.\n"
    "6. Be concise. Security teams are time-constrained."
)

USER_PROMPT_TEMPLATE = "Context documents:\n\n{context}\n\nUser question: {question}\n\nGrounded answer:"
