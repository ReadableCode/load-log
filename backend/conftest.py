# %%
"""Put src/ on the import path for the test suite.

Keeps per-file sys.path hacks out of the tests themselves. Importing config here
also loads the repo .env, which is what supplies POSTGRES_* and the login
credentials the real-dependency tests need.
"""

import os
import sys

SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
