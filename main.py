"""Article Writer extension — entry point with module hot-reload."""
from __future__ import annotations

import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in list(sys.modules):
    if _m in ("app", "api_client", "params", "response_models", "richtext", "navstate", "skeleton",
              "cache_helpers",
              "handlers_projects", "handlers_articles", "handlers_generate", "handlers_edit",
              "panels_side", "panels_workspace"):
        del sys.modules[_m]

from app import ext, chat  # noqa: E402, F401

import skeleton              # noqa: E402, F401
import handlers_projects     # noqa: E402, F401
import handlers_articles     # noqa: E402, F401
import handlers_generate     # noqa: E402, F401
import handlers_edit         # noqa: E402, F401
import panels_side           # noqa: E402, F401
import panels_workspace      # noqa: E402, F401
