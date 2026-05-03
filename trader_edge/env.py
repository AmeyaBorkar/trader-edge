"""Locate and load the project's .env file once per process.

Idempotent: safe to call from multiple entry points. Existing environment
variables take precedence over .env values, so production deployments can
override settings without touching the file.
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # python-dotenv is optional at import time
    _load_dotenv = None

_LOADED = False


def project_root() -> Path:
    """Repository root — the directory containing the `trader_edge/` package."""
    return Path(__file__).resolve().parent.parent


def load_env() -> bool:
    """Load `.env` from the project root if present. Returns True if a file was loaded."""
    global _LOADED
    if _LOADED:
        return True
    if _load_dotenv is None:
        return False
    env_file = project_root() / ".env"
    if not env_file.exists():
        _LOADED = True
        return False
    _load_dotenv(env_file, override=False)
    _LOADED = True
    return True
