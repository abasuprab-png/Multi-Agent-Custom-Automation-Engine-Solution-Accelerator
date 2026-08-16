"""Process-wide lock secrets. Production sets these in the Foundry container env."""

import os

os.environ.setdefault("ALLY_LOCK_HMAC_SECRET", "pytest-lock-hmac-secret")
os.environ.setdefault("ALLY_ENTRA_TEST_SECRET", "pytest-entra-hs256")
os.environ.setdefault("ALLY_ENTRA_TENANT_ID", "test-tenant")
os.environ.setdefault("ALLY_ENTRA_AUDIENCE", "ally-lock")
