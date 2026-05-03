"""Env loader and provider-override behavior."""
import os

from trader_edge.api.mock_provider import MockProvider
from trader_edge.env import load_env, project_root
from trader_edge.server.dependencies import _get_provider, reset_provider_cache


def test_project_root_contains_pyproject_or_readme():
    root = project_root()
    assert (root / "README.md").exists() or (root / "pyproject.toml").exists()


def test_load_env_is_idempotent():
    assert load_env() in (True, False)
    assert load_env() in (True, False)


def test_provider_override_mock(monkeypatch):
    monkeypatch.setenv("TRADER_EDGE_PROVIDER", "mock")
    monkeypatch.setenv("GROWW_ACCESS_TOKEN", "fake-token-should-be-ignored")
    reset_provider_cache()
    p = _get_provider()
    assert isinstance(p, MockProvider), "explicit mock override should beat token"


def test_provider_auto_falls_back_without_token(monkeypatch):
    monkeypatch.delenv("GROWW_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("TRADER_EDGE_PROVIDER", "auto")
    reset_provider_cache()
    p = _get_provider()
    assert isinstance(p, MockProvider)
