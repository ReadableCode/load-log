# %%
# Imports #

import os
import sys
from os.path import expanduser

from dotenv import load_dotenv

# %%
# Base Paths #

home_dir = expanduser("~")

file_dir = os.path.dirname(
    sys.executable if getattr(sys, "frozen", False) else __file__
)

# %%
# Env #

# Walk up from this file looking for a .env. Stops at the filesystem root.
# In Docker the container has no .env file — it relies on `environment:` from
# docker-compose, so a missing .env is silently fine.
cur = file_dir
for _ in range(6):
    candidate = os.path.join(cur, ".env")
    if os.path.isfile(candidate):
        load_dotenv(candidate)
        break
    parent = os.path.dirname(cur)
    if parent == cur:
        break
    cur = parent

APP_ENV = os.getenv("APP_ENV", "development")

POSTGRES_URL = os.getenv("POSTGRES_URL", "localhost")
POSTGRES_USER = os.getenv("POSTGRES_USER", "")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "apps")
