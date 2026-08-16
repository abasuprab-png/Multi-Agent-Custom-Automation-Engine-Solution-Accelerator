"""Existing CommsOS Foundry project. No secrets. Do not provision a second account."""

SUBSCRIPTION_ID = "85d4d146-1694-46a2-9830-43ec9f2c5ba2"
RESOURCE_GROUP = "rg-rag-prototype"
ACCOUNT_NAME = "commsos-prod-resource"
PROJECT_NAME = "commsos-prod"
PROJECT_ENDPOINT = (
    "https://commsos-prod-resource.services.ai.azure.com/api/projects/commsos-prod"
)
PROJECT_RESOURCE_ID = (
    f"/subscriptions/{SUBSCRIPTION_ID}/resourceGroups/{RESOURCE_GROUP}"
    f"/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT_NAME}"
    f"/projects/{PROJECT_NAME}"
)
AGENT_NAME = "ally"
DEFAULT_LISTEN_HOST = "0.0.0.0"
DEFAULT_LISTEN_PORT = 8088
