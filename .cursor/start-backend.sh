#!/usr/bin/env bash
# Start the backend FastAPI service.
#
# The backend loads Azure configuration at import time and requires a handful of
# variables to be defined. To let the API boot for local/dev work (frontend, MCP,
# tests, non-Azure endpoints) even before real Azure credentials are configured,
# we fill only the *unset/empty* required variables with harmless placeholders.
# Real values injected as Cloud Agent secrets / process env always take precedence,
# and no .env file is written (so nothing overrides genuine secrets).
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/../src/backend"

: "${APP_ENV:=dev}"
: "${AZURE_OPENAI_ENDPOINT:=https://placeholder.openai.azure.com/}"
: "${AZURE_AI_SUBSCRIPTION_ID:=00000000-0000-0000-0000-000000000000}"
: "${AZURE_AI_RESOURCE_GROUP:=placeholder-rg}"
: "${AZURE_AI_PROJECT_NAME:=placeholder-project}"
: "${AZURE_AI_AGENT_ENDPOINT:=https://placeholder.services.ai.azure.com/api/projects/placeholder}"
export APP_ENV AZURE_OPENAI_ENDPOINT AZURE_AI_SUBSCRIPTION_ID \
  AZURE_AI_RESOURCE_GROUP AZURE_AI_PROJECT_NAME AZURE_AI_AGENT_ENDPOINT

exec uv run uvicorn app:app --host 0.0.0.0 --port 8000
