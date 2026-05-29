"""Core RAG pipeline for SecOps Copilot.

This module is intentionally UI-agnostic so the same pipeline can be driven
by the Streamlit app, a CLI ingest script, or future integrations (Slack bot,
API endpoint, agentic workflow).

Architecture:

    PDFs -> Loader -> Splitter -> Embeddings -> FAISS Index
                                                      |
    User Query -> Embeddings -> FAISS Retriever ------+
                                                      |
                                                      v
                                    LLM (grounded prompt) -> Answer + Citations

"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterable

from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# Model factories
# ---------------------------------------------------------------------------

def get_embeddings() -> OllamaEmbeddings:
    """Return the embeddings model. Centralized so we can swap implementations."""
    return OllamaEmbeddings(
        model=config.EMBEDDING_MODEL,
        base_url=config.OLLAMA_BASE_URL,
    )


def get_llm():
    """Return the chat LLM based on LLM_PROVIDER env var.

    Supported providers:
      - "ollama" (default): fully local via Ollama. Privacy-preserving.
      - "groq": fast cloud inference. Requires GROQ_API_KEY.
      - "openai": cloud inference. Requires OPENAI_API_KEY.

    Temperature kept low (0.1) for factual, grounded InfoSec answers.

    The Ollama path sets num_gpu=0 by default to avoid Vulkan-backend
    token corruption observed on shared boxes with OLLAMA_VULKAN=1 at the
    daemon level. Override via LLM_NUM_GPU in .env if your GPU works.
    """
    provider = config.LLM_PROVIDER

    if provider == "groq":
        if not config.GROQ_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                "Get a free key at https://console.groq.com and add it to .env."
            )
        try:
            from langchain_groq import ChatGroq
        except ImportError as e:
            raise RuntimeError(
                "langchain-groq not installed. Run: pip install langchain-groq"
            ) from e
        return ChatGroq(
            model=config.GROQ_MODEL,
            api_key=config.GROQ_API_KEY,
            temperature=config.TEMPERATURE,
        )

    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Get a key at https://platform.openai.com/api-keys and add it to .env."
            )
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as e:
            raise RuntimeError(
                "langchain-openai not installed. Run: pip install langchain-openai"
            ) from e
        return ChatOpenAI(
            model=config.OPENAI_MODEL,
            api_key=config.OPENAI_API_KEY,
            temperature=config.TEMPERATURE,
        )

    # FIX #9: import os moved to top of file; was previously buried here.
    # Default: Ollama (local)
    num_gpu = int(os.getenv("LLM_NUM_GPU", "0"))
    return ChatOllama(
        model=config.LLM_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=config.TEMPERATURE,
        num_gpu=num_gpu,
    )


# FIX #3: Cache the LLM instance at module level so it is not re-instantiated
# on every call to answer_question(). get_llm() creates a new HTTP client each
# time; calling it per-query wastes time and connection handles under load.
# The cached instance is reused for the lifetime of the Python process.
# Streamlit's @st.cache_resource handles the app-level cache; this handles
# the pipeline-level cache for CLI / non-Streamlit usage.
_llm_instance = None


def get_cached_llm():
    """Return a module-level cached LLM instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = get_llm()
    return _llm_instance


# ---------------------------------------------------------------------------
# Ingestion: PDFs -> chunks -> embeddings -> FAISS index
# ---------------------------------------------------------------------------

def load_pdfs(sources_path: Path) -> tuple[list[Document], list[str]]:
    """Load all PDFs from the sources directory.

    PyPDFLoader attaches `source` (filename) and `page` metadata to each
    Document, which is what enables citations in the final answer.

    Returns:
        A tuple of (documents, failed_filenames) so callers can surface
        load errors rather than silently receiving a short document list.

    FIX #5: Previously swallowed PDF load errors and returned a shorter list
    with no indication of which files failed. Now returns failures explicitly
    so the caller (build_index, ingest.py) can warn or abort.
    """
    if not sources_path.exists():
        raise FileNotFoundError(f"Sources path does not exist: {sources_path}")

    pdf_files = list(sources_path.glob("*.pdf"))
    if not pdf_files:
        raise ValueError(f"No PDFs found in {sources_path}")

    logger.info("Loading %d PDF(s) from %s", len(pdf_files), sources_path)

    documents: list[Document] = []
    failed: list[str] = []

    for pdf in pdf_files:
        try:
            loader = PyPDFLoader(str(pdf))
            docs = loader.load()
            for d in docs:
                d.metadata["source"] = pdf.name
            documents.extend(docs)
            logger.info("  Loaded %s (%d pages)", pdf.name, len(docs))
        except Exception as exc:
            logger.error("  Failed to load %s: %s", pdf.name, exc)
            failed.append(pdf.name)

    if not documents:
        raise ValueError(
            f"All {len(pdf_files)} PDF(s) failed to load. "
            "Check the files in data/sources/ and review the errors above."
        )

    return documents, failed


