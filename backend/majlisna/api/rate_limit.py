import os

from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared rate limiter instance. Registered on the app in app.py (app.state.limiter).
#
# In-memory storage keeps a separate counter per uvicorn worker, so with
# N workers the real limit becomes N× the configured value. Point this at
# Redis in production (RATE_LIMIT_STORAGE_URI=redis://...) so the limit is
# shared across workers. Defaults to in-memory for tests/single-process dev.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() != "false",
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URI", "memory://"),
)
