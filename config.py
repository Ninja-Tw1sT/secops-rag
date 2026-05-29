"""Centralized configuration for the SecOps RAG application.

All knobs (models, paths, retrieval params) live here so the rest of the
codebase stays clean and so that environment variables can override defaults
without touching code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Ollama settings
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.1:8b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# Retrieval tuning
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "4"))

# Paths
PROJECT_ROOT = Path(__file__).parent
VECTOR_STORE_PATH = Path(os.getenv("VECTOR_STORE_PATH", PROJECT_ROOT / "vector_store"))
SOURCES_PATH = Path(os.getenv("SOURCES_PATH", PROJECT_ROOT / "data" / "sources"))

# Generation tuning
TEMPERATURE = 0.1  # Low temp for factual, grounded security answers

# The InfoSec-specific system prompt.
# Note the hard refusal rule - this is what makes the RAG "grounded".
SYSTEM_PROMPT = """You are SecOps Copilot, an AI assistant for security analysts \
and GRC professionals. You answer questions strictly from the provided context \
documents (security policies, compliance frameworks, runbooks, advisories).

RULES (these are absolute):
1. Answer ONLY using information from the provided context below.
2. If the context does not contain the answer, respond exactly: \
"I don't have enough information in the provided documents to answer that. \
Consider consulting [relevant source type, e.g., your incident response team \
or the original framework documentation]."
3. Cite the source document and page number for every factual claim using the \
format: (Source: <filename>, page <n>).
4. Never fabricate CVE numbers, control IDs, compliance clauses, or technical \
details. If unsure, refuse per rule 2.
5. For incident-related questions, always recommend human analyst review \
before taking automated action.
6. Be concise. Security teams are time-constrained.

Context documents:
{context}

User question: {question}

Grounded answer:"""
