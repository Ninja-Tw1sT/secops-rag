# 🛡️ SecOps Copilot

> A fully local, privacy-preserving RAG chatbot for security analysts and GRC teams. Ask grounded questions about your security policies, compliance frameworks (NIST, ISO 27001, CIS, OWASP), and incident runbooks — without sending a single byte to a cloud LLM.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Local](https://img.shields.io/badge/runs-100%25%20locally-brightgreen.svg)

---

## 🎯 Problem statement

Security and GRC teams maintain hundreds of pages of policies, control frameworks, advisories, and runbooks. When an analyst needs to know *"Does our access control policy require MFA for production database access?"* or *"Which NIST 800-53 controls map to ISO 27001 A.8.2?"*, the answer exists — but finding it means grepping PDFs or asking a senior colleague.

Cloud LLMs like ChatGPT could answer these questions, but:
- **They hallucinate** control IDs, CVE numbers, and clause references.
- **They can't be trusted** with sensitive internal policies.
- **Most regulated industries forbid** sending compliance documents to third-party APIs.

**SecOps Copilot** solves all three: grounded answers, fully local execution, and citations to the source document and page number for every claim.

---

## ✨ Features

- 🔒 **100% local** — Ollama LLM and embeddings; no API keys, no data exfiltration.
- 📎 **Cited answers** — every response shows source file + page number + retrieved chunk.
- 🚫 **Hard refusal on out-of-scope questions** — the system prompt forbids fabrication.
- ⚡ **Fast retrieval** — FAISS in-memory index, sub-second similarity search.
- 📂 **Multi-document corpus** — drop PDFs in `data/sources/` and rebuild.
- 🖥️ **Streamlit chat UI** with sidebar corpus management.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       INGESTION (one-time)                       │
│                                                                  │
│  PDFs ──▶ PyPDFLoader ──▶ RecursiveCharacterSplitter             │
│                                    │                             │
│                                    ▼                             │
│                          chunks (1000 chars, 200 overlap)        │
│                                    │                             │
│                                    ▼                             │
│              Ollama nomic-embed-text  ──▶  FAISS Index           │
│                                            (saved to disk)      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         QUERY (per request)                      │
│                                                                  │
│  User question                                                   │
│         │                                                        │
│         ▼                                                        │
│  Ollama embed ──▶ FAISS top-k similarity ──▶ retrieved chunks   │
│                                                       │          │
│                                                       ▼          │
│                              Grounded prompt template            │
│                              (with hard refusal rules)           │
│                                                       │          │
│                                                       ▼          │
│                              Ollama llama3.1:8b                 │
│                                                       │          │
│                                                       ▼          │
│                              Answer + citations                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why these choices

| Component | Choice | Why |
|---|---|---|
| LLM | Ollama + `llama3.1:8b` | Fully local, no API costs, strong reasoning, fits in 16GB RAM |
| Embeddings | `nomic-embed-text` | Local, 768-dim, outperforms OpenAI `ada-002` on MTEB benchmarks |
| Vector store | FAISS (CPU) | Zero-infrastructure, file-based persistence, sub-second retrieval at this scale |
| Chunking | Recursive, 1000/200 | Preserves paragraph-level coherence in policy documents |
| Orchestration | LangChain | Standard primitives for loaders, splitters, retrievers, prompts |
| UI | Streamlit | Fastest path from script to demo-able chat app |

---

## 🚀 Quickstart

### Prerequisites
- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- 16GB+ RAM (or use `llama3.2:3b` for lower RAM)

### One-command setup

```bash
make setup
```

That single command:
1. Verifies Python 3.10+ and the Ollama daemon are running.
2. Pulls `llama3.1:8b` and `nomic-embed-text` if missing.
3. Creates a `.venv` and installs all pinned dependencies.
4. Verifies all critical imports succeed.
5. Copies `.env.example` → `.env` if not already present.
6. Downloads starter PDFs (NIST CSF 2.0, OWASP Top 10) into `data/sources/`.
7. Builds the FAISS index.
8. Runs a smoke test through the full pipeline.

Then launch:

```bash
make run    # opens http://localhost:8501
```

### Useful commands

```bash
make help      # show all available commands
make health    # diagnose the environment (run anytime)
make ingest    # rebuild the FAISS index after adding new PDFs
make test      # run a quick end-to-end test query
make clean     # remove the FAISS index (keeps everything else)
make reset     # nuclear: remove venv + index, then `make setup` rebuilds
```

### Manual setup (if you prefer)

<details>
<summary>Click to expand</summary>

```bash
# 1. Pull models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 2. Install dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Add PDFs to data/sources/
# 4. Build the index
python ingest.py

# 5. Launch
streamlit run app.py
```

Suggested starter corpus (all public):
- [NIST Cybersecurity Framework 2.0](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf)
- [NIST SP 800-53 Rev. 5](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-53r5.pdf)
- [CIS Critical Security Controls v8.1](https://www.cisecurity.org/controls)
- [OWASP Top 10 (2021)](https://owasp.org/Top10/)

</details>

---

## 🧪 Demo flow (use this for your video / interview)

1. **Show the privacy guarantee**: open Ollama logs, point out no outbound HTTPS to OpenAI/Anthropic.
2. **In-corpus question**: *"What are the six functions of the NIST Cybersecurity Framework 2.0?"* → grounded answer with citation to the CSF PDF.
3. **Out-of-corpus question**: *"What's the latest Kubernetes CVE?"* → graceful refusal.
4. **Cross-document question**: *"Which OWASP Top 10 risks relate to NIST CSF's Protect function?"* → synthesis with citations from both PDFs.
5. **Show citations panel**: click the 📎 expander to verify each claim against the retrieved chunk.

---

## 🗺️ Roadmap

This RAG chatbot is the foundation for a broader **AI-for-InfoSec portfolio**:

- **Project 2 (LangGraph)** — Incident triage agent: classify alert, enrich with threat intel, draft IR report, route to human reviewer.
- **Project 3 (CrewAI)** — Multi-agent vulnerability assessment: recon agent + CVE lookup + risk scoring + remediation writer.
- **Project 4 (n8n)** — Automated phishing email triage workflow: inbox → URL/attachment analysis → verdict → ticket → Slack.

---

## 💼 Interview talking points

- **Why grounded RAG over fine-tuning?** Compliance frameworks change constantly (NIST CSF 2.0 launched Feb 2024). Re-fine-tuning a 7B model every quarter is expensive and lossy; re-indexing takes minutes and preserves citations.
- **Why local-only?** Most regulated industries (finance, healthcare, defense) cannot send internal policies to third-party APIs. The technical pattern is the differentiator, not the cloud convenience.
- **Why the hard refusal rule?** Security tooling that hallucinates a CVE or control ID is worse than no tool — it actively misleads analysts. The prompt template enforces "I don't know" as a first-class answer.
- **Why human-in-the-loop for incident questions?** Agentic systems acting unilaterally on security incidents is unsafe; the prompt explicitly requires recommending analyst review.
- **How would you scale this?** Swap FAISS → Qdrant/Weaviate for multi-tenant; add reranking (Cohere/bge-reranker); add hybrid search (BM25 + dense); add evaluation harness (Ragas).

---

## 📁 Project structure

```
secops-rag/
├── app.py              # Streamlit UI
├── rag_pipeline.py     # Core RAG logic (UI-agnostic)
├── config.py           # Centralized configuration
├── ingest.py           # CLI ingestion script
├── Makefile            # One-word commands (setup, run, health, ...)
├── scripts/
│   ├── setup.sh        # One-shot setup with health checks
│   └── healthcheck.sh  # Diagnostic script
├── requirements.txt
├── .env.example
├── .gitignore
├── data/sources/       # Drop PDFs here
├── vector_store/       # FAISS index (gitignored)
└── report/             # PDF report for assignment submission
```

---

## 📜 License

MIT. Use freely. If you ship this in production, please cite the original frameworks (NIST, CIS, OWASP) per their respective licenses.

---

## 🙏 Acknowledgements

Built as part of the Codecademy **Building Agentic AI Applications for Beginners** bootcamp.
