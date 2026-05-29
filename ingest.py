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
        vectorstore = build_index()
        # FAISS exposes the internal index; .ntotal gives vector count
        logger.info("✓ Index built successfully with %d vectors", vectorstore.index.ntotal)
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
