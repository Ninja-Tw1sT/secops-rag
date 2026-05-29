"""CLI to build the FAISS index from PDFs in data/sources/.

Usage:
    python ingest.py

Run this once after adding/updating documents in data/sources/.
The Streamlit app will then load the index instantly on startup.
"""

import sys
import logging

from rag_pipeline import build_index

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        # FIX #10: build_index() now returns (vectorstore, chunk_count) so we
        # can log the vector count without reaching into the internal
        # vectorstore.index.ntotal attribute, which is undocumented and fragile
        # across LangChain versions.
        vectorstore, chunk_count = build_index()
        logger.info("✓ Index built successfully with %d vectors", chunk_count)
        return 0
    except FileNotFoundError as exc:
        logger.error("✗ %s", exc)
        logger.error("  Drop PDFs into data/sources/ and try again.")
        return 1
    except ValueError as exc:
        logger.error("✗ %s", exc)
        return 1
    except Exception as exc:
        logger.exception("✗ Unexpected error: %s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
