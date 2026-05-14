"""Tests for feature extraction. Focuses on _ci_status, the trickiest helper."""
from pr_audit.features import _ci_status


def test_check_runs_authoritative_when_combined_is_pending():
    """Modern Actions-only repos: /status returns 'pending', but check_runs say success.
    We must trust check_runs.
    """
    combined = {"state": "pending"}
    check_runs = {"check_runs": [
        {"conclusion": "success"},
        {"conclusion": "success"},
    ]}
    assert _ci_status(combined, check_runs) == "passing"


def test_check_run_failure_overrides_combined_success():
    """If any check_run failed, the PR is failing — even if /status disagrees."""
    combined = {"state": "success"}
    check_runs = {"check_runs": [
        {"conclusion": "success"},
        {"conclusion": "failure"},
    ]}
    assert _ci_status(combined, check_runs) == "failing"


def test_check_run_in_progress_is_pending():
    combined = None
    check_runs = {"check_runs": [
        {"conclusion": "success"},
        {"status": "in_progress", "conclusion": None},
    ]}
    assert _ci_status(combined, check_runs) == "pending"


def test_legacy_combined_status_when_no_check_runs():
    """Old repos with only commit-status checks: fall back to combined."""
    assert _ci_status({"state": "success"}, None) == "passing"
    assert _ci_status({"state": "failure"}, None) == "failing"
    assert _ci_status({"state": "pending"}, None) == "pending"


def test_unknown_when_no_signal():
    assert _ci_status(None, None) == "unknown"
    assert _ci_status({}, {"check_runs": []}) == "unknown"


def test_neutral_conclusion_counts_as_passing():
    """GitHub's 'neutral' conclusion (skipped/no-op checks) shouldn't be treated as a failure."""
    check_runs = {"check_runs": [
        {"conclusion": "success"},
        {"conclusion": "neutral"},
    ]}
    assert _ci_status(None, check_runs) == "passing"


def test_cancelled_check_run_is_failing():
    check_runs = {"check_runs": [
        {"conclusion": "success"},
        {"conclusion": "cancelled"},
    ]}
    assert _ci_status(None, check_runs) == "failing"
