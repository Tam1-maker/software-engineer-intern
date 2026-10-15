# Tools Used

## Development tools

- Python 3.14 for local development and Python 3.12 in the API container
- FastAPI and Uvicorn for the HTTP API
- SQLite through Python's built-in sqlite3 module
- pytest for automated testing
- httpx for OCR and account-opening HTTP clients
- Docker Desktop and Docker Compose v2
- nginx for external routing
- Git and GitHub for source control and submission
- curl for contract exploration and endpoint verification
- macOS Terminal and nano for local development

## External references

I used the repository README files as the primary specification:

- Root README for assessment requirements and submission rules
- q1_api/README.md for the API entry point and test command
- q2_integration/README.md for local integration startup
- mock_ocr/README.md for the OCR contract and failure behavior
- mock_onboarding/README.md for ingestion and idempotency behavior
- q3_deploy/README.md for deployment and operational requirements

The mock services were tested directly with curl before the integration clients were implemented.

## AI assistance

Microsoft Copilot was used for:

- Breaking the exercise into implementation stages
- Explaining Git, Python virtual environments, FastAPI, SQLite, Docker, and nginx
- Drafting initial code structures and automated tests
- Diagnosing Python, Git authentication, pytest, Docker health-check, and shell-command errors
- Reviewing retry, recovery, idempotency, backup, and deployment behavior
- Drafting documentation for later review and editing

All generated or suggested code was run locally, tested, inspected, and modified as necessary. AI-generated content was not accepted solely on the basis that it looked correct.
