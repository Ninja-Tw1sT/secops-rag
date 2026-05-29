"""SecOps Copilot - Streamlit UI.

Run with: streamlit run app.py

"""

from pathlib import Path

import streamlit as st

import config
from rag_pipeline import answer_question, build_index, load_index

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="SecOps Copilot",
    page_icon="🛡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Cached resources
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading vector index...")
def get_vectorstore():
    """Load the FAISS index. Cached across reruns."""
    return load_index()


# FIX #3: Cache the LLM at the Streamlit app level so it is not re-instantiated
# on every query. get_cached_llm() in rag_pipeline handles the pipeline-level
# cache; this ensures Streamlit's resource cache also holds a warm reference.
@st.cache_resource(show_spinner="Loading LLM...")
def get_app_llm():
    """Pre-warm the LLM connection on first load. Cached across reruns."""
    from rag_pipeline import get_cached_llm
    return get_cached_llm()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_sources(sources: list[dict]) -> None:
    """Render a sources expander from a list of serialized source dicts.

    FIX #2 / #4: Sources are now plain dicts (keys: 'metadata', 'page_content')
    rather than live LangChain Document objects. Both the history renderer and
    the live-response renderer use this single function so they stay in sync.
    """
    with st.expander(f"📎 Sources ({len(sources)})"):
        for i, src in enumerate(sources, start=1):
            metadata = src["metadata"]
            page_content = src["page_content"]
            source_name = metadata.get("source", "unknown")
            page = metadata.get("page", "?")
            page_human = page + 1 if isinstance(page, int) else page
            st.markdown(f"**[{i}] {source_name} — page {page_human}**")
            st.text(page_content[:500] + ("..." if len(page_content) > 500 else ""))
            st.divider()


# ---------------------------------------------------------------------------
# Sidebar: corpus management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🛡️ SecOps Copilot")
    st.caption("Grounded Q&A over security & compliance docs")
    st.divider()

    st.subheader("Corpus")
    sources = list(config.SOURCES_PATH.glob("*.pdf")) if config.SOURCES_PATH.exists() else []
    if sources:
        st.write(f"**{len(sources)} document(s) loaded:**")
        for src in sources:
            st.write(f"• {src.name}")
    else:
        st.warning(
            f"No PDFs in `{config.SOURCES_PATH}`. "
            "Drop NIST/CIS/OWASP PDFs there and click rebuild."
        )

    st.divider()
    st.subheader("Index")
    index_exists = config.VECTOR_STORE_PATH.exists()
    if index_exists:
        st.success("✓ Index ready")
    else:
        st.error("✗ No index built yet")

    if st.button("🔄 Rebuild Index", help="Re-embed all PDFs. Slow on first run."):
        with st.spinner("Building index..."):
            try:
                _vs, chunk_count = build_index()
                # FIX #8: Clear only the specific cached resources we care about,
                # not all cached resources in the app. Previously used
                # st.cache_resource.clear() which would nuke every cached
                # resource (including the LLM cache and any future additions).
                get_vectorstore.clear()
                get_app_llm.clear()
                st.success(f"Index rebuilt! ({chunk_count} vectors)")
                st.rerun()
            except Exception as exc:
                st.error(f"Build failed: {exc}")

    st.divider()
    st.subheader("Settings")
    st.write(f"**LLM:** `{config.LLM_MODEL}`")
    st.write(f"**Embeddings:** `{config.EMBEDDING_MODEL}`")
    st.write(f"**Chunks retrieved:** {config.TOP_K}")
    st.caption("🔒 Fully local. No data leaves your machine.")

# ---------------------------------------------------------------------------
# Main panel: chat
# ---------------------------------------------------------------------------

st.title("SecOps Copilot")
st.caption(
    "Ask grounded questions about your security policies, compliance frameworks, "
    "and runbooks. Answers cite the source document and page."
)

# Guard: must have an index
if not config.VECTOR_STORE_PATH.exists():
    st.error(
        "**No FAISS index found.** Drop your PDFs into `data/sources/` and click "
        "**Rebuild Index** in the sidebar, or run `python ingest.py` from your terminal."
    )
    st.stop()

# Session state for chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render history
# FIX #4: Uses _render_sources() which expects plain dicts — consistent with
# how sources are stored (see answer_question fix in rag_pipeline.py).
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            _render_sources(msg["sources"])

# Chat input
if prompt := st.chat_input("Ask about a security policy, control, CVE, or runbook..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Retrieving and reasoning..."):
            vectorstore = get_vectorstore()
            result = answer_question(prompt, vectorstore)

        st.markdown(result["answer"])
        if result["sources"]:
            _render_sources(result["sources"])

    # FIX #2: result["sources"] is already a list of plain dicts (serialized in
    # rag_pipeline.answer_question), safe to store in session_state.
    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
    })
