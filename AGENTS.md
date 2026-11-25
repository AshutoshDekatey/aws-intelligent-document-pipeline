# Contributor instructions

Use Python 3.12 and the existing checkout; cloud tasks already have isolation.
Install `.venv/bin/python -m pip install -r requirements-dev.txt` after creating
`.venv` with `python3.12 -m venv .venv`. Run `.venv/bin/pytest` and
`.venv/bin/sam validate --lint` before proposing changes. Never use real AWS
credentials in tests. Keep clients injectable and use mocks. Never deploy,
invoke AWS APIs, upload documents, or create resources without explicit user
approval. Never commit secrets, personal invoices, .env, or samconfig.toml.
Use Decimal for financial arithmetic; maintain strict schema validation.
Document changes in CHANGELOG.md. Distinguish local validation from live AWS
verification. Keep the v0.1 text-only template deployable. v0.2 supports raster OCR and excludes PDFs and payment automation.
