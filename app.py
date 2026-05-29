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
# Index loading (cached so it doesn't reload on every interaction)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner="Loading vector index...")
def get_vectorstore():
    """Load the FAISS index. Cached across reruns."""
    return load_index()


# ---------------------------------------------------------------------------
# Sidebar: corpus management
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🛡️ SecOps Copilot")
    st.caption("Grounded Q&A over security & compliance docs")

    st.divider()
    st.subheader("Corpus")

    # Show what's in data/sources/
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
                build_index()
                st.cache_resource.clear()  # Force reload on next query
                st.success("Index rebuilt!")
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
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            with st.expander(f"📎 Sources ({len(msg['sources'])})"):
                for i, src in enumerate(msg["sources"], start=1):
                    source_name = src.metadata.get("source", "unknown")
                    page = src.metadata.get("page", "?")
                    page_human = page + 1 if isinstance(page, int) else page
                    st.markdown(f"**[{i}] {source_name} — page {page_human}**")
                    st.text(src.page_content[:500] + ("..." if len(src.page_content) > 500 else ""))
                    st.divider()

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
                with st.expander(f"📎 Sources ({len(result['sources'])})"):
                    for i, src in enumerate(result["sources"], start=1):
                        source_name = src.metadata.get("source", "unknown")
                        page = src.metadata.get("page", "?")
                        page_human = page + 1 if isinstance(page, int) else page
                        st.markdown(f"**[{i}] {source_name} — page {page_human}**")
                        st.text(src.page_content[:500] + ("..." if len(src.page_content) > 500 else ""))
                        st.divider()

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
    })
