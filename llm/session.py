"""Session-wide switches for the conversation engine.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

from config import TOOLS_ENABLED

# Flipped off for the rest of the session the first time LM Studio
# rejects a tools payload, so a model without a tool template falls back
# to the old keyword triggers instead of erroring on every turn.
_tools_supported = TOOLS_ENABLED


def tools_active():
    return _tools_supported