def split_documents(documents: Iterable[Document]) -> list[Document]:
    """Split documents into overlapping chunks.

    RecursiveCharacterTextSplitter tries to split on natural boundaries
    (paragraphs, then sentences, then words) before resorting to characters.
    This preserves semantic coherence within chunks - critical for InfoSec
    documents where a single control description shouldn't be split mid-sentence.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
        length_function=len,
    )
    chunks = splitter.split_documents(list(documents))
    logger.info(
        "Split into %d chunks (size=%d, overlap=%d)",
        len(chunks), config.CHUNK_SIZE, config.CHUNK_OVERLAP,
    )
    return chunks


def build_index(
    sources_path: Path | None = None,
    vector_store_path: Path | None = None,
) -> tuple[FAISS, int]:
    """End-to-end: load PDFs, split, embed, store in FAISS, persist to disk.

    Returns:
        (vectorstore, chunk_count) — the in-memory FAISS index and the number
        of vectors embedded, for logging without touching FAISS internals.

    FIX #10: Previously returned only the vectorstore and accessed the internal
    vectorstore.index.ntotal attribute in ingest.py. Now returns the chunk count
    directly so callers don't need to reach into FAISS internals.
    """
    sources_path = sources_path or config.SOURCES_PATH
    vector_store_path = vector_store_path or config.VECTOR_STORE_PATH

    documents, failed = load_pdfs(sources_path)
    if failed:
        logger.warning(
            "%d PDF(s) could not be loaded and were skipped: %s",
            len(failed), ", ".join(failed),
        )

    chunks = split_documents(documents)
    chunk_count = len(chunks)

    logger.info("Embedding %d chunks with %s...", chunk_count, config.EMBEDDING_MODEL)
    embeddings = get_embeddings()
    vectorstore = FAISS.from_documents(chunks, embeddings)

    vector_store_path.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(vector_store_path))
    logger.info("Index saved to %s", vector_store_path)

    # Reset cached LLM so a fresh instance picks up any config changes made
    # between runs (e.g., switching LLM_PROVIDER before a rebuild).
    global _llm_instance
    _llm_instance = None

    return vectorstore, chunk_count


def load_index(vector_store_path: Path | None = None) -> FAISS:
    """Load an existing FAISS index from disk."""
    vector_store_path = vector_store_path or config.VECTOR_STORE_PATH

    if not vector_store_path.exists():
        raise FileNotFoundError(
            f"No FAISS index found at {vector_store_path}. "
            "Run `python ingest.py` first."
        )

    embeddings = get_embeddings()
    # allow_dangerous_deserialization is required for FAISS because pickle files
    # can execute arbitrary code. Safe here because WE created the file ourselves.
    # In production with user-uploaded indexes, this would need sandboxing.
    return FAISS.load_local(
        str(vector_store_path),
        embeddings,
        allow_dangerous_deserialization=True,
    )


# ---------------------------------------------------------------------------
# Retrieval + generation
# ---------------------------------------------------------------------------

def format_context(docs: list[Document]) -> str:
    """Format retrieved chunks into a citation-friendly context block.

    Each chunk is prefixed with [Source: filename, page N] so the LLM has
    structured citation info to include in its answer.
    """
    formatted = []
    for i, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        page = doc.metadata.get("page", "?")
        page_human = page + 1 if isinstance(page, int) else page
        formatted.append(
            f"[Chunk {i} | Source: {source}, page {page_human}]\n{doc.page_content}"
        )
    return "\n\n---\n\n".join(formatted)


def answer_question(
    question: str,
    vectorstore: FAISS,
    top_k: int | None = None,
) -> dict:
    """Retrieve relevant chunks and generate a grounded answer.

    Returns a dict with:
      - answer: the LLM's response string
      - sources: list of plain dicts (not Document objects) with keys
        'metadata' and 'page_content', safe for serialization into
        Streamlit session state or JSON.

    FIX #2 / #4: Previously returned live LangChain Document objects which
    were stored directly in st.session_state. Document objects are not safely
    serializable for Streamlit's session state persistence or multiprocessing
    workers. Sources are now returned as plain dicts.

    FIX #3: Uses get_cached_llm() instead of get_llm() to avoid
    re-instantiating the LLM (and its HTTP client) on every query.

    FIX #7: Sends system prompt as SystemMessage and user content as
    HumanMessage so the LLM receives proper role-separated messages rather
    than one big string in the user turn.
    """
    top_k = top_k or config.TOP_K

    # Retrieve
    retrieved_docs = vectorstore.similarity_search(question, k=top_k)
    if not retrieved_docs:
        return {
            "answer": "I don't have enough information in the provided documents to answer that.",
            "sources": [],
        }

    # FIX #7: Send as properly role-separated messages.
    context = format_context(retrieved_docs)
    user_content = config.USER_PROMPT_TEMPLATE.format(
        context=context,
        question=question,
    )
    messages = [
        SystemMessage(content=config.SYSTEM_PROMPT_BASE),
        HumanMessage(content=user_content),
    ]

    # FIX #3: Use cached LLM instance.
    llm = get_cached_llm()
    response = llm.invoke(messages)
    answer = response.content if hasattr(response, "content") else str(response)

    # FIX #2: Serialize Document objects to plain dicts before returning so
    # app.py can safely store them in st.session_state.
    sources = [
        {"metadata": doc.metadata, "page_content": doc.page_content}
        for doc in retrieved_docs
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
