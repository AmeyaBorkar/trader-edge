"""Dependency providers for FastAPI routes.

Lazily resolves which DataProvider to use based on the GROWW_ACCESS_TOKEN env
var. A single provider instance is reused across requests; if you want
per-request authentication, replace `_get_provider()` with a Depends() that
reads an Authorization header.
"""
from __future__ import annotations

import os
from functools import lru_cache

from ..api.base import DataProvider
from ..api.mock_provider import MockProvider


@lru_cache(maxsize=1)
def _get_provider() -> DataProvider:
    if os.environ.get("GROWW_ACCESS_TOKEN"):
        from ..api.groww_client import GrowwClient
        return GrowwClient()
    return MockProvider()


def get_provider() -> DataProvider:
    return _get_provider()


def reset_provider_cache() -> None:
    """Used by tests when env vars change between cases."""
    _get_provider.cache_clear()
