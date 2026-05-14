"""Tests for the Airweave retrieval backend. The SDK is mocked so we don't
need a live Airweave instance to run these.
"""
import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_airweave_sdk(monkeypatch):
    """Inject a fake `airweave` module. The real SDK shape is
    c.collections.search.instant(readable_id=..., query=...) -> SearchV2Response
    where SearchV2Response.results is a list of items each with a
    `textual_representation` attribute.
    """
    fake_module = types.ModuleType("airweave")
    fake_client = MagicMock()

    def _make_item(text: str):
        m = MagicMock()
        m.textual_representation = text
        return m

    response = MagicMock()
    response.results = [
        _make_item("Airweave is a context retrieval layer for AI agents."),
        _make_item("Run pytest before opening a PR; ruff handles formatting."),
        _make_item("Past review: please add a docstring to the public method."),
    ]
    fake_client.collections.search.instant.return_value = response
    fake_module.AirweaveSDK = MagicMock(return_value=fake_client)
    monkeypatch.setitem(sys.modules, "airweave", fake_module)
    # The live throttle protects against API rate limits; tests don't need it.
    monkeypatch.setattr("pr_audit.airweave_backend._throttle", lambda: None)
    return fake_client


def test_get_airweave_config_from_env(monkeypatch):
    from pr_audit.airweave_backend import get_airweave_config

    monkeypatch.delenv("AIRWEAVE_API_KEY", raising=False)
    monkeypatch.delenv("AIRWEAVE_COLLECTION", raising=False)
    assert get_airweave_config() is None

    monkeypatch.setenv("AIRWEAVE_API_KEY", "secret")
    monkeypatch.setenv("AIRWEAVE_COLLECTION", "my-coll")
    assert get_airweave_config() == ("secret", "my-coll")


def test_get_airweave_config_cli_overrides(monkeypatch):
    from pr_audit.airweave_backend import get_airweave_config

    monkeypatch.setenv("AIRWEAVE_API_KEY", "env-key")
    monkeypatch.setenv("AIRWEAVE_COLLECTION", "env-coll")
    assert get_airweave_config("cli-key", "cli-coll") == ("cli-key", "cli-coll")


def test_get_airweave_config_partial_not_configured(monkeypatch):
    from pr_audit.airweave_backend import get_airweave_config

    monkeypatch.setenv("AIRWEAVE_API_KEY", "secret")
    monkeypatch.delenv("AIRWEAVE_COLLECTION", raising=False)
    assert get_airweave_config() is None


def test_fetch_repo_context_via_airweave(mock_airweave_sdk):
    from pr_audit.airweave_backend import fetch_repo_context_via_airweave

    rc = fetch_repo_context_via_airweave("key", "personal-twhw3k", "owner", "repo")
    assert rc.name == "owner/repo"
    # The mock returns the same chunks for every query, so all sections should populate
    assert "Airweave is a context retrieval" in rc.readme_excerpt
    assert "pytest" in rc.contributing_excerpt
    assert len(rc.recent_merged_titles) > 0
    assert len(rc.recent_review_excerpts) > 0
    # SDK was called multiple times (one per query)
    assert mock_airweave_sdk.collections.search.instant.call_count >= 3


def test_fetch_pr_context_via_airweave(mock_airweave_sdk):
    from pr_audit.airweave_backend import fetch_pr_context_via_airweave

    pc = fetch_pr_context_via_airweave(
        "key", "personal-twhw3k",
        pr_title="fix(google_drive): add drive_id config",
        pr_body="Closes #1735",
        changed_files=["backend/sources/google_drive.py"],
    )
    assert len(pc.issue_comments) > 0
    # Search call includes the PR title in the query
    search_call_args = mock_airweave_sdk.collections.search.instant.call_args_list
    assert any("drive_id" in str(call) for call in search_call_args)


def test_search_handles_sdk_failure(mock_airweave_sdk):
    """If Airweave is misconfigured or unreachable, we don't crash and we don't
    leak error strings into the chunk stream (which would surface as fake
    "concerns" in the LLM review). Failure logs to stderr; fields stay empty.
    """
    from pr_audit.airweave_backend import fetch_repo_context_via_airweave

    mock_airweave_sdk.collections.search.instant.side_effect = RuntimeError("network down")
    rc = fetch_repo_context_via_airweave("key", "personal-twhw3k", "owner", "repo")
    assert rc.name == "owner/repo"
    # Fields are empty — no error markers leaked through
    assert rc.readme_excerpt == ""
    assert rc.recent_merged_titles == []
    assert rc.recent_review_excerpts == []
