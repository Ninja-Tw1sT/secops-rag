# SecOps RAG — Makefile
# Run `make` or `make help` to see available targets.

.PHONY: help setup health run ingest clean reset shell test

help:  ## Show this help
	@echo "SecOps RAG — available commands:"
	@echo
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Full one-shot setup (idempotent, safe to re-run)
	@bash scripts/setup.sh

health:  ## Run health checks on the environment
	@bash scripts/healthcheck.sh

run:  ## Launch the Streamlit app
	@.venv/bin/streamlit run app.py

ingest:  ## (Re)build the FAISS index from data/sources/
	@.venv/bin/python ingest.py

clean:  ## Remove the FAISS index (keeps PDFs and venv)
	@rm -rf vector_store
	@echo "✓ Removed vector_store/"

reset:  ## Nuclear option: remove venv AND index (keeps PDFs)
	@rm -rf .venv vector_store
	@echo "✓ Removed .venv/ and vector_store/. Run 'make setup' to rebuild."

shell:  ## Open a Python shell with the pipeline pre-loaded
	@.venv/bin/python -i -c "from rag_pipeline import *; vs = load_index(); print('vectorstore loaded as vs')"

test:  ## Quick end-to-end test query
	@.venv/bin/python -c "from rag_pipeline import load_index, answer_question; \
		r = answer_question('What is the NIST CSF?', load_index()); \
		print(r['answer'][:500]); print('---'); \
		print(f\"Sources: {len(r['sources'])}\")"
